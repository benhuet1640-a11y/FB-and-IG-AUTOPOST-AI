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

{performance}
"""

HOOKS = """
HOOK CRAFT (this decides whether anyone reads the post):
First brainstorm 5 very different hooks in "hook_options", one of each type:
  1. Curiosity gap: hints at a payoff without giving it away ("The call you're losing every Friday at 4pm")
  2. Costly mistake: names a mistake the reader is probably making ("You're losing jobs in the first 3 rings")
  3. Audience callout: speaks straight to them ("Plumbing owners: stop doing this after 5pm")
  4. Contrarian: challenges a common belief ("More ads won't fix your empty schedule")
  5. Specific number or list: concrete and scannable ("4 phone habits of fully booked plumbers")
Then pick the ONE that would make a busy plumbing owner stop scrolling, and use it.
Set "hook_type" to its type: curiosity, mistake, callout, contrarian or number.
A great hook is specific, concrete, about THEIR money, time or stress, and under 9 words.
The post must deliver on the hook; no bait-and-switch.
Banned: "Unlock", "Game-changer", "Level up", "In today's world", "Did you know",
"Secret", rhetorical fluff, ALL CAPS sentences, and emojis on the images.
"""

CAROUSEL = """
Write ONE educational carousel post. Pick a specific, useful topic from these themes:
{themes}
""" + HOOKS + """
COVER
- title: the winning hook (max 9 words).
- highlight: 1-3 consecutive words copied EXACTLY from the title to color for emphasis
  (the most emotional or concrete words, e.g. "losing jobs" or "4pm").
- kicker: a 2-4 word label shown above the title, e.g. "PLUMBING OWNERS", "3 COSTLY
  MISTAKES", "SAVE THIS", "FREEZE SEASON".
- subtitle: max 12 words that raise the stakes or promise the payoff.

SLIDES: between {n_min} and {n_max} teaching slides, as many as the idea genuinely needs and no
padding (a sharp single insight can be 1-2 slides; a step-by-step can be {n_max}). The whole post
is the cover + these slides + a CTA slide. Keep people swiping:
- Each heading max 6 words, punchy and specific. Each body max 26 words, plain English,
  concrete (real situations, times of day, what a customer actually says).
- Open loops: at least one slide should end in a way that makes the next slide feel
  necessary (e.g. "But that's not the expensive part...").
- "tip" (use on 2-3 slides, "" on the rest): something the reader can use TODAY, max 16
  words. It must be one of: a word-for-word phone script ('Say: "I can get a tech there by 3.
  Want that slot?"'), a specific action with a time or number ("Check missed calls at 7am
  and 1pm daily."), or a quick test ("Call your own line after 5pm. What happens?").
  Never restate the slide body or give vague advice like "have a process".
- With 3 or more teaching slides, the LAST one is a quick recap/takeaway the reader can
  screenshot. With fewer, every slide should simply be strong on its own.
- Teach, don't sell. No product mentions or calls to action on these slides. (A separate
  final slide handles the CTA.) Never say or imply AI replaces staff.

CAPTION
- First line: a second hook, max 110 characters (it shows before "...more").
- Then 2-3 short sentences of extra value, using line breaks for readability.
- End with ONE specific question that plumbing owners will want to answer in the comments.
- No hashtags or links in the caption. At most 2 emojis in total.
- hashtags: {hashtags}

IMAGE
{image_brief}

Return ONLY JSON:
{{"topic": "...", "hook_options": ["...", "...", "...", "...", "..."], "hook_type": "...",
  "cover": {{"kicker": "...", "title": "...", "highlight": "...", "subtitle": "..."}},
  "slides": [{{"heading": "...", "body": "...", "tip": "..."}}],
  "caption": "...", "hashtags": ["#..."], "image_prompt": "..."}}"""

AD = """
Write ONE single-image ad for {brand}. Pick one sharp angle (for example: the 2am burst
pipe call, a tech who can't answer mid-job, the Monday-morning voicemail pile, the
weekend rush, or getting set up in a day) and build the whole ad around it.
""" + HOOKS + """
- headline: the winning hook, max 8 words, speaking to plumbing business owners.
- highlight: 1-3 consecutive words copied EXACTLY from the headline to color for emphasis.
- subhead: max 18 words, says what we do for them in plain English.
- points: exactly 3 short benefits (max 4 words each), drawn ONLY from "What we offer".
- Caption: first line is a hook (max 110 characters), then 1-2 short sentences in the same
  voice. Don't put links or hashtags in it. At most 1 emoji.
- hashtags: {hashtags}
{image_brief}

Return ONLY JSON:
{{"topic": "...", "hook_options": ["...", "...", "...", "...", "..."], "hook_type": "...",
  "headline": "...", "highlight": "...", "subhead": "...", "points": ["...", "...", "..."],
  "caption": "...", "hashtags": ["#..."], "image_prompt": "..."}}"""

REQUIRED = {"carousel": ("topic", "cover", "slides", "caption"),
            "ad": ("topic", "headline", "subhead", "points", "caption")}


def bullets(items):
    return "\n".join(f"- {i}" for i in items)


IMAGE_PERSON = """- image_prompt: ONE natural, believable moment for the cover with a PERSON as the
  focal point: a plumber, a homeowner or an office manager, with a real, relatable
  expression (e.g. "a plumber in a customer's basement glancing at his ringing phone while
  holding a wrench", or "a worried homeowner on the phone next to a leaking water heater").
  Everyday setting, nothing staged or dramatic. Describe the scene only, not the art style."""

IMAGE_SCENE = """- image_prompt: ONE natural, believable everyday scene for the cover that makes the hook
  feel real; it can be an object or setting rather than a person (e.g. "a phone ringing
  on a workbench in a plumber's van next to a coiled drain snake"). Nothing staged or
  dramatic. Describe the scene only, not the art style."""

NO_TEXT = """
  No text anywhere: if a phone appears, its screen is plain light, never words, icons or caller ID."""


def build_prompt(cfg, kind, recent_topics, local, person=True, performance=""):
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
        performance=performance,
    )
    hashtags = " ".join(c["hashtags"].split())
    image_brief = (IMAGE_PERSON if person else IMAGE_SCENE) + NO_TEXT
    if kind == "ad":
        return shared + AD.format(brand=cfg["brand"]["name"], hashtags=hashtags, image_brief=image_brief)
    n_min, n_max = c["content_slides"]
    return shared + CAROUSEL.format(themes=bullets(c["themes"]), n_min=n_min, n_max=n_max,
                                    hashtags=hashtags, image_brief=image_brief)


def _gemini(prompt, models):
    """Try each model in turn, waiting and retrying when Google says it's busy (429/5xx)."""
    last = None
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        for wait in (0, 10):
            time.sleep(wait)
            try:
                r = requests.post(
                    url,
                    headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
                    json={
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {"responseMimeType": "application/json", "temperature": 1.0},
                    },
                    timeout=90,
                )
            except requests.RequestException as e:  # timeouts and dropped connections are temporary too
                last = f"{model}: {type(e).__name__}"
                print(f"Gemini problem ({last})")
                continue
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
    hook = post["cover"]["title"] if kind == "carousel" else post["headline"]
    if len(hook.split()) > 11:
        raise ValueError(f"hook too long: {hook}")
    if kind == "carousel":
        n_min, n_max = cfg["content"]["content_slides"]
        post["slides"] = post["slides"][:n_max]
        if len(post["slides"]) < n_min:
            raise ValueError("carousel has no teaching slides")
    else:
        post["points"] = post["points"][:3]
    post["kind"] = kind
    return post


EDITOR = """You are a sharp social media editor for {brand}, reviewing a draft {kind} post
written for plumbing business owners. Return the SAME JSON structure with every field kept,
fixing anything that breaks these checks:

1. Rules (non-negotiable):
{rules}
   - Never say or imply AI replaces staff.
{selling_rule}
2. The hook must be specific and scroll-stopping, under 9 words, and the post must deliver on it.
   "highlight" must be words copied exactly from the {hook_field}.
3. Flawless spelling and grammar; plain English a busy owner can skim; no repeated words,
   filler or clichés ("Unlock", "Game-changer", "Level up").
4. Respect the length limits: slide headings max 6 words, bodies max 26 words, tips max
   16 words; ad subhead max 18 words, points max 4 words.
5. Every claim must be generally true. No invented statistics, percentages or studies.
6. Each non-empty "tip" must be a word-for-word script, a specific action with a time or
   number, or a quick test. Rewrite vague tips ("have a process") or ones that repeat the body.
7. image_prompt must describe a natural, believable moment (nothing dramatic or staged) and
   must not ask for any text, words, icons or caller ID on screens or signs.

Make the smallest changes needed; keep what's already good. Return ONLY the JSON.

DRAFT:
{draft}"""

NO_SELLING = """   - This is an EDUCATIONAL carousel. The cover, slides, tips and caption must NOT mention
     {brand}, "we", our service, setup time, demos or any call to action. Rewrite those
     parts as pure, useful advice (a separate final slide already handles the CTA)."""


def edit_post(cfg, post, kind):
    """Second pass: a reviewer prompt that enforces the rules and polishes the copy."""
    prompt = EDITOR.format(
        brand=cfg["brand"]["name"],
        kind="educational carousel" if kind == "carousel" else "single-image ad",
        rules=bullets(cfg["business"]["rules"]),
        selling_rule=NO_SELLING.format(brand=cfg["brand"]["name"]) if kind == "carousel" else "",
        hook_field="cover title" if kind == "carousel" else "headline",
        draft=json.dumps(post, indent=2),
    )
    edited = json.loads(_complete(cfg, prompt))
    return validate(edited, kind, cfg)


def _complete(cfg, prompt):
    """Write with the configured provider; if that fails and the other key exists, use the other one."""
    ai = cfg["ai"]
    gemini = lambda: _gemini(prompt, [ai["gemini_model"], *ai.get("gemini_fallback_models", [])])
    openai = lambda: _openai(prompt, ai["openai_model"])
    order = [("OpenAI", "OPENAI_API_KEY", openai), ("Gemini", "GEMINI_API_KEY", gemini)]
    if ai["provider"] != "openai":
        order.reverse()
    available = [(name, fn) for name, key, fn in order if os.environ.get(key)]
    if not available:
        raise RuntimeError("No AI key found: add a GEMINI_API_KEY or OPENAI_API_KEY secret in GitHub.")
    for i, (name, fn) in enumerate(available):
        try:
            return fn()
        except Exception as e:
            if i == len(available) - 1:
                raise
            print(f"{name} failed ({e}); switching to {available[i + 1][0]} for this post.")


def generate_post(cfg, kind, recent_topics, performance=""):
    local = random.random() < cfg["content"]["local_share"]
    person = random.random() < cfg["content"].get("person_share", 0.8)
    prompt = build_prompt(cfg, kind, recent_topics, local, person, performance)
    last_err = None
    for _ in range(3):  # LLMs occasionally return malformed JSON; just retry
        try:
            post = validate(json.loads(_complete(cfg, prompt)), kind, cfg)
            break
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            last_err = e
    else:
        raise RuntimeError(f"Could not get a valid post from the AI: {last_err}")

    try:
        post = edit_post(cfg, post, kind)
    except Exception as e:  # the draft is still usable if the editor pass fails
        print(f"Editor pass failed, keeping the draft: {e}")
    post["local"] = local
    post["person"] = person
    return post


def generate_cover_image(scene, cfg, art_style):
    """One portrait illustration from OpenAI's image model. Text is added later by render.py."""
    ai = cfg["ai"]
    r = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        json={
            "model": ai["image_model"],
            "prompt": f"{scene}\n\nStyle: {' '.join(ai['image_styles'][art_style].split())}",
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
            "kicker": "PLUMBING OWNERS",
            "title": "You're losing jobs in the first 3 rings",
            "highlight": "losing jobs",
            "subtitle": "What fully booked shops do before the 4th ring",
        },
        "slides": [
            {"heading": "Speed beats price", "body": "Most homeowners book whoever gets back to them first. A quick, friendly reply often matters more than being the cheapest quote.", "tip": "Say: \"I can get a tech there by 3. Want that slot?\""},
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
        "highlight": "2am burst pipe",
        "subhead": "We pick up every call, 24/7, and book the job straight into your schedule.",
        "points": ["24/7 call answering", "Books into your schedule", "Qualifies every lead"],
        "caption": "Plumbing business owners: emergencies don't wait for business hours, and neither do your customers. We answer every call so the job lands on your schedule, not your competitor's.",
        "hashtags": ["#plumbingbusiness", "#plumber", "#emergencyplumber", "#smallbusinessowner", "#plumbingservice"],
        "image_prompt": "a plumber asleep at night while his phone glows on the nightstand in a dark bedroom",
        "local": False,
    },
}
