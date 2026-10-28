"""Turn a post (JSON) into branded 1080x1350 carousel slides or a single ad image (JPEG — Instagram's required format)."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350          # 4:5 portrait, the largest feed size Instagram allows
PAD = 96
ROOT = Path(__file__).resolve().parent.parent
FONTS, ASSETS = ROOT / "fonts", ROOT / "assets"
WHITE = "#FFFFFF"


def font(weight, size):
    return ImageFont.truetype(str(FONTS / f"Inter-{weight}.otf"), size)


def logo(name, width):
    img = Image.open(ASSETS / name).convert("RGBA")
    return img.resize((width, round(img.height * width / img.width)), Image.LANCZOS)


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
    scale = max(W / img.width, H / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    left = (img.width - W) // 2
    top = int((img.height - H) * 0.35)
    return img.crop((left, top, left + W, top + H))


def bottom_fade(color_hex, start, end, max_alpha=245):
    """Transparent → brand color gradient so white text stays readable over any image."""
    r, g, b = (int(color_hex[i:i + 2], 16) for i in (1, 3, 5))
    grad = Image.new("RGBA", (W, H), (r, g, b, 0))
    d = ImageDraw.Draw(grad)
    for y in range(start, H):
        a = max_alpha if y >= end else int(max_alpha * ((y - start) / (end - start)) ** 1.4)
        d.line((0, y, W, y), fill=(r, g, b, a))
    return grad


def art_background(c, art=None, fade_from=0.34, fade_to=0.64):
    """AI illustration with a navy fade at the bottom, or a plain branded backdrop if there's no art."""
    if art is not None:
        img = cover_fit(art).convert("RGBA")
        img.alpha_composite(bottom_fade(c["navy"], int(H * fade_from), int(H * fade_to)))
        return img.convert("RGB")
    img = Image.new("RGB", (W, H), c["navy"])
    deco = ImageDraw.Draw(img)
    deco.ellipse((W - 420, -260, W + 260, 420), fill=c["teal"])
    deco.ellipse((W - 355, 285, W - 285, 355), fill=c["amber"])
    return img


def cover_slide(post, c, website, total, cover_img=None):
    img = art_background(c, cover_img)
    d = ImageDraw.Draw(img, "RGBA")

    icon = logo("icon.png", 92)
    img.paste(icon, (PAD, PAD), icon)

    title_f, title_l, title_h = fit_text(d, post["cover"]["title"], "ExtraBold", 100, W - 2 * PAD, 480, 1.1)
    sub_f, sub_l, sub_h = fit_text(d, post["cover"]["subtitle"], "Medium", 42, W - 2 * PAD, 160, 1.3)
    y = H - 250 - sub_h - 36 - title_h
    d.rectangle((PAD, y - 44, PAD + 110, y - 34), fill=c["amber"])
    y = draw_block(d, (PAD, y), title_l, title_f, WHITE, 1.1)
    draw_block(d, (PAD, y + 36), sub_l, sub_f, WHITE + "D9", 1.3)
    d.text((W - PAD, H - 170), "Swipe  →", font=font("Bold", 38), fill=c["amber"], anchor="rs")
    chrome(d, c, website, 1, total, dark=True)
    return img


def content_slide(slide, num, c, brand, website, index, total):
    img = Image.new("RGB", (W, H), c["paper"])
    d = ImageDraw.Draw(img, "RGBA")
    icon = logo("icon.png", 56)
    img.paste(icon, (PAD, PAD), icon)
    d.text((PAD + 76, PAD + 28), brand, font=font("Bold", 30), fill=c["navy"], anchor="lm")

    d.text((PAD - 6, 300), f"{num:02d}", font=font("ExtraBold", 170), fill=c["teal"])
    head_f, head_l, _ = fit_text(d, slide["heading"], "ExtraBold", 78, W - 2 * PAD, 270, 1.15)
    y = draw_block(d, (PAD, 540), head_l, head_f, c["navy"], 1.15)
    d.rectangle((PAD, y + 30, PAD + 80, y + 38), fill=c["teal"])
    d.ellipse((PAD + 92, y + 28, PAD + 104, y + 40), fill=c["amber"])
    body_f, body_l, _ = fit_text(d, slide["body"], "Regular", 50, W - 2 * PAD, H - y - 300, 1.42)
    draw_block(d, (PAD, y + 82), body_l, body_f, c["navy"] + "E6", 1.42)
    chrome(d, c, website, index, total)
    return img


def cta_slide(cta, c, website, total):
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img, "RGBA")
    wordmark = logo("wordmark.png", 440)
    img.paste(wordmark, (PAD, 190), wordmark)

    head_f, head_l, _ = fit_text(d, cta["headline"], "ExtraBold", 86, W - 2 * PAD, 320, 1.12)
    y = draw_block(d, (PAD, 450), head_l, head_f, c["navy"], 1.12)
    body_f, body_l, _ = fit_text(d, cta["body"], "Regular", 44, W - 2 * PAD, 240, 1.4)
    y = draw_block(d, (PAD, y + 36), body_l, body_f, c["muted"], 1.4)

    button(d, c, cta["action"], y + 64)
    chrome(d, c, website, total, total)
    return img


def button(d, c, label, top):
    pill_f = font("Bold", 42)
    tw = d.textlength(label, font=pill_f)
    d.rounded_rectangle((PAD, top, PAD + tw + 150, top + 104), radius=52, fill=c["teal"])
    d.text((PAD + 52, top + 52), label, font=pill_f, fill=WHITE, anchor="lm")
    d.text((PAD + tw + 92, top + 52), "→", font=pill_f, fill=c["amber"], anchor="lm")
    return PAD + tw + 150


def ad_image(post, cfg, art=None):
    """Single-image ad: AI art up top, headline + 3 benefits + button over the navy fade."""
    c, website = cfg["brand"]["colors"], cfg["brand"]["website"]
    img = art_background(c, art, fade_from=0.26, fade_to=0.52)
    d = ImageDraw.Draw(img, "RGBA")
    icon = logo("icon.png", 92)
    img.paste(icon, (PAD, PAD), icon)

    max_w = W - 2 * PAD
    head_f, head_l, head_h = fit_text(d, post["headline"], "ExtraBold", 88, max_w, 300, 1.1)
    sub_f, sub_l, sub_h = fit_text(d, post["subhead"], "Medium", 40, max_w, 160, 1.32)
    point_f = font("SemiBold", 36)
    points_h = 58 * len(post["points"])
    btn_top = H - PAD - 104
    y = btn_top - 56 - points_h - 34 - sub_h - 30 - head_h

    y = draw_block(d, (PAD, y), head_l, head_f, WHITE, 1.1)
    y = draw_block(d, (PAD, y + 30), sub_l, sub_f, WHITE + "D9", 1.32) + 34
    for pt in post["points"]:
        cy = y + 22
        d.ellipse((PAD, cy - 15, PAD + 30, cy + 15), fill=c["amber"])
        d.line((PAD + 8, cy, PAD + 13, cy + 6, PAD + 22, cy - 6), fill=c["navy"], width=4, joint="curve")
        d.text((PAD + 50, cy), pt, font=point_f, fill=WHITE, anchor="lm")
        y += 58
    right = button(d, c, cfg["cta"]["action"], btn_top)
    d.text((right + 32, btn_top + 52), website, font=font("Medium", 32), fill=WHITE + "CC", anchor="lm")
    return img


def render_post(post, cfg, out_dir, cover_img=None):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if post["kind"] == "ad":
        p = out_dir / "ad.jpg"
        ad_image(post, cfg, cover_img).save(p, "JPEG", quality=92)
        return [p]
    c, brand, website = cfg["brand"]["colors"], cfg["brand"]["name"], cfg["brand"]["website"]
    total = len(post["slides"]) + 2
    images = [cover_slide(post, c, website, total, cover_img)]
    for i, s in enumerate(post["slides"], start=1):
        images.append(content_slide(s, i, c, brand, website, i + 1, total))
    images.append(cta_slide(cfg["cta"], c, website, total))
    paths = []
    for i, img in enumerate(images, start=1):
        p = out_dir / f"slide_{i:02d}.jpg"
        img.save(p, "JPEG", quality=92)
        paths.append(p)
    return paths
