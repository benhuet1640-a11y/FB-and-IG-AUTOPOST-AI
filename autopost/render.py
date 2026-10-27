"""Turn a post (JSON) into branded 1080x1350 carousel slides (JPEG — Instagram's required format)."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350          # 4:5 portrait, the largest feed size Instagram allows
PAD = 96
FONTS = Path(__file__).resolve().parent.parent / "fonts"


def font(weight, size):
    return ImageFont.truetype(str(FONTS / f"Inter-{weight}.otf"), size)


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
        y += int(fnt.size * line_gap)
    return y


def chrome(draw, colors, handle, index, total):
    """Footer handle, slide counter and progress bar shared by every slide."""
    draw.text((PAD, H - PAD - 10), handle, font=font("Medium", 30), fill=colors["muted"], anchor="ls")
    draw.text((W - PAD, H - PAD - 10), f"{index}/{total}", font=font("Medium", 30), fill=colors["muted"], anchor="rs")
    bar_y = H - 56
    draw.rounded_rectangle((PAD, bar_y, W - PAD, bar_y + 8), radius=4, fill=colors["muted"] + "40")
    fill_w = PAD + (W - 2 * PAD) * index / total
    draw.rounded_rectangle((PAD, bar_y, fill_w, bar_y + 8), radius=4, fill=colors["accent"])


def new_slide(colors):
    img = Image.new("RGB", (W, H), colors["background"])
    return img, ImageDraw.Draw(img, "RGBA")


def cover_slide(post, colors, handle, total):
    img, d = new_slide(colors)
    d.rectangle((PAD, 300, PAD + 120, 312), fill=colors["accent"])
    fnt, lines, h = fit_text(d, post["cover"]["title"], "ExtraBold", 104, W - 2 * PAD, 560, 1.12)
    y = draw_block(d, (PAD, 360), lines, fnt, colors["text"], 1.12)
    sub_f, sub_l, _ = fit_text(d, post["cover"]["subtitle"], "Regular", 44, W - 2 * PAD, 220)
    draw_block(d, (PAD, y + 40), sub_l, sub_f, colors["muted"])
    d.text((W - PAD, H - 190), "Swipe  →", font=font("Bold", 40), fill=colors["accent"], anchor="rs")
    chrome(d, colors, handle, 1, total)
    return img


def content_slide(slide, num, colors, handle, index, total):
    img, d = new_slide(colors)
    d.text((PAD, 200), f"{num:02d}", font=font("ExtraBold", 150), fill=colors["accent"] + "55")
    head_f, head_l, hh = fit_text(d, slide["heading"], "Bold", 76, W - 2 * PAD, 280, 1.15)
    y = draw_block(d, (PAD, 420), head_l, head_f, colors["text"], 1.15)
    d.rectangle((PAD, y + 30, PAD + 80, y + 38), fill=colors["accent"])
    body_f, body_l, _ = fit_text(d, slide["body"], "Regular", 48, W - 2 * PAD, H - y - 330, 1.4)
    draw_block(d, (PAD, y + 80), body_l, body_f, colors["text"] + "DD", 1.4)
    chrome(d, colors, handle, index, total)
    return img


def cta_slide(cta, colors, handle, total):
    img, d = new_slide(colors)
    head_f, head_l, _ = fit_text(d, cta["headline"], "ExtraBold", 92, W - 2 * PAD, 340, 1.12)
    y = draw_block(d, (PAD, 380), head_l, head_f, colors["text"], 1.12)
    body_f, body_l, _ = fit_text(d, cta["body"], "Regular", 46, W - 2 * PAD, 260, 1.35)
    y = draw_block(d, (PAD, y + 40), body_l, body_f, colors["muted"], 1.35)
    pill_f = font("Bold", 40)
    tw = d.textlength(cta["action"], font=pill_f)
    top = y + 70
    d.rounded_rectangle((PAD, top, PAD + tw + 96, top + 100), radius=50, fill=colors["accent"])
    d.text((PAD + 48, top + 50), cta["action"], font=pill_f, fill=colors["background"], anchor="lm")
    chrome(d, colors, handle, total, total)
    return img


def render_post(post, cfg, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    colors, handle = cfg["brand"]["colors"], cfg["brand"]["handle"]
    total = len(post["slides"]) + 2
    images = [cover_slide(post, colors, handle, total)]
    for i, s in enumerate(post["slides"], start=1):
        images.append(content_slide(s, i, colors, handle, i + 1, total))
    images.append(cta_slide(cfg["cta"], colors, handle, total))
    paths = []
    for i, img in enumerate(images, start=1):
        p = out_dir / f"slide_{i:02d}.jpg"
        img.save(p, "JPEG", quality=92)
        paths.append(p)
    return paths
