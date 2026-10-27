"""Ask an LLM for one educational carousel post (structured JSON), plus an optional AI cover image."""
import base64
import io
import json
import os

import requests
from PIL import Image

PROMPT = """You write educational Instagram/Facebook carousel posts for {brand}.

About the business (context only, do NOT pitch it on the teaching slides):
{what_we_do}
{positioning}

Audience: {audience}
Tone: {tone}

Pick ONE specific, useful topic related to these themes:
{themes}

Do NOT repeat or closely resemble any of these recent posts:
{recent}

Rules:
- Teach, don't sell. No product mentions, no calls to action, no "DM us" on any slide.
  (A separate final slide handles the CTA.)
- Never say or imply AI replaces staff. Where AI comes up, frame it as backup that
  helps the team.
- Don't invent statistics, percentages or studies. Use practical, defensible statements.
- Cover slide: a scroll-stopping hook title (max 8 words) and a one-line subtitle.
- Exactly {n} content slides. Each has a heading (max 6 words) and a body (max 30 words).
  One idea per slide, concrete and actionable for a busy owner.
- Caption: 2-4 short sentences that add value on their own, then a blank line,
  then exactly {h} relevant hashtags.
- image_prompt: describe ONE simple illustration scene for the cover that fits the topic
  (e.g. "an HVAC technician on a rooftop with a phone ringing in his pocket").
  Describe the scene only, not the art style, and don't include any text in the image.

Return ONLY JSON in this exact shape:
{{"topic": "...", "cover": {{"title": "...", "subtitle": "..."}},
  "slides": [{{"heading": "...", "body": "..."}}],
  "caption": "...", "image_prompt": "..."}}"""


def build_prompt(cfg, recent_topics):
    c, b = cfg["content"], cfg["business"]
    return PROMPT.format(
        brand=cfg["brand"]["name"],
        what_we_do=b["what_we_do"].strip(),
        positioning=b["positioning"].strip(),
        audience=" ".join(c["audience"].split()),
        tone=c["tone"],
        themes="\n".join(f"- {t}" for t in c["themes"]),
        recent="\n".join(f"- {t}" for t in recent_topics) or "- (none yet)",
        n=c["content_slides"],
        h=c["hashtags_per_post"],
    )


def _gemini(prompt, model):
    key = os.environ["GEMINI_API_KEY"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    r = requests.post(
        url,
        headers={"x-goog-api-key": key},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 1.0},
        },
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


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
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def validate(post, n_slides):
    for key in ("topic", "cover", "slides", "caption"):
        if key not in post:
            raise ValueError(f"AI response missing '{key}'")
    if len(post["slides"]) < 1:
        raise ValueError("AI response has no slides")
    post["slides"] = post["slides"][:n_slides]
    return post


def generate_post(cfg, recent_topics):
    ai = cfg["ai"]
    prompt = build_prompt(cfg, recent_topics)
    last_err = None
    for _ in range(3):  # LLMs occasionally return malformed JSON; just retry
        try:
            if ai["provider"] == "openai":
                raw = _openai(prompt, ai["openai_model"])
            else:
                raw = _gemini(prompt, ai["gemini_model"])
            return validate(json.loads(raw), cfg["content"]["content_slides"])
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


SAMPLE_POST = {
    "topic": "Why the first 5 minutes decide who gets the job",
    "cover": {
        "title": "Why the first 5 minutes decide the job",
        "subtitle": "What fast-responding shops do differently",
    },
    "slides": [
        {"heading": "Speed beats price", "body": "Most homeowners book whoever gets back to them first. A quick, friendly reply often matters more than being the cheapest quote."},
        {"heading": "Interest fades fast", "body": "A customer with a leaking pipe isn't waiting around. If you don't answer, they're already dialing the next number on Google."},
        {"heading": "Voicemail is a dead end", "body": "Many callers hang up instead of leaving a message. If nobody picks up, assume that job is gone."},
        {"heading": "Set a callback standard", "body": "Pick a target, like calling back within 5 minutes during business hours, and make it the whole team's rule."},
        {"heading": "Track what you miss", "body": "Check your call log every Friday. Count missed and unreturned calls. You can't fix what you don't measure."},
    ],
    "caption": "Most jobs aren't lost on price. They're lost because nobody got back to the customer fast enough.\n\nSave this and share it with your office team.\n\n#smallbusiness #homeservices #contractors #customerservice #businesstips",
    "image_prompt": "a plumber kneeling under a kitchen sink with tools while a phone lights up and rings on the counter behind him",
}
