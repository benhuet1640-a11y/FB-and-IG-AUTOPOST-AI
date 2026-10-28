"""
Usage:
  python -m autopost.main generate carousel|ad      # AI writes a post + renders it into posts/<id>/
  python -m autopost.main publish <id>              # posts it to Instagram/Facebook
  python -m autopost.main sample carousel|ad [img]  # renders a built-in sample (no API keys needed)
  python -m autopost.main due                       # what (if anything) is scheduled for this hour?
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from PIL import Image

from autopost.generate import SAMPLES, generate_cover_image, generate_post
from autopost.render import render_post

ROOT = Path(__file__).resolve().parent.parent
POSTS = ROOT / "posts"
HISTORY = ROOT / "history.json"


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


def create(post, cfg, cover_img=None):
    post_id = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    out = POSTS / post_id
    paths = render_post(post, cfg, out, cover_img)
    post["images"] = [p.name for p in paths]
    (out / "post.json").write_text(json.dumps(post, indent=2) + "\n")
    print(f"Rendered {len(paths)} image(s) → {out}")
    print(f"Topic: {post['topic']}")
    set_output("post_id", post_id)
    return post_id


def cmd_generate(kind):
    cfg = load_config()
    recent = [h["topic"] for h in load_history() if h.get("kind", "carousel") == kind][-60:]
    post = generate_post(cfg, kind, recent)
    cover_img = None
    if cfg["ai"].get("cover_image") and post.get("image_prompt"):
        try:
            cover_img = generate_cover_image(post["image_prompt"], cfg)
        except Exception as e:  # a missing picture shouldn't cost us the post
            print(f"Cover image failed, using the plain branded cover: {e}", file=sys.stderr)
    create(post, cfg, cover_img)


def cmd_sample(kind, image_path=None):
    cover_img = Image.open(image_path).convert("RGB") if image_path else None
    create(dict(SAMPLES[kind]), load_config(), cover_img)


def cmd_due():
    sched = load_config()["schedule"]
    hour = datetime.now(ZoneInfo(sched["timezone"])).hour
    kind = sched["slots"].get(hour)
    print(f"New York hour {hour} → {kind or 'nothing scheduled, skipping'}")
    set_output("due", "true" if kind else "false")
    set_output("kind", kind or "")


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
    folder = POSTS / post_id
    post = json.loads((folder / "post.json").read_text())
    urls = [f"{image_base_url()}/posts/{post_id}/{name}" for name in post["images"]]
    result = {"id": post_id, "kind": post["kind"], "topic": post["topic"],
              "posted_at": datetime.now(timezone.utc).isoformat()}

    errors = []
    for platform, fn in (("instagram", post_instagram), ("facebook", post_facebook)):
        if not cfg["platforms"].get(platform):
            continue
        try:
            result[platform] = fn(urls, build_caption(post, cfg, platform))
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
    if cmd == "generate" and len(sys.argv) == 3 and sys.argv[2] in SAMPLES:
        cmd_generate(sys.argv[2])
    elif cmd == "publish" and len(sys.argv) == 3:
        cmd_publish(sys.argv[2])
    elif cmd == "sample" and len(sys.argv) >= 3 and sys.argv[2] in SAMPLES:
        cmd_sample(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    elif cmd == "due":
        cmd_due()
    else:
        sys.exit(__doc__)
