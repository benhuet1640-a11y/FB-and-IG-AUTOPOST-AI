"""Ask an LLM for one post as JSON: a tweet-style thread, a single tweet, or a real-photo post."""
import json
import os
import random
import time

import requests

SHARED = """You write social posts for {brand}. They appear as tweets from {founder}, the founder, so write
as {founder}: "I" for his own view ("I think most plumbers lose more jobs to voicemail than to
price"), "we" for the company ("we built this because...").

About the business:
{what_we_do}
What we offer:
{features}
{positioning}

Audience: {audience}
{local}

VOICE (this is what makes it feel real, not AI):
- First person, founder/team: "we", "I've talked to", "we keep hearing". Like a real person who
  knows the trade texting a plumber they respect. Casual, direct, a little blunt.
- Short sentences. Contractions. Plain words a plumber uses (callback, the van, under a sink,
  the office line, voicemail, the schedule, estimate). One idea per sentence.
- Specific, concrete moments beat general claims: "It's 6:40pm, you're elbow-deep in a
  water heater, the phone buzzes in your pocket. Third time today."
- Illustrative math is fine if framed as a hypothetical ("if a job's worth $400 to you and
  you miss 3 calls a week..."), never as a statistic or a study.
- Do NOT sound like AI marketing. Never use: em dashes, "Here's the thing", "Let's be honest",
  "game-changer", "unlock", "level up", "in today's world", "imagine", "say goodbye to",
  "Did you know", "the secret", lists of three adjectives, rhetorical "Sound familiar?",
  ALL CAPS, more than one emoji, or hashtags inside the post text.

ANGLE: pain → cost → fix.
- Open on ONE real, specific pain plumbing owners feel about the phone. Pick from (or near):
{pains}
- Show what it costs them (jobs, money, nights, stress) in their terms.
- Then the fix: {brand}, said plainly and specifically (what actually happens when a call
  comes in), and an invitation to book a demo at {website}.
- Nothing seasonal or dated. Posts must make sense any day of the year.

Hard rules:
{rules}

HOOK (the first line decides everything):
Brainstorm 5 hooks in "hook_options", one of each type, then use the strongest:
  1. scene: drop them into the moment ("You're under a sink. Phone rings. You let it go.")
  2. hard truth: a blunt line they can't argue with ("The plumber who answers gets the job. Not the best one.")
  3. we-hear: a pattern, not an invented story ("We hear the same thing from plumbers all the
     time: 'I can't answer the phone and do the job.'"). Never invent a specific conversation,
     person, dollar amount or event as if it really happened.
  4. question that stings ("How many calls hit voicemail while you were on a job today?")
  5. number: ("4 calls you missed this week that went to the guy down the street")
Set "hook_type" to scene, truth, heard, question or number. The hook must be under 15 words,
specific, and make a plumbing owner feel seen. No clickbait the post doesn't pay off.

"topic" = a short, specific title for THIS post (not a theme name).
Do NOT repeat or closely resemble any of these recent posts:
{recent}

{performance}
"""

FORMATS = {
    "thread": """
FORMAT: a thread of {n_min}-{n_max} tweets, shown as tweet screenshots people swipe through.
- tweets[0] is the hook tweet: the hook plus at most one more short line. It must make
  people swipe.
- Middle tweets: the pain and what it costs, one beat per tweet, each 1-3 short sentences
  (max 200 characters). Concrete moments, not advice-column lists.
- Last tweet: the fix. Say what {brand} does in plain words and end with the exact line
  "Book a demo at {website}".
- Use as many tweets as the story needs within the range; never pad.
Return ONLY JSON:
{{"topic": "...", "hook_options": ["...","...","...","...","..."], "hook_type": "...",
  "tweets": ["...", "..."], "caption": "...", "hashtags": ["#..."]}}""",

    "tweet": """
FORMAT: ONE standalone tweet shown as a screenshot (max 260 characters). Hook first, then
the pain/cost in a line or two, then the fix, ending with "Book a demo at {website}". It should read like a real
founder's tweet, not an ad.
Return ONLY JSON:
{{"topic": "...", "hook_options": ["...","...","...","...","..."], "hook_type": "...",
  "tweet": "...", "caption": "...", "hashtags": ["#..."]}}""",

    "photo": """
FORMAT: a real photo of a plumber at work with ONE short line of text on it.
- headline: the hook, max 10 words, written like something a person would actually say.
- The caption carries the rest: pain, cost, and the fix with {brand}.
Return ONLY JSON:
{{"topic": "...", "hook_options": ["...","...","...","...","..."], "hook_type": "...",
  "headline": "...", "caption": "...", "hashtags": ["#..."]}}""",
}

CAPTION = """
CAPTION (goes under the post): founder voice, 2-4 short lines with line breaks. Line one is a
second hook (max 110 characters, it shows before "...more"). Add a detail the images don't
say. End with a question plumbing owners will want to answer in the comments. No links,
no hashtags in it, at most 1 emoji.
hashtags: {hashtags}
"""

REQUIRED = {"thread": ("tweets",), "tweet": ("tweet",), "photo": ("headline",)}


def bullets(items):
    return "\n".join(f"- {i}" for i in items)


def build_prompt(cfg, fmt, recent_topics, local, performance=""):
    b, c = cfg["business"], cfg["content"]
    brand, website = cfg["brand"]["name"], cfg["brand"]["website"]
    local_line = (f"This post should feel local to {c['local_market']}: mention Pittsburgh or its "
                  "neighborhoods naturally, the way a local would." if local
                  else "Write for plumbing owners anywhere in the US.")
    shared = SHARED.format(
        brand=brand, website=website, pains=bullets(c["pain_points"]),
        founder=(cfg["brand"].get("founder") or {}).get("name", "the founder"),
        what_we_do=" ".join(b["what_we_do"].split()),
        features=bullets(b["features"]),
        positioning=" ".join(b["positioning"].split()),
        audience=c["audience"],
        local=local_line,
        rules=bullets(b["rules"]),
        recent=bullets(recent_topics) or "- (none yet)",
        performance=performance,
    )
    n_min, n_max = c["thread_tweets"]
    return (shared + FORMATS[fmt].format(brand=brand, website=website, n_min=n_min, n_max=n_max)
            + CAPTION.format(hashtags=" ".join(c["hashtags"].split())))


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


def validate(post, fmt, cfg):
    for key in ("topic", "caption", *REQUIRED[fmt]):
        if not post.get(key):
            raise ValueError(f"AI response missing '{key}'")
    if fmt == "thread":
        n_min, n_max = cfg["content"]["thread_tweets"]
        post["tweets"] = [t.strip() for t in post["tweets"] if t.strip()][:n_max]
        if len(post["tweets"]) < n_min:
            raise ValueError("thread too short")
    if fmt == "photo" and len(post["headline"].split()) > 14:
        raise ValueError("photo headline too long")
    # every tweet-style post ends with the same clear ask
    ask = f"Book a demo at {cfg['brand']['website']}"
    if fmt == "thread" and "book a demo" not in post["tweets"][-1].lower():
        post["tweets"][-1] = post["tweets"][-1].rstrip() + "\n\n" + ask
    if fmt == "tweet" and "book a demo" not in post["tweet"].lower():
        post["tweet"] = post["tweet"].rstrip() + "\n\n" + ask
    post["format"] = fmt
    return post


EDITOR = """You edit social posts for {brand} so they sound like a real founder wrote them,
not an AI. Return the SAME JSON structure with every field kept, fixing anything that breaks:

1. Hard rules:
{rules}
   - Never say or imply AI replaces staff; it covers the calls the team can't get to.
2. Sounds human: short sentences, contractions, plain trade words. Remove em dashes, "Here's
   the thing", "game-changer", "unlock", "imagine", "say goodbye to", "Sound familiar?",
   triple-adjective lists, corporate phrasing and anything that reads like an ad agency.
3. The first line is a strong, specific hook a plumbing owner would stop on. Sharpen it if weak.
4. pain → cost → fix: the fix names {brand} plainly, and tweet posts end with
   "Book a demo at {website}".
5. Nothing seasonal. No invented statistics, studies, people, businesses, conversations or
   events presented as real ("a plumber told me last week..."); turn those into general
   patterns ("we hear this a lot"). Hypothetical math must be framed as hypothetical.
6. Perfect spelling and grammar. Tweets max 200 characters each (single tweet max 260).

Make the smallest changes needed; keep what's already good. Return ONLY the JSON.

DRAFT:
{draft}"""


def edit_post(cfg, post, fmt):
    """Second pass: enforce the rules and strip anything that sounds like AI."""
    prompt = EDITOR.format(brand=cfg["brand"]["name"], website=cfg["brand"]["website"],
                           rules=bullets(cfg["business"]["rules"]), draft=json.dumps(post, indent=2))
    return validate(json.loads(_complete(cfg, prompt)), fmt, cfg)


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


def generate_post(cfg, fmt, recent_topics, performance=""):
    local = random.random() < cfg["content"]["local_share"]
    prompt = build_prompt(cfg, fmt, recent_topics, local, performance)
    last_err = None
    for _ in range(3):  # LLMs occasionally return malformed JSON; just retry
        try:
            post = validate(json.loads(_complete(cfg, prompt)), fmt, cfg)
            break
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            last_err = e
    else:
        raise RuntimeError(f"Could not get a valid post from the AI: {last_err}")

    try:
        post = edit_post(cfg, post, fmt)
    except Exception as e:  # the draft is still usable if the editor pass fails
        print(f"Editor pass failed, keeping the draft: {e}")
    post["local"] = local
    return post


SAMPLES = {
    "thread": {
        "format": "thread",
        "topic": "Voicemail is where plumbing jobs go to die",
        "hook_type": "scene",
        "tweets": [
            "You're under a sink. Phone buzzes. You let it go to voicemail.\n\nThat was probably a job.",
            "Most people calling a plumber don't leave a message. They've got water on the floor. They just call the next number on Google.",
            "So by the time you wipe your hands and call back, they've already booked someone. Not a better plumber. Just the one who picked up.",
            "We built Pipeline Reception for exactly this. Every call gets answered, 24/7. Real jobs get booked straight into your schedule while you finish the one you're on.\n\nBook a demo at pipelinereception.com",
        ],
        "caption": "Most plumbing jobs aren't lost on price. They're lost to voicemail.\n\nWe hear it from owners every week: they find out about the missed call an hour later, and the customer's already gone.\n\nWhat do you do with calls that come in while you're on a job?",
        "hashtags": ["#plumbingbusiness", "#plumber", "#plumbinglife", "#smallbusinessowner", "#tradesbusiness"],
        "local": False,
    },
    "tweet": {
        "format": "tweet",
        "topic": "The plumber who answers gets the job",
        "hook_type": "truth",
        "tweet": "The plumber who answers gets the job. Not the cheapest one. Not the best one.\n\nIf your phone goes to voicemail while you're on a job, someone else is booking your customer.\n\nWe fix that. pipelinereception.com",
        "caption": "Hard truth we keep hearing from owners: the first one to pick up wins.\n\nHow many calls did you miss today?",
        "hashtags": ["#plumbingbusiness", "#plumber", "#smallbusinessowner"],
        "local": False,
    },
    "photo": {
        "format": "photo",
        "topic": "You can't answer the phone with both hands in a wall",
        "hook_type": "scene",
        "headline": "You can't answer the phone with both hands in a wall.",
        "caption": "That's not a time management problem. It's a phone problem.\n\nWe answer every call 24/7 and book the real jobs straight into your schedule, so you can finish the one you're on.\n\nWho's answering your phone right now?",
        "hashtags": ["#plumbingbusiness", "#plumber", "#plumbinglife"],
        "local": False,
    },
}
