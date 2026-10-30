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
    "light": {"bg": "#FFFFFF", "text": "#0F1419", "muted": "#536471"},
    "dark": {"bg": "#000000", "text": "#E7E9EA", "muted": "#71767B"},
}
SIDE = 90


def avatar(size, name="icon.png"):
    """A round profile picture: the founder's photo on tweets, the P logo elsewhere."""
    icon = logo(name, size)
    mask = Image.new("L", icon.size, 0)
    ImageDraw.Draw(mask).ellipse((0, 0, icon.size[0] - 1, icon.size[1] - 1), fill=255)
    icon.putalpha(Image.composite(icon.getchannel("A"), mask, mask))
    return icon


def tweet_card(text, cfg, theme):
    """A minimal tweet screenshot: avatar, name, handle, the text. Nothing else (Hormozi-style)."""
    t = THEMES[theme]
    brand = cfg["brand"]
    founder = brand.get("founder") or {}
    img = canvas(t["bg"])
    d = Draw(img)
    max_w = W - 2 * SIDE

    # short tweets get big text, long ones shrink; the block sits just above the middle
    paras = [p.strip() for p in text.split("\n") if p.strip()]
    header_h, gap = 150, 56
    size = 64
    while True:
        f = font("Regular", size)
        blocks = [wrap(d, p, f, max_w) for p in paras]
        text_h = sum(len(b) * int(size * 1.32) for b in blocks) + int(size * 0.7) * (len(blocks) - 1)
        if header_h + gap + text_h <= H - 220 or size <= 40:
            break
        size -= 2
    y = max(90, int((H - (header_h + gap + text_h)) * 0.42))

    paste(img, avatar(header_h, founder.get("avatar", "icon.png")), (SIDE, y))
    nx = SIDE + header_h + 34
    d.text((nx, y + header_h * 0.5 - 6), founder.get("display_name", brand["name"]), font=font("Bold", 46),
           fill=t["text"], anchor="ls")
    d.text((nx, y + header_h * 0.5 + 10), brand["instagram"], font=font("Regular", 42),
           fill=t["muted"], anchor="lt")
    for i in range(2):  # the "··" menu in the corner
        cx = W - SIDE - 10 - i * 18
        d.ellipse((cx - 4, y + 30, cx + 4, y + 38), fill=t["muted"])
    y += header_h + gap

    for b in blocks:
        for ln in b:
            d.text((SIDE, y), ln, font=f, fill=t["text"])
            y += int(size * 1.32)
        y += int(size * 0.7)
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


def render_post(post, cfg, out_dir, photo=None, theme="light"):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fmt = post["format"]
    if fmt == "photo":
        return [save(photo_post(post["headline"], photo, cfg), out_dir, "photo.jpg")]
    tweets = post["tweets"] if fmt == "thread" else [post["tweet"]]
    return [save(tweet_card(t, cfg, theme), out_dir, f"slide_{i + 1:02d}.jpg") for i, t in enumerate(tweets)]
