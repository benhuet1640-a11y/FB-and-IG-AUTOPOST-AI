"""Publish a carousel to Instagram and a multi-photo post to a Facebook Page via the Meta Graph API."""
import os
import time

import requests

API = f"https://graph.facebook.com/{os.environ.get('GRAPH_API_VERSION', 'v23.0')}"


def _call(method, path, **params):
    params["access_token"] = os.environ["META_PAGE_TOKEN"]
    r = requests.request(method, f"{API}/{path}", data=params if method == "POST" else None,
                         params=params if method == "GET" else None, timeout=120)
    if not r.ok:
        raise RuntimeError(f"Meta API error on {path}: {r.status_code} {r.text}")
    return r.json()


def _wait_until_ready(container_id, timeout=300):
    """Instagram processes media asynchronously; publishing too early fails."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = _call("GET", container_id, fields="status_code")["status_code"]
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram container {container_id} failed: {status}")
        time.sleep(5)
    raise TimeoutError(f"Instagram container {container_id} not ready after {timeout}s")


def post_instagram(image_urls, caption):
    ig_user = os.environ["IG_USER_ID"]
    if len(image_urls) == 1:
        container = _call("POST", f"{ig_user}/media", image_url=image_urls[0], caption=caption)["id"]
    else:
        children = [
            _call("POST", f"{ig_user}/media", image_url=u, is_carousel_item="true")["id"]
            for u in image_urls[:10]  # Instagram API carousel limit
        ]
        for c in children:
            _wait_until_ready(c)
        container = _call("POST", f"{ig_user}/media", media_type="CAROUSEL",
                          children=",".join(children), caption=caption)["id"]
    _wait_until_ready(container)
    return _call("POST", f"{ig_user}/media_publish", creation_id=container)["id"]


def post_facebook(image_urls, caption):
    page = os.environ["FB_PAGE_ID"]
    # Upload each photo unpublished, then attach them all to one feed post.
    photo_ids = [_call("POST", f"{page}/photos", url=u, published="false")["id"] for u in image_urls]
    attached = {f"attached_media[{i}]": f'{{"media_fbid":"{pid}"}}' for i, pid in enumerate(photo_ids)}
    return _call("POST", f"{page}/feed", message=caption, **attached)["id"]
