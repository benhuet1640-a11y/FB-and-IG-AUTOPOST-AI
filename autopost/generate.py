"""Ask an LLM for one educational carousel post, returned as structured JSON."""
import json
import os

import requests

PROMPT = """You write educational Instagram/Facebook carousel posts.

Audience: {audience}
Tone: {tone}
Pick ONE specific, useful topic related to these themes:
{themes}

Do NOT repeat or closely resemble any of these recent posts:
{recent}

Rules:
- Teach, don't sell. No product mentions, no calls to action, no "DM us" on any slide.
- Cover slide: a short, curiosity-driving hook title (max 8 words) and a one-line subtitle.
- Exactly {n} content slides. Each has a heading (max 6 words) and a body (max 30 words).
  One idea per slide, concrete and actionable.
- Caption: 2-4 short sentences that add value on their own, then a blank line,
  then exactly {h} relevant hashtags.

Return ONLY JSON in this exact shape:
{{"topic": "...", "cover": {{"title": "...", "subtitle": "..."}},
  "slides": [{{"heading": "...", "body": "..."}}],
  "caption": "..."}}"""


def build_prompt(cfg, recent_topics):
    c = cfg["content"]
    return PROMPT.format(
        audience=c["audience"],
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
        timeout=120,
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


SAMPLE_POST = {
    "topic": "The 5-minute rule for responding to new leads",
    "cover": {
        "title": "Why the first 5 minutes decide the sale",
        "subtitle": "What fast-responding businesses do differently",
    },
    "slides": [
        {"heading": "Speed beats price", "body": "Most customers hire whoever responds first. A quick, friendly reply often matters more than being the cheapest option."},
        {"heading": "Interest fades fast", "body": "A lead that's eager right now may already be calling your competitor in 30 minutes. Momentum is everything."},
        {"heading": "Voicemail is a dead end", "body": "Many callers hang up instead of leaving a message. If nobody answers, assume that lead is gone."},
        {"heading": "Set a response standard", "body": "Pick a target, like replying within 5 minutes during business hours, and make it the team's non-negotiable."},
        {"heading": "Track what you miss", "body": "Check your call log weekly. Count missed calls and unanswered forms. You can't fix what you don't measure."},
    ],
    "caption": "Most leads don't go cold because of price. They go cold because nobody got back to them fast enough.\n\nSave this for your next team meeting.\n\n#smallbusiness #leadgeneration #customerservice #businesstips #salestips",
}
