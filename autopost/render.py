"""Turn a post (JSON) into tweet-style cards or a real-photo post, as 4:5 JPEGs (what Instagram requires)."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350          # layout units: 4:5 portrait, Instagram's largest feed size
S = 2                      # every slide is drawn at 2x (2160x2700) so text stays razor sharp
PAD = 96
ROOT = Path(__file__).resolve().parent.parent
FONTS, ASSETS = ROOT / "fonts", ROOT / "assets"
WHITE = "#FFFFFF"
JPEG = {"quality": 95, "subsampling": 0, "optimize": True}  # 4:4:4 keeps colored text crisp


def font(weight, size):
    f = ImageFont.truetype(str(FONTS / f"Inter-{weight}.otf"), size * S)
    f.lsize = size  # size in layout units
    return f


def logo(name, width):
    img = Image.open(ASSETS / name).convert("RGBA")
    return img.resize((width * S, round(img.height * width * S / img.width)), Image.LANCZOS)


def paste(img, overlay, xy):
    img.paste(overlay, (round(xy[0] * S), round(xy[1] * S)), overlay)


def canvas(color):
    return Image.new("RGB", (W * S, H * S), color)


class Draw:
    """ImageDraw that takes layout coordinates (1080x1350) and draws at S x resolution."""

    def __init__(self, img):
        self.d = ImageDraw.Draw(img, "RGBA")

    @staticmethod
    def _s(seq):
        return [v * S for v in seq]

    def text(self, xy, text, **kw):
        self.d.text(self._s(xy), text, **kw)

    def textlength(self, text, font):
        return self.d.textlength(text, font=font) / S

    def rectangle(self, box, **kw):
        self.d.rectangle(self._s(box), **kw)

    def rounded_rectangle(self, box, radius=0, **kw):
        self.d.rounded_rectangle(self._s(box), radius=radius * S, **kw)

    def ellipse(self, box, **kw):
        self.d.ellipse(self._s(box), **kw)

    def line(self, xy, width=1, **kw):
        self.d.line(self._s(xy), width=width * S, **kw)

    def arc(self, box, start, end, width=1, **kw):
        self.d.arc(self._s(box), start, end, width=width * S, **kw)

    def polygon(self, xy, width=1, **kw):
        self.d.polygon(self._s(xy), width=width * S, **kw)


def wrap(draw, text, fnt, max_w):
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=fnt) <= max_w:
            line = trial
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def fit_text(draw, text, weight, size, max_w, max_h, line_gap=1.25, min_size=28):
    """Shrink the font until the wrapped text fits in the box."""
    while True:
        fnt = font(weight, size)
        lines = wrap(draw, text, fnt, max_w)
        height = int(len(lines) * size * line_gap)
        if height <= max_h or size <= min_size:
            return fnt, lines, height
        size -= 4


def draw_block(draw, xy, lines, fnt, fill, line_gap=1.25):
    x, y = xy
    for ln in lines:
        draw.text((x, y), ln, font=fnt, fill=fill)
        y += int(fnt.lsize * line_gap)
    return y


def cover_fit(img):
    """Scale an image to fill the slide, cropping a little more from the bottom than the top."""
    rw, rh = W * S, H * S
    scale = max(rw / img.width, rh / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    left = (img.width - rw) // 2
    top = int((img.height - rh) * 0.35)
    return img.crop((left, top, left + rw, top + rh))


def bottom_fade(color_hex, start, end, max_alpha=245):
    """Transparent → brand color gradient so white text stays readable over any image."""
    r, g, b = (int(color_hex[i:i + 2], 16) for i in (1, 3, 5))
    rw, rh = W * S, H * S
    grad = Image.new("RGBA", (rw, rh), (r, g, b, 0))
    d = ImageDraw.Draw(grad)
    for y in range(start, rh):
        a = max_alpha if y >= end else int(max_alpha * ((y - start) / (end - start)) ** 1.4)
        d.line((0, y, rw, y), fill=(r, g, b, a))
    return grad



# ── Tweet-style cards ──────────────────────────────────────────────────────────

THEMES = {
    "light": {"bg": "#FFFFFF", "text": "#0F1419", "muted": "#536471", "line": "#EFF3F4"},
    "dark": {"bg": "#000000", "text": "#E7E9EA", "muted": "#71767B", "line": "#2F3336"},
}
SIDE = 84


def avatar(size, name="icon.png"):
    """A round profile picture: the founder's photo on tweets, the P logo elsewhere."""
    icon = logo(name, size)
    mask = Image.new("L", icon.size, 0)
    ImageDraw.Draw(mask).ellipse((0, 0, icon.size[0] - 1, icon.size[1] - 1), fill=255)
    icon.putalpha(Image.composite(icon.getchannel("A"), mask, mask))
    return icon


def icons_row(d, y, color):
    """Reply, repost, like, bookmark, share: the outline icons under a tweet (no counts)."""
    xs = [SIDE + 20 + i * ((W - 2 * SIDE - 40) / 4) for i in range(5)]
    w = 3
    x = xs[0]  # reply bubble
    d.rounded_rectangle((x, y, x + 40, y + 30), radius=14, outline=color, width=w)
    d.line((x + 10, y + 29, x + 6, y + 40, x + 18, y + 30), width=w, fill=color)
    x = xs[1]  # repost arrows
    d.line((x + 2, y + 14, x + 2, y + 6, x + 34, y + 6), width=w, fill=color)
    d.line((x + 27, y - 1, x + 34, y + 6, x + 27, y + 13), width=w, fill=color)
    d.line((x + 40, y + 24, x + 40, y + 32, x + 8, y + 32), width=w, fill=color)
    d.line((x + 15, y + 25, x + 8, y + 32, x + 15, y + 39), width=w, fill=color)
    x = xs[2]  # heart
    d.arc((x, y, x + 22, y + 22), 140, 360, width=w, fill=color)
    d.arc((x + 18, y, x + 40, y + 22), 180, 40, width=w, fill=color)
    d.line((x + 2, y + 16, x + 20, y + 38, x + 38, y + 16), width=w, fill=color)
    x = xs[3]  # bookmark
    d.line((x + 6, y, x + 34, y, x + 34, y + 40, x + 20, y + 29, x + 6, y + 40, x + 6, y), width=w, fill=color)
    x = xs[4]  # share
    d.line((x + 20, y + 26, x + 20, y), width=w, fill=color)
    d.line((x + 10, y + 10, x + 20, y, x + 30, y + 10), width=w, fill=color)
    d.line((x + 4, y + 22, x + 4, y + 38, x + 36, y + 38, x + 36, y + 22), width=w, fill=color)


def tweet_card(text, cfg, theme, stamp, link_card=False):
    t = THEMES[theme]
    brand = cfg["brand"]
    img = canvas(t["bg"])
    d = Draw(img)
    max_w = W - 2 * SIDE

    # measure everything first so the tweet sits in the middle of the frame
    paras = [p.strip() for p in text.split("\n") if p.strip()]
    card_h, banner = (330, 210) if link_card else (0, 0)
    fixed = 116 + 40 + (card_h + 36 if link_card else 0) + 40 + 34 + 34 + 2 + 30 + 40
    size = 72  # short tweets get big, screenshot-style text; long ones shrink to fit
    while True:
        f = font("Regular", size)
        blocks = [wrap(d, p, f, max_w) for p in paras]
        text_h = sum(len(b) * int(size * 1.34) for b in blocks) + int(size * 0.6) * (len(blocks) - 1)
        if fixed + text_h <= H - 150 or size <= 36:
            break
        size -= 2
    total = fixed + text_h
    y = max(60, (H - total) // 2)

    founder = brand.get("founder") or {}
    paste(img, avatar(116, founder.get("avatar", "icon.png")), (SIDE, y))
    d.text((SIDE + 140, y + 30), founder.get("display_name", brand["name"]), font=font("Bold", 42),
           fill=t["text"], anchor="lm")
    d.text((SIDE + 140, y + 84), brand["instagram"], font=font("Regular", 36), fill=t["muted"], anchor="lm")
    y += 116 + 40

    for b in blocks:
        for ln in b:
            d.text((SIDE, y), ln, font=f, fill=t["text"])
            y += int(size * 1.34)
        y += int(size * 0.6)
    y -= int(size * 0.6)

    if link_card:
        y += 36
        top = y
        d.rounded_rectangle((SIDE, top, W - SIDE, top + card_h), radius=28, outline=t["line"], width=3)
        d.rounded_rectangle((SIDE + 2, top + 2, W - SIDE - 2, top + banner), radius=26, fill="#F4F8F7")
        d.rectangle((SIDE + 2, top + banner - 30, W - SIDE - 2, top + banner), fill="#F4F8F7")
        wm = logo("wordmark.png", 330)
        paste(img, wm, ((W - 330) / 2, top + (banner - wm.size[1] / S) / 2))
        d.text((SIDE + 30, top + banner + 22), brand["website"], font=font("Regular", 30), fill=t["muted"])
        d.text((SIDE + 30, top + banner + 62), "Book a demo · AI receptionist for plumbers", font=font("Medium", 32), fill=t["text"])
        y = top + card_h

    y += 40
    d.text((SIDE, y), stamp, font=font("Regular", 34), fill=t["muted"])
    y += 34 + 34
    d.line((SIDE, y, W - SIDE, y), width=2, fill=t["line"])
    icons_row(d, y + 30, t["muted"])
    return img


# ── Real-photo post ────────────────────────────────────────────────────────────

def photo_post(headline, photo, cfg):
    """A real photo, darkened at the bottom, with one plain line of text and a small logo."""
    img = cover_fit(photo.convert("RGB")).convert("RGBA")
    img.alpha_composite(bottom_fade("#0B0F12", int(H * S * 0.40), int(H * S * 0.78), max_alpha=225))
    img = img.convert("RGB")
    d = Draw(img)
    f, lines, h = fit_text(d, headline, "Bold", 78, W - 2 * SIDE, 460, 1.14, min_size=54)
    y = H - 170 - h
    for ln in lines:
        d.text((SIDE, y), ln, font=f, fill=WHITE)
        y += int(f.lsize * 1.14)
    paste(img, avatar(64), (SIDE, H - 118))
    d.text((SIDE + 84, H - 86), cfg["brand"]["website"], font=font("Medium", 32), fill=WHITE + "D9", anchor="lm")
    return img


def save(img, out_dir, name):
    """Write the 1080x1350 version (Instagram, committed to the repo) and an HD one for Facebook."""
    (out_dir / "hd").mkdir(exist_ok=True)
    img.save(out_dir / "hd" / name, "JPEG", **JPEG)
    img.resize((W, H), Image.LANCZOS).save(out_dir / name, "JPEG", **JPEG)
    return out_dir / name


def render_post(post, cfg, out_dir, photo=None, theme="light", stamp=""):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fmt = post["format"]
    if fmt == "photo":
        return [save(photo_post(post["headline"], photo, cfg), out_dir, "photo.jpg")]
    tweets = post["tweets"] if fmt == "thread" else [post["tweet"]]
    return [save(tweet_card(t, cfg, theme, stamp, link_card=(i == len(tweets) - 1)), out_dir,
                 f"slide_{i + 1:02d}.jpg") for i, t in enumerate(tweets)]
