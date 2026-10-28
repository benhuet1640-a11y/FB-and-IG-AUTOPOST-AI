"""Ask an LLM for one post (educational carousel or single-image ad) as JSON, plus an optional AI image."""
import base64
import io
import json
import os
import random
import time
from datetime import date

import requests
from PIL import Image

SHARED = """You create Instagram/Facebook content for {brand}.

About the business:
{what_we_do}
What we offer:
{features}
{positioning}

Audience: {audience}
Voice: {voice}
Today is {today}. Where it fits naturally, make the post timely for the season
(e.g. frozen pipes in winter, storms and sump pumps in spring, holiday call volume).
{local}

Hard rules:
{rules}

"topic" in your JSON = a short, specific title for THIS post (e.g. "Why 2am callers
never leave voicemails"), not the name of a theme.

Do NOT repeat or closely resemble any of these recent posts:
{recent}
"""

CAROUSEL = """
Write ONE educational carousel post. Pick a specific, useful topic from these themes:
{themes}

- Teach, don't sell. No product mentions or calls to action on the cover or content
  slides. (A separate final slide handles the CTA.)
- Never say or imply AI replaces staff.
- Cover: a scroll-stopping hook title (max 8 words) and a one-line subtitle (max 12 words).
- Exactly {n} content slides. Each has a heading (max 6 words) and a body (max 30 words).
  One idea per slide, concrete and actionable for a busy plumbing business owner.
- Caption: 2-4 short sentences that add value on their own. No hashtags in it.
- hashtags: {hashtags}
- image_prompt: ONE simple illustration scene for the cover that fits the topic
  (e.g. "a plumber under a kitchen sink while a phone rings on the counter").
  Describe the scene only, not the art style. No text in the image.

Return ONLY JSON:
{{"topic": "...", "cover": {{"title": "...", "subtitle": "..."}},
  "slides": [{{"heading": "...", "body": "..."}}],
  "caption": "...", "hashtags": ["#..."], "image_prompt": "..."}}"""

AD = """
Write ONE single-image ad for {brand}. Pick one angle (for example: a missed
emergency call at 2am, a tech who can't answer mid-job, the weekend rush, or getting
set up in a day) and build the ad around it.

- headline: punchy, max 8 words. Speak to plumbing business owners.
- subhead: max 18 words, says what we do for them in plain English.
- points: exactly 3 short benefits (max 4 words each), drawn ONLY from "What we offer".
- Caption: 2-3 short sentences in the same voice. Don't put links or hashtags in it.
- hashtags: {hashtags}
- image_prompt: ONE simple illustration scene that shows the angle (e.g. "a plumber
  asleep at night while his phone glows on the nightstand"). Describe the scene only,
  not the art style. No text in the image.

Return ONLY JSON:
{{"topic": "...", "headline": "...", "subhead": "...", "points": ["...", "...", "..."],
  "caption": "...", "hashtags": ["#..."], "image_prompt": "..."}}"""

REQUIRED = {"carousel": ("topic", "cover", "slides", "caption"),
            "ad": ("topic", "headline", "subhead", "points", "caption")}


def bullets(items):
    return "\n".join(f"- {i}" for i in items)


def build_prompt(cfg, kind, recent_topics, local):
    b, c = cfg["business"], cfg["content"]
    local_line = (f"This post should have a {c['local_market']} angle: local weather, older "
                  "housing stock, neighborhoods or the local business community."
                  if local else "Write for a nationwide audience.")
    shared = SHARED.format(
        brand=cfg["brand"]["name"],
        what_we_do=" ".join(b["what_we_do"].split()),
        features=bullets(b["features"]),
        positioning=" ".join(b["positioning"].split()),
        audience=c["audience"],
        voice=" ".join(b["voice"].split()),
        today=date.today().strftime("%B %d, %Y"),
        local=local_line,
        rules=bullets(b["rules"]),
        recent=bullets(recent_topics) or "- (none yet)",
    )
    hashtags = " ".join(c["hashtags"].split())
    if kind == "ad":
        return shared + AD.format(brand=cfg["brand"]["name"], hashtags=hashtags)
    return shared + CAROUSEL.format(themes=bullets(c["themes"]), n=c["content_slides"], hashtags=hashtags)


def _gemini(prompt, models):
    """Try each model in turn, waiting and retrying when Google says it's busy (429/5xx)."""
    last = None
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        for wait in (0, 15, 45):
            time.sleep(wait)
            r = requests.post(
                url,
                headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"responseMimeType": "application/json", "temperature": 1.0},
                },
                timeout=120,
            )
            if r.ok:
                return r.json()["candidates"][0]["content"]["parts"][0]["text"]
            try:
                reason = r.json()["error"]["message"]
            except (ValueError, KeyError):
                reason = r.text[:300]
            last = f"{model}: {r.status_code} {reason}"
            print(f"Gemini problem ({last})")
            if r.status_code not in (429, 500, 502, 503, 504):
                break  # not a temporary problem; try the next model
    raise RuntimeError(f"Gemini error: {last}")


def _openai(prompt, model):
    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
        },
        timeout=180,
    )
    if not r.ok:
        raise RuntimeError(f"OpenAI error: {r.status_code} {r.text}")
    return r.json()["choices"][0]["message"]["content"]


def validate(post, kind, cfg):
    for key in REQUIRED[kind]:
        if not post.get(key):
            raise ValueError(f"AI response missing '{key}'")
    if kind == "carousel":
        post["slides"] = post["slides"][:cfg["content"]["content_slides"]]
    else:
        post["points"] = post["points"][:3]
    post["kind"] = kind
    return post


def generate_post(cfg, kind, recent_topics):
    ai = cfg["ai"]
    local = random.random() < cfg["content"]["local_share"]
    prompt = build_prompt(cfg, kind, recent_topics, local)
    last_err = None
    for _ in range(3):  # LLMs occasionally return malformed JSON; just retry
        try:
            if ai["provider"] == "openai":
                raw = _openai(prompt, ai["openai_model"])
            else:
                raw = _gemini(prompt, [ai["gemini_model"], *ai.get("gemini_fallback_models", [])])
            post = validate(json.loads(raw), kind, cfg)
            post["local"] = local
            return post
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            last_err = e
    raise RuntimeError(f"Could not get a valid post from the AI: {last_err}")


def generate_cover_image(scene, cfg):
    """One portrait illustration from OpenAI's image model. Text is added later by render.py."""
    ai = cfg["ai"]
    r = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        json={
            "model": ai["image_model"],
            "prompt": f"{scene}\n\nStyle: {' '.join(ai['image_style'].split())}",
            "size": "1024x1536",
            "quality": ai["image_quality"],
            "n": 1,
        },
        timeout=300,
    )
    if not r.ok:
        raise RuntimeError(f"OpenAI image error: {r.status_code} {r.text}")
    return Image.open(io.BytesIO(base64.b64decode(r.json()["data"][0]["b64_json"]))).convert("RGB")


SAMPLES = {
    "carousel": {
        "kind": "carousel",
        "topic": "Why the first 5 minutes decide who gets the job",
        "cover": {
            "title": "Why the first 5 minutes decide the job",
            "subtitle": "What fast-responding plumbing shops do differently",
        },
        "slides": [
            {"heading": "Speed beats price", "body": "Most homeowners book whoever gets back to them first. A quick, friendly reply often matters more than being the cheapest quote."},
            {"heading": "Interest fades fast", "body": "A customer with a leaking pipe isn't waiting around. If you don't answer, they're already dialing the next number on Google."},
            {"heading": "Voicemail is a dead end", "body": "Many callers hang up instead of leaving a message. If nobody picks up, assume that job is gone."},
            {"heading": "Set a callback standard", "body": "Pick a target, like calling back within 5 minutes during business hours, and make it the whole team's rule."},
            {"heading": "Track what you miss", "body": "Check your call log every Friday. Count missed and unreturned calls. You can't fix what you don't measure."},
        ],
        "caption": "Most plumbing jobs aren't lost on price. They're lost because nobody got back to the customer fast enough.\n\nSave this and share it with your office team.",
        "hashtags": ["#plumbingbusiness", "#plumber", "#plumbingcontractor", "#smallbusinessowner", "#homeservices"],
        "image_prompt": "a plumber kneeling under a kitchen sink with tools while a phone lights up and rings on the counter behind him",
        "local": False,
    },
    "ad": {
        "kind": "ad",
        "topic": "The 2am burst pipe call",
        "headline": "Who answers the 2am burst pipe call?",
        "subhead": "We pick up every call, 24/7, and book the job straight into your schedule.",
        "points": ["24/7 call answering", "Books into your schedule", "Qualifies every lead"],
        "caption": "Plumbing business owners: emergencies don't wait for business hours, and neither do your customers. We answer every call so the job lands on your schedule, not your competitor's.",
        "hashtags": ["#plumbingbusiness", "#plumber", "#emergencyplumber", "#smallbusinessowner", "#plumbingservice"],
        "image_prompt": "a plumber asleep at night while his phone glows on the nightstand in a dark bedroom",
        "local": False,
    },
}
