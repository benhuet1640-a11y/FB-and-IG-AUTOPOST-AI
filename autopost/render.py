"""Turn a post (JSON) into branded 4:5 carousel slides or a single ad image (JPEG, as Instagram requires)."""
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


def _norm(word):
    return "".join(ch for ch in word.lower() if ch.isalnum())


def highlight_mask(words, phrase):
    """Mark the words of `text` that belong to the highlight phrase (first match)."""
    target = [_norm(w) for w in (phrase or "").split() if _norm(w)]
    mask = [False] * len(words)
    norm = [_norm(w) for w in words]
    for i in range(len(words) - len(target) + 1):
        if target and norm[i:i + len(target)] == target:
            for j in range(i, i + len(target)):
                mask[j] = True
            break
    return mask


def fit_rich(draw, text, phrase, weight, size, max_w, max_h, line_gap=1.08, min_size=40):
    """Like fit_text, but keeps track of which words to color."""
    words = text.split()
    mask = highlight_mask(words, phrase)
    while True:
        fnt = font(weight, size)
        lines, line = [], []
        for word, hl in zip(words, mask):
            trial = " ".join(w for w, _ in line + [(word, hl)])
            if line and draw.textlength(trial, font=fnt) > max_w:
                lines.append(line)
                line = []
            line.append((word, hl))
        if line:
            lines.append(line)
        height = int(len(lines) * size * line_gap)
        if height <= max_h or size <= min_size:
            return fnt, lines, height
        size -= 4


def draw_rich(draw, xy, lines, fnt, fill, hl_fill, line_gap=1.08):
    x0, y = xy
    space = draw.textlength(" ", font=fnt)
    for line in lines:
        x = x0
        for word, hl in line:
            draw.text((x, y), word, font=fnt, fill=hl_fill if hl else fill)
            x += draw.textlength(word, font=fnt) + space
        y += int(fnt.lsize * line_gap)
    return y


def kicker(draw, c, text, x, y):
    """Small uppercase label in a pill, e.g. 'PLUMBING OWNERS'."""
    f = font("Bold", 28)
    label = " ".join(text.upper().split())
    tw = draw.textlength(label, font=f)
    draw.rounded_rectangle((x, y, x + tw + 44, y + 54), radius=27, fill=c["teal"])
    draw.text((x + 22, y + 27), label, font=f, fill=WHITE, anchor="lm")


def chrome(draw, c, website, index, total, dark=False):
    """Footer website, slide counter and progress bar shared by every slide."""
    muted = WHITE + "B3" if dark else c["muted"]
    draw.text((PAD, H - PAD - 10), website, font=font("Medium", 30), fill=muted, anchor="ls")
    draw.text((W - PAD, H - PAD - 10), f"{index}/{total}", font=font("Medium", 30), fill=muted, anchor="rs")
    bar_y = H - 56
    draw.rounded_rectangle((PAD, bar_y, W - PAD, bar_y + 8), radius=4,
                           fill=(WHITE if dark else c["navy"]) + "26")
    fill_w = PAD + (W - 2 * PAD) * index / total
    draw.rounded_rectangle((PAD, bar_y, fill_w, bar_y + 8), radius=4, fill=c["teal"])
    draw.ellipse((fill_w - 9, bar_y - 5, fill_w + 9, bar_y + 13), fill=c["amber"])


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


def art_background(c, art=None, fade_from=0.28, fade_to=0.58):
    """AI illustration with a navy fade at the bottom, or a plain branded backdrop if there's no art."""
    if art is not None:
        img = cover_fit(art).convert("RGBA")
        img.alpha_composite(bottom_fade(c["navy"], int(H * S * fade_from), int(H * S * fade_to)))
        return img.convert("RGB")
    img = canvas(c["navy"])
    deco = Draw(img)
    deco.ellipse((W - 420, -260, W + 260, 420), fill=c["teal"])
    deco.ellipse((W - 355, 285, W - 285, 355), fill=c["amber"])
    return img


def cover_slide(post, c, website, total, cover_img=None):
    img = art_background(c, cover_img)
    d = Draw(img)

    icon = logo("icon.png", 92)
    paste(img, icon, (PAD, PAD))

    cover = post["cover"]
    title_f, title_l, title_h = fit_rich(d, cover["title"], cover.get("highlight"), "ExtraBold", 116,
                                         W - 2 * PAD, 520, 1.04)
    sub_f, sub_l, sub_h = fit_text(d, cover["subtitle"], "Medium", 42, W - 2 * PAD, 130, 1.28)
    y = H - 240 - sub_h - 34 - title_h
    if cover.get("kicker"):
        kicker(d, c, cover["kicker"], PAD, y - 84)
    else:
        d.rectangle((PAD, y - 44, PAD + 110, y - 34), fill=c["amber"])
    y = draw_rich(d, (PAD, y), title_l, title_f, WHITE, c["amber"], 1.04)
    draw_block(d, (PAD, y + 34), sub_l, sub_f, WHITE + "D9", 1.28)
    d.text((W - PAD, H - 170), "Swipe  →", font=font("Bold", 38), fill=c["amber"], anchor="rs")
    chrome(d, c, website, 1, total, dark=True)
    return img


def content_slide(slide, num, c, brand, website, index, total):
    img = canvas(c["paper"])
    d = Draw(img)
    icon = logo("icon.png", 56)
    paste(img, icon, (PAD, PAD))
    d.text((PAD + 76, PAD + 28), brand, font=font("Bold", 30), fill=c["navy"], anchor="lm")

    d.text((PAD - 6, 240), f"{num:02d}", font=font("ExtraBold", 170), fill=c["teal"])
    head_f, head_l, _ = fit_text(d, slide["heading"], "ExtraBold", 78, W - 2 * PAD, 270, 1.15)
    y = draw_block(d, (PAD, 470), head_l, head_f, c["navy"], 1.15)
    d.rectangle((PAD, y + 30, PAD + 80, y + 38), fill=c["teal"])
    d.ellipse((PAD + 92, y + 28, PAD + 104, y + 40), fill=c["amber"])
    tip = (slide.get("tip") or "").strip()
    tip_f, tip_l, tip_h = fit_text(d, tip, "SemiBold", 38, W - 2 * PAD - 80, 200, 1.32) if tip else (None, [], 0)
    tip_box = tip_h + 64 if tip else 0
    body_f, body_l, body_h = fit_text(d, slide["body"], "Regular", 48, W - 2 * PAD,
                                      H - y - 250 - (tip_box + 44 if tip else 0), 1.42, min_size=40)
    y = draw_block(d, (PAD, y + 82), body_l, body_f, c["navy"] + "E6", 1.42)
    if tip:
        top = y + 40
        d.rounded_rectangle((PAD, top, W - PAD, top + tip_box), radius=22, fill=c["teal"] + "1F")
        d.rounded_rectangle((PAD, top, PAD + 10, top + tip_box), radius=5, fill=c["teal"])
        draw_block(d, (PAD + 44, top + 30), tip_l, tip_f, c["navy"], 1.32)
    chrome(d, c, website, index, total)
    return img


def cta_slide(cta, c, website, total):
    img = canvas(WHITE)
    d = Draw(img)
    wordmark = logo("wordmark.png", 440)
    paste(img, wordmark, (PAD, 190))

    if cta.get("save_prompt"):
        kicker(d, c, cta["save_prompt"], PAD, 410)
    head_f, head_l, _ = fit_text(d, cta["headline"], "ExtraBold", 86, W - 2 * PAD, 320, 1.12)
    y = draw_block(d, (PAD, 500), head_l, head_f, c["navy"], 1.12)
    body_f, body_l, _ = fit_text(d, cta["body"], "Regular", 44, W - 2 * PAD, 240, 1.4)
    y = draw_block(d, (PAD, y + 36), body_l, body_f, c["muted"], 1.4)

    button(d, c, cta["action"], y + 64)
    chrome(d, c, website, total, total)
    return img


def button(d, c, label, top):
    size = 42
    while True:  # shrink long labels so the pill always fits the slide
        pill_f = font("Bold", size)
        tw = d.textlength(label, font=pill_f)
        if tw + 150 <= W - 2 * PAD or size <= 28:
            break
        size -= 2
    d.rounded_rectangle((PAD, top, PAD + tw + 150, top + 104), radius=52, fill=c["teal"])
    d.text((PAD + 52, top + 52), label, font=pill_f, fill=WHITE, anchor="lm")
    d.text((PAD + tw + 92, top + 52), "→", font=pill_f, fill=c["amber"], anchor="lm")
    return PAD + tw + 150


def ad_image(post, cfg, art=None):
    """Single-image ad: AI art up top, headline + 3 benefits + button over the navy fade."""
    c = cfg["brand"]["colors"]
    img = art_background(c, art, fade_from=0.26, fade_to=0.52)
    d = Draw(img)
    icon = logo("icon.png", 92)
    paste(img, icon, (PAD, PAD))

    max_w = W - 2 * PAD
    head_f, head_l, head_h = fit_rich(d, post["headline"], post.get("highlight"), "ExtraBold", 96, max_w, 320, 1.06)
    sub_f, sub_l, sub_h = fit_text(d, post["subhead"], "Medium", 40, max_w, 160, 1.32)
    point_f = font("SemiBold", 36)
    points_h = 58 * len(post["points"])
    btn_top = H - PAD - 104
    y = btn_top - 56 - points_h - 34 - sub_h - 30 - head_h

    y = draw_rich(d, (PAD, y), head_l, head_f, WHITE, c["amber"], 1.06)
    y = draw_block(d, (PAD, y + 30), sub_l, sub_f, WHITE + "D9", 1.32) + 34
    for pt in post["points"]:
        cy = y + 22
        d.ellipse((PAD, cy - 15, PAD + 30, cy + 15), fill=c["amber"])
        d.line((PAD + 8, cy, PAD + 13, cy + 6, PAD + 22, cy - 6), fill=c["navy"], width=4, joint="curve")
        d.text((PAD + 50, cy), pt, font=point_f, fill=WHITE, anchor="lm")
        y += 58
    button(d, c, cfg["cta"]["action"], btn_top)
    return img


def save(img, out_dir, name):
    """Write the 1080x1350 version (Instagram, committed to the repo) and an HD one for Facebook."""
    (out_dir / "hd").mkdir(exist_ok=True)
    img.save(out_dir / "hd" / name, "JPEG", **JPEG)
    img.resize((W, H), Image.LANCZOS).save(out_dir / name, "JPEG", **JPEG)
    return out_dir / name


def render_post(post, cfg, out_dir, cover_img=None):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if post["kind"] == "ad":
        return [save(ad_image(post, cfg, cover_img), out_dir, "ad.jpg")]
    c, brand, website = cfg["brand"]["colors"], cfg["brand"]["name"], cfg["brand"]["website"]
    total = len(post["slides"]) + 2
    images = [cover_slide(post, c, website, total, cover_img)]
    for i, s in enumerate(post["slides"], start=1):
        images.append(content_slide(s, i, c, brand, website, i + 1, total))
    images.append(cta_slide(cfg["cta"], c, website, total))
    return [save(img, out_dir, f"slide_{i:02d}.jpg") for i, img in enumerate(images, start=1)]
