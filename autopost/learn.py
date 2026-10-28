"""Learn from past posts: pull Facebook views/engagement and tell the AI what's working."""
import os
import random
from datetime import datetime, timedelta, timezone

import requests

API = f"https://graph.facebook.com/{os.environ.get('GRAPH_API_VERSION', 'v23.0')}"
# Needs the read_insights permission (views) and pages_read_user_content (reactions/comments).
# Anything the token can't read is simply left out.


def _get(path, **params):
    params["access_token"] = os.environ["META_PAGE_TOKEN"]
    r = requests.get(f"{API}/{path}", params=params, timeout=30)
    return r.json() if r.ok else None


def _insight(post_id, metric):
    data = _get(f"{post_id}/insights", metric=metric)
    try:
        value = data["data"][0]["values"][0]["value"]
    except (TypeError, KeyError, IndexError):
        return None
    return sum(value.values()) if isinstance(value, dict) else value


def _count(post_id, field):
    data = _get(post_id, fields=f"{field}.summary(total_count).limit(0)")
    try:
        return data[field]["summary"]["total_count"]
    except (TypeError, KeyError):
        return None


def fetch_metrics(post_id):
    shares = (_get(post_id, fields="shares") or {}).get("shares", {}).get("count", 0)
    m = {
        "views": _insight(post_id, "post_media_view"),
        "reactions": _count(post_id, "reactions"),
        "comments": _count(post_id, "comments"),
        "shares": shares,
    }
    if m["reactions"] is None:  # without pages_read_user_content, insights still has reactions
        m["reactions"] = _insight(post_id, "post_reactions_by_type_total")
    if m["views"] is None and m["reactions"] is None and m["comments"] is None:
        return None  # token can't read results yet; nothing worth recording
    m["checked_at"] = datetime.now(timezone.utc).isoformat()
    return m


def refresh_metrics(history, max_age_days=30):
    """Update metrics for Facebook posts that are 1-30 days old (newer ones haven't settled yet)."""
    if not os.environ.get("META_PAGE_TOKEN"):
        return
    now = datetime.now(timezone.utc)
    for h in history:
        if not h.get("facebook") or "posted_at" not in h:
            continue
        age = now - datetime.fromisoformat(h["posted_at"])
        if timedelta(days=1) <= age <= timedelta(days=max_age_days):
            if m := fetch_metrics(h["facebook"]):
                h["metrics"] = m


def score(m):
    engagement = (m["reactions"] or 0) + 3 * (m["comments"] or 0) + 5 * (m["shares"] or 0)
    return (m["views"] or 0) + 10 * engagement


def _describe(h):
    m = h["metrics"]
    views = f"{m['views']} views, " if m.get("views") is not None else ""
    return (f'- [{h.get("kind", "carousel")}] "{h.get("hook") or h["topic"]}" '
            f'(hook type: {h.get("hook_type", "?")}, art: {h.get("art_style", "?")}, '
            f'person on cover: {"yes" if h.get("person") else "no"}, '
            f'{"Pittsburgh" if h.get("local") else "national"}) → '
            f'{views}{m["reactions"] or 0} reactions, {m["comments"] or 0} comments, {m["shares"]} shares')


def _averages(measured, key):
    groups = {}
    for h in measured:
        groups.setdefault(h.get(key) or "?", []).append(score(h["metrics"]))
    return {k: sum(v) / len(v) for k, v in groups.items() if k != "?"}


def performance_brief(history, kind, min_posts=3):
    """A short 'what's working' section for the prompt, or a nudge to experiment if there's no data yet."""
    measured = [h for h in history if h.get("metrics") and h.get("kind", "carousel") == kind]
    if len(measured) < min_posts:
        return ("PERFORMANCE: not enough data yet. Experiment: vary hook types, topics and angles "
                "so we learn what this audience responds to.")
    ranked = sorted(measured, key=lambda h: score(h["metrics"]), reverse=True)
    top, bottom = ranked[:3], ranked[-3:] if len(ranked) >= 6 else []
    by_hook = _averages(measured, "hook_type")
    lines = [f"PERFORMANCE: what our last {len(measured)} {kind} posts did on Facebook "
             "(ranked by views and engagement):", "Best:"]
    lines += [_describe(h) for h in top]
    if bottom:
        lines += ["Weakest:"] + [_describe(h) for h in bottom]
    if by_hook:
        best = sorted(by_hook, key=by_hook.get, reverse=True)
        lines.append(f"Hook types from strongest to weakest: {', '.join(best)}.")
    lines.append("Lean toward what the best posts have in common (topics, angles, hook types) about "
                 "70% of the time, and deliberately try something different the other 30% so we "
                 "keep learning. Never reuse a past hook word for word.")
    return "\n".join(lines)


def pick_art_style(history, styles, explore=0.3, min_each=2):
    """Use the better-performing art style most of the time; alternate until there's enough data."""
    measured = [h for h in history if h.get("metrics") and h.get("art_style") in styles]
    avg = _averages(measured, "art_style")
    counts = {s: sum(1 for h in measured if h["art_style"] == s) for s in styles}
    if all(counts[s] >= min_each for s in styles) and random.random() > explore:
        return max(styles, key=lambda s: avg.get(s, 0))
    last = next((h.get("art_style") for h in reversed(history) if h.get("art_style") in styles), None)
    return styles[(styles.index(last) + 1) % len(styles)] if last else styles[0]
