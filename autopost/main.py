"""
Usage:
  python -m autopost.main generate carousel|ad      # AI writes a post + renders it into posts/<id>/
  python -m autopost.main publish <id>              # posts it to Instagram/Facebook
  python -m autopost.main sample thread|tweet|photo [img]  # built-in sample, no API keys needed
  python -m autopost.main due                       # what (if anything) is scheduled for this hour?
"""
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from PIL import Image

from autopost.generate import SAMPLES, generate_post
from autopost.learn import performance_brief, pick_art_style, refresh_metrics
from autopost.render import render_post

ROOT = Path(__file__).resolve().parent.parent
POSTS = ROOT / "posts"
PHOTOS = ROOT / "assets" / "photos"
HISTORY = ROOT / "history.json"


def load_dotenv():
    """For local runs: read KEY=value lines from .env. In GitHub Actions the secrets are already set."""
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep and not key.strip().startswith("#") and value.strip():
            os.environ.setdefault(key.strip(), value.strip())


load_dotenv()


def load_config():
    return yaml.safe_load((ROOT / "config.yaml").read_text())


def load_history():
    return json.loads(HISTORY.read_text()) if HISTORY.exists() else []


def save_history(history):
    HISTORY.write_text(json.dumps(history, indent=2) + "\n")


def set_output(name, value):
    if gh_out := os.environ.get("GITHUB_OUTPUT"):
        with open(gh_out, "a") as f:
            f.write(f"{name}={value}\n")


def create(post, cfg, photo=None):
    post_id = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    if slot := os.environ.get("SLOT"):
        post["slot"] = slot  # marks this scheduled slot as taken
    out = POSTS / post_id
    tz = ZoneInfo(cfg["schedule"]["timezone"])
    stamp = datetime.now(tz).strftime("%-I:%M %p · %b %-d, %Y")  # the tweet's timestamp line
    paths = render_post(post, cfg, out, photo=photo, theme=post.get("theme", "light"), stamp=stamp)
    post["images"] = [p.name for p in paths]
    (out / "post.json").write_text(json.dumps(post, indent=2) + "\n")
    print(f"Rendered {len(paths)} image(s) → {out}")
    print(f"Topic: {post['topic']}")
    set_output("post_id", post_id)
    return post_id


def pick_photo(history):
    """A photo from assets/photos, avoiding the ones used most recently."""
    photos = sorted(p for p in PHOTOS.glob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"))
    if not photos:
        return None
    recent = [h.get("photo") for h in history[-30:] if h.get("photo")]
    fresh = [p for p in photos if p.name not in recent] or photos
    return random.choice(fresh)


def check_secrets(names):
    """Fail early with a clear message instead of a confusing API error."""
    for name in names:
        value = os.environ.get(name, "")
        if value != value.strip():
            os.environ[name] = value.strip()  # stray spaces/newlines from copy-paste
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        sys.exit(f"Missing GitHub secret(s): {', '.join(missing)}. Add them under Settings → "
                 "Secrets and variables → Actions (names must match exactly).")


def prune_old_images(days=21):
    """Published images aren't needed after a few weeks; keep post.json, drop the JPEGs."""
    cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
    for folder in POSTS.iterdir():
        if folder.is_dir() and (folder / "post.json").exists() and folder.stat().st_mtime < cutoff:
            for jpg in folder.rglob("*.jpg"):
                jpg.unlink()


def pick_format(kind, history, cfg):
    """Carousel slots are tweet threads; single-post slots alternate real photos and single tweets."""
    if kind == "carousel":
        return "thread"
    if not any(PHOTOS.glob("*")):
        return "tweet"
    return pick_art_style(history, ["photo", "tweet"])


def cmd_generate(kind):
    cfg = load_config()
    prune_old_images()
    for key in ("GEMINI_API_KEY", "OPENAI_API_KEY", "META_PAGE_TOKEN"):
        if not os.environ.get(key, "").strip():
            print(f"Note: {key} is not set.", file=sys.stderr)
    history = load_history()
    try:  # learn from how earlier posts did before writing the next one
        refresh_metrics(history)
        save_history(history)
    except Exception as e:
        print(f"Couldn't refresh post metrics, continuing without them: {e}", file=sys.stderr)
    recent = [h["topic"] for h in history][-60:]
    fmt = pick_format(kind, history, cfg)
    post = generate_post(cfg, fmt, recent, performance_brief(history, kind))
    post["kind"] = kind
    post["art_style"] = fmt  # what learn.py compares between posts
    post["theme"] = random.choice(["light", "dark"])
    photo = None
    if fmt == "photo":
        path = pick_photo(history)
        post["photo"] = path.name
        photo = Image.open(path)
    create(post, cfg, photo)


def cmd_sample(fmt, image_path=None):
    """Render a built-in example post (no API keys needed). fmt: thread, tweet or photo."""
    post = dict(SAMPLES[fmt], kind="carousel" if fmt == "thread" else "ad", theme="light")
    photo = None
    if fmt == "photo":
        photo = Image.open(image_path) if image_path else Image.open(pick_photo([]))
    create(post, load_config(), photo)


def slot_done(slot):
    """True if this slot already has a post (generated or published), so we never double-post."""
    if any(h.get("slot") == slot for h in load_history()):
        return True
    for f in POSTS.glob("*/post.json"):
        try:
            if json.loads(f.read_text()).get("slot") == slot:
                return True
        except ValueError:
            continue
    return False


def due_slot(now=None):
    """The earliest slot today that has started, is still within the catch-up window and isn't posted yet."""
    sched = load_config()["schedule"]
    tz = ZoneInfo(sched["timezone"])
    now = now or datetime.now(tz)
    window = timedelta(hours=sched.get("catch_up_hours", 3))
    for hhmm, kind in sorted(sched["slots"].items()):
        h, m = map(int, str(hhmm).split(":"))
        start = now.replace(hour=h, minute=m, second=0, microsecond=0)
        slot = start.strftime("%Y-%m-%d %H:%M")
        if start <= now < start + window and not slot_done(slot):
            return slot, kind
    return None, None


def cmd_due():
    tz = load_config()["schedule"]["timezone"]
    slot, kind = due_slot()
    now = datetime.now(ZoneInfo(tz)).strftime("%H:%M")
    print(f"New York time {now} → {f'posting the {slot} {kind}' if slot else 'nothing due, skipping'}")
    set_output("due", "true" if slot else "false")
    set_output("kind", kind or "")
    set_output("slot", slot or "")


def build_caption(post, cfg, platform):
    extra = cfg["captions"][platform][post["kind"]]
    tags = list(dict.fromkeys(post.get("hashtags", []) + [cfg["captions"]["always_hashtag"]]))
    return f"{post['caption'].strip()}\n\n{extra}\n\n{' '.join(tags)}"


def image_base_url():
    if base := os.environ.get("IMAGE_BASE_URL"):
        return base.rstrip("/")
    repo, sha = os.environ["GITHUB_REPOSITORY"], os.environ["COMMIT_SHA"]
    return f"https://raw.githubusercontent.com/{repo}/{sha}"


def cmd_publish(post_id):
    from autopost.publish import post_facebook, post_instagram

    cfg = load_config()
    check_secrets(["META_PAGE_TOKEN"] + (["FB_PAGE_ID"] if cfg["platforms"].get("facebook") else []))
    if cfg["platforms"].get("instagram") and not os.environ.get("IG_USER_ID", "").strip():
        print("Instagram is on but the IG_USER_ID secret is missing; posting to Facebook only.",
              file=sys.stderr)
        cfg["platforms"]["instagram"] = False
    folder = POSTS / post_id
    post = json.loads((folder / "post.json").read_text())
    files = [folder / name for name in post["images"]]
    result = {"id": post_id, "kind": post["kind"], "topic": post["topic"],
              "hook": (post.get("tweets") or [post.get("tweet") or post.get("headline")])[0].split("\n")[0],
              "format": post.get("format"), "photo": post.get("photo"),
              "hook_type": post.get("hook_type"), "art_style": post.get("art_style"),
              "person": post.get("person"), "local": post.get("local"), "slot": post.get("slot"),
              "posted_at": datetime.now(timezone.utc).isoformat()}

    errors = []
    for platform, fn in (("instagram", post_instagram), ("facebook", post_facebook)):
        if not cfg["platforms"].get(platform):
            continue
        try:
            # Facebook takes the files directly; Instagram only accepts public image URLs.
            hd = [f.parent / "hd" / f.name for f in files]
            media = (hd if all(p.exists() for p in hd) else files) if platform == "facebook" else \
                [f"{image_base_url()}/posts/{post_id}/{f.name}" for f in files]
            result[platform] = fn(media, build_caption(post, cfg, platform))
            print(f"Posted to {platform}: {result[platform]}")
        except Exception as e:  # keep going so one platform failing doesn't block the other
            errors.append(f"{platform}: {e}")
            print(f"FAILED on {platform}: {e}", file=sys.stderr)

    history = load_history()
    history.append(result)
    save_history(history)
    if errors:
        sys.exit("Some platforms failed:\n" + "\n".join(errors))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "generate" and len(sys.argv) == 3 and sys.argv[2] in ("carousel", "ad"):
        cmd_generate(sys.argv[2])
    elif cmd == "publish" and len(sys.argv) == 3:
        cmd_publish(sys.argv[2])
    elif cmd == "sample" and len(sys.argv) >= 3 and sys.argv[2] in SAMPLES:
        cmd_sample(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    elif cmd == "due":
        cmd_due()
    else:
        sys.exit(__doc__)
