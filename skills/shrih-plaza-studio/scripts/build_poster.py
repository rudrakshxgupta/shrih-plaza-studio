"""Build an Adobe-Express-ready Instagram poster (1080x1350) to the owner's
Premium Poster Standard (brand kit, approved 2026-09-26).

Usage:  python build_poster.py spec.json out.html

Spec (JSON):
  layout      "hero" (default) | "brands"
  palette     "navy" (default) | "maroon" | "emerald"   (all keep the dark ground the gold logo needs)
  photo       file name or absolute path. Looked up in: absolute path, skill assets/photos/,
              repo assets/original/golden/, repo assets/original/
  focus_x/y   0..1 point of interest in the SOURCE photo to centre on (default 0.5 / 0.5)
  zoom        >= 1, zoom into the point of interest (e.g. 1.8 to feature one signboard)
  graded      true if the photo is already colour-graded (skip sharpen/contrast)
  verified    path to the architecture guard's JSON for an enhanced photo (required for enhanced photos)
  props       festival/decor layers placed IN FRONT of the building, never painted into it:
              [{"src": "/path/cutout.png" | "url": "https://...", "x": 0..1, "y": 0..1, "w": 0..1}]
              x/y = top-left, w = width, all as fractions of the 1080x1350 canvas
  kicker      spaced line above the hero word, e.g. "SH-11 · DHURI · PUNJAB"
  hero_word   ONE word, Playfair Display Bold Italic, gold (e.g. "Limited")
  subheadline Poppins Light, wide tracking, uppercase (e.g. "SCO spaces available")
  support     one italic Playfair line (e.g. "Construction nearing completion on SH-11, Dhuri.")
  facts       up to 3 {"title": "...", "line": "..."} panels
  brands      brand file stems in repo assets/original/brands (brands layout)
  badge       true -> RERA APPROVED / FULLY APPROVED seal (only while project_facts allows it)
  cta         default "BOOK A SITE VISIT"
  phone       from project_facts contact
  disclaimer  default "Artist's impression."
"""

import base64
import html
import io
import json
import os
import sys
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter

REPO = Path(os.environ.get("SHRIH_REPO", "/home/claude/shrih-plaza-studio"))
SKILL = Path(__file__).resolve().parents[1]
ASSETS = REPO / "assets" / "original"
W, H = 1080, 1350
TYPEKIT = "https://use.typekit.net/ubj2uch.css"  # owner's Adobe Fonts kit: Poppins + Playfair Display
P = "font-family:'poppins',sans-serif;"
PF = "font-family:'playfair-display',serif;font-style:italic;"
FLAT_AERIAL = ("aerial-site-plan",)
LOWRES = [0]  # set when the photo had to be upscaled a lot

PALETTES = {
    "navy": {"n": "#0B1237", "deep": "8,12,38", "soft": "#E4E7F2", "sub": "#C9CEE3", "mute": "#AEB6D0"},
    "maroon": {"n": "#3A0D16", "deep": "30,6,12", "soft": "#F2E4E7", "sub": "#E3C9CE", "mute": "#C4A9AE"},
    "emerald": {"n": "#0B2A24", "deep": "6,26,22", "soft": "#E1F0EB", "sub": "#C2DAD2", "mute": "#A3C0B8"},
}
G, G2 = "#D7B469", "#F1D89A"


def esc(s):
    return html.escape(str(s or ""))


def b64(img, fmt, **kw):
    buf = io.BytesIO()
    img.save(buf, fmt, **kw)
    return base64.b64encode(buf.getvalue()).decode()


def find_photo(name):
    p = Path(name)
    for cand in ([p] if p.is_absolute() else []) + [SKILL / "assets/photos" / name, ASSETS / "golden" / name, ASSETS / name]:
        if cand.exists():
            return cand
    sys.exit(f"Photo not found: {name}")


def load_photo(spec, w, h):
    path = find_photo(spec["photo"])
    # Owner 2026-09-27: render signage is fine as-is. Enhanced photos must carry a passing guard report.
    if path.with_suffix(".edits.json").exists():
        rep = spec.get("verified")
        if not rep or not Path(rep).exists() or not json.loads(Path(rep).read_text()).get("pass"):
            sys.exit(f"BLOCKED: {path.name} is an enhanced photo without a passing architecture check. "
                     "Run verify_architecture.py and pass its JSON as 'verified'.")
    if path.name.startswith(FLAT_AERIAL):
        print("WARNING: the premium standard says never the flat aerial on its own.", file=sys.stderr)
    src = Image.open(path).convert("RGB")
    s = max(w / src.width, h / src.height) * max(1.0, float(spec.get("zoom", 1.0)))
    LOWRES[0] = round(s * (W / w if w < W else 1), 2) if s > 2.4 else 0
    img = src.resize((round(src.width * s), round(src.height * s)), Image.LANCZOS)
    cx, cy = spec.get("focus_x", 0.5) * img.width, spec.get("focus_y", 0.5) * img.height
    x0 = int(min(max(cx - w / 2, 0), img.width - w))
    y0 = int(min(max(cy - h / 2, 0), img.height - h))
    img = img.crop((x0, y0, x0 + w, y0 + h))
    if not spec.get("graded"):
        img = img.filter(ImageFilter.UnsharpMask(radius=1.4, percent=90, threshold=3))
        img = ImageEnhance.Contrast(img).enhance(1.06)
        img = ImageEnhance.Color(img).enhance(1.08)
    return b64(img, "JPEG", quality=86, optimize=True)


def load_logo(width):
    logo = Image.open(ASSETS / "logo-transparent.png").convert("RGBA")
    logo = logo.crop(logo.getbbox() or (0, 0, logo.width, logo.height))
    h = round(width * logo.height / logo.width)
    return b64(logo.resize((width, h), Image.LANCZOS), "PNG", optimize=True), h


def open_doc(pal):
    return (
        '<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8">\n'
        '<meta name="hz:slide-selector" content=".slide">\n'
        f'<link rel="stylesheet" href="{TYPEKIT}">\n'
        f"<style>html,body{{margin:0;padding:0;background:{pal['n']}}}\n"
        f".slide{{position:relative;width:{W}px;height:{H}px;overflow:hidden;background:{pal['n']}}}\n"
        ".a{position:absolute;margin:0;white-space:nowrap}</style></head><body>\n"
        f'<div class="slide" data-canvas-width="{W}" data-canvas-height="{H}">'
    )


def frame():
    out = ['<div class="a" style="left:28px;top:28px;width:1024px;height:1294px;border:1.5px solid rgba(215,180,105,0.75)"></div>']
    for x, y, vx, vy in [(20, 20, 20, 20), (1016, 20, 1057, 20), (20, 1327, 20, 1286), (1016, 1327, 1057, 1286)]:
        out.append(f'<div class="a" style="left:{x}px;top:{y}px;width:44px;height:3px;background:{G}"></div>'
                   f'<div class="a" style="left:{vx}px;top:{vy}px;width:3px;height:44px;background:{G}"></div>')
    return "\n".join(out)


def seal(pal):
    return f"""<div class="a" style="left:862px;top:58px;width:150px;height:150px;border-radius:75px;border:2px solid {G};background:rgba({pal['deep']},0.55)"></div>
<div class="a" style="left:872px;top:68px;width:130px;height:130px;border-radius:65px;border:1px solid rgba(215,180,105,0.55)"></div>
<p class="a" style="left:862px;top:92px;width:150px;text-align:center;{P}font-weight:600;font-size:22px;line-height:26px;letter-spacing:3px;color:{G2}">RERA</p>
<p class="a" style="left:862px;top:120px;width:150px;text-align:center;{P}font-weight:500;font-size:14px;line-height:18px;letter-spacing:3px;color:#FFFFFF">APPROVED</p>
<div class="a" style="left:912px;top:146px;width:50px;height:1px;background:{G}"></div>
<p class="a" style="left:862px;top:153px;width:150px;text-align:center;{P}font-weight:400;font-size:11px;line-height:14px;letter-spacing:2px;color:{pal['soft']}">FULLY APPROVED</p>"""


def kicker(text, top):
    return (f'<div class="a" style="left:66px;top:{top+14}px;width:60px;height:1px;background:{G}"></div>\n'
            f'<p class="a" style="left:140px;top:{top}px;width:874px;{P}font-weight:500;font-size:19px;line-height:28px;letter-spacing:8px;color:{G2}">{esc(text).upper()}</p>') if text else ""


def hero_word(word, top, max_size=176):
    # Playfair Bold Italic ~0.52em per char; the preview check confirms the real fit
    size = int(min(max_size, 960 / max(len(word) * 0.52, 1)))
    return size, f'<p class="a" style="left:56px;top:{top}px;width:980px;{PF}font-weight:700;font-size:{size}px;line-height:{size+4}px;color:{G}">{esc(word)}</p>'


def sub_line(text, top, max_size=50):
    t = esc(text).upper()
    size = int(min(max_size, 948 / max(len(t) * 0.62 + len(t) * 10 / max_size, 1)))
    return f'<p class="a" style="left:66px;top:{top}px;width:948px;{P}font-weight:300;font-size:{size}px;line-height:{size+8}px;letter-spacing:10px;color:#FFFFFF">{t}</p>'


def support(text, top, pal):
    return f'<p class="a" style="left:66px;top:{top}px;width:948px;{PF}font-weight:400;font-size:24px;line-height:32px;color:{pal["soft"]}">{esc(text)}</p>' if text else ""


def fact_panels(facts, top, pal):
    facts = (facts or [])[:3]
    if not facts:
        return ""
    gap, total = 18, 948
    cw = (total - gap * (len(facts) - 1)) // len(facts)
    out = []
    for i, f in enumerate(facts):
        x = 66 + i * (cw + gap)
        out.append(f'<div class="a" style="left:{x}px;top:{top}px;width:{cw}px;height:84px;background:rgba(255,255,255,0.07);border:1px solid rgba(215,180,105,0.35)"></div>'
                   f'<div class="a" style="left:{x}px;top:{top}px;width:{cw}px;height:3px;background:{G}"></div>'
                   f'<p class="a" style="left:{x}px;top:{top+14}px;width:{cw}px;text-align:center;{P}font-weight:600;font-size:19px;line-height:26px;letter-spacing:3px;color:#FFFFFF">{esc(f.get("title")).upper()}</p>'
                   f'<p class="a" style="left:{x}px;top:{top+42}px;width:{cw}px;text-align:center;{P}font-weight:400;font-size:15px;line-height:22px;letter-spacing:1px;color:{pal["sub"]}">{esc(f.get("line"))}</p>')
    return "\n".join(out)


def props_layers(spec):
    """Festival props as separate layers (editable in Express). Local PNGs are inlined."""
    out = []
    for i, pr in enumerate(spec.get("props") or []):
        x, y, wd = int(pr["x"] * W), int(pr["y"] * H), int(pr["w"] * W)
        if pr.get("src"):
            im = Image.open(pr["src"]).convert("RGBA")
            im = im.crop(im.getbbox() or (0, 0, im.width, im.height))
            hd = round(wd * im.height / im.width)
            src = "data:image/png;base64," + b64(im.resize((wd, hd), Image.LANCZOS), "PNG", optimize=True)
        else:
            hd = int(pr.get("h", pr["w"]) * H)
            src = esc(pr["url"])
        out.append(f'<img class="a" data-prop="{i}" src="{src}" style="left:{x}px;top:{y}px;width:{wd}px;height:{hd}px" alt="{esc(pr.get("alt", "festive decor"))}">')
    return "\n".join(out)


def split_cta(spec, pal, top=1204):
    cta, phone = esc(spec.get("cta") or "BOOK A SITE VISIT").upper(), esc(spec.get("phone", ""))
    return f"""<div class="a" style="left:66px;top:{top}px;width:560px;height:80px;background:{G}"></div>
<p class="a" style="left:98px;top:{top+14}px;width:520px;{P}font-weight:600;font-size:26px;line-height:52px;letter-spacing:2px;color:{pal['n']}">{cta}</p>
<div class="a" style="left:626px;top:{top}px;width:388px;height:80px;background:rgba({pal['deep']},0.85);border:1.5px solid {G}"></div>
<p class="a" style="left:626px;top:{top+8}px;width:388px;text-align:center;{P}font-weight:500;font-size:12px;line-height:16px;letter-spacing:4px;color:{G2}">CALL</p>
<p class="a" style="left:626px;top:{top+26}px;width:388px;text-align:center;{P}font-weight:600;font-size:30px;line-height:40px;color:#FFFFFF">{phone}</p>"""


def footer(spec, pal):
    d = esc(spec.get("disclaimer", "Artist's impression."))
    return f'<p class="a" style="left:66px;top:1296px;width:948px;text-align:right;{P}font-weight:400;font-size:14px;line-height:18px;color:{pal["mute"]}">{d}</p>' if d else ""


def hero(spec, pal):
    photo = load_photo(spec, W, H)
    logo, lh = load_logo(210)
    d = pal["deep"]
    size, word = hero_word(spec["hero_word"], 802)
    return "\n".join(x for x in [
        open_doc(pal),
        f'<img class="a" src="data:image/jpeg;base64,{photo}" style="left:0;top:0;width:{W}px;height:{H}px" alt="Shrih Plaza render">',
        f'<div class="a" style="left:0;top:0;width:{W}px;height:300px;background:linear-gradient(180deg,rgba({d},0.88) 0%,rgba({d},0.45) 60%,rgba({d},0) 100%)"></div>',
        f'<div class="a" style="left:0;top:600px;width:{W}px;height:750px;background:linear-gradient(180deg,rgba({d},0) 0%,rgba({d},0.72) 22%,rgba({d},0.93) 42%,rgb({d}) 100%)"></div>',
        props_layers(spec),
        frame(),
        f'<img class="a" src="data:image/png;base64,{logo}" style="left:66px;top:60px;width:210px;height:{lh}px" alt="Shrih Plaza logo">',
        seal(pal) if spec.get("badge") else "",
        kicker(spec.get("kicker"), 778),
        word,
        sub_line(spec.get("subheadline", ""), 986) if spec.get("subheadline") else "",
        support(spec.get("support"), 1050, pal),
        fact_panels(spec.get("facts"), 1102, pal),
        split_cta(spec, pal),
        footer(spec, pal),
        "</div></body></html>",
    ] if x)


def brands(spec, pal):
    ph = 640
    photo = load_photo(spec, W, ph)
    logo, lh = load_logo(190)
    d = pal["deep"]
    size, word = hero_word(spec["hero_word"], 548, max_size=130)
    y = 548 + size + 8
    parts = [
        open_doc(pal),
        f'<img class="a" src="data:image/jpeg;base64,{photo}" style="left:0;top:0;width:{W}px;height:{ph}px" alt="Shrih Plaza render">',
        f'<div class="a" style="left:0;top:0;width:{W}px;height:260px;background:linear-gradient(180deg,rgba({d},0.88) 0%,rgba({d},0) 100%)"></div>',
        f'<div class="a" style="left:0;top:340px;width:{W}px;height:{ph-338}px;background:linear-gradient(180deg,rgba({d},0) 0%,rgba({d},0.8) 55%,{pal["n"]} 100%)"></div>',
        props_layers(spec),
        frame(),
        f'<img class="a" src="data:image/png;base64,{logo}" style="left:66px;top:60px;width:190px;height:{lh}px" alt="Shrih Plaza logo">',
        seal(pal) if spec.get("badge") else "",
        kicker(spec.get("kicker"), 520),
        word,
    ]
    if spec.get("subheadline"):
        parts.append(sub_line(spec["subheadline"], y + 6, max_size=34))
        y += 58
    y += 40
    cols, cw, ch, gap = 4, 222, 100, 24
    names = (spec.get("brands") or [])[:12]
    for i, name in enumerate(names):
        r, c = divmod(i, cols)
        x, top = 66 + c * (cw + gap), y + r * (ch + gap)
        parts.append(f'<div class="a" style="left:{x}px;top:{top}px;width:{cw}px;height:{ch}px;background:#FFFFFF;border-top:3px solid {G}"></div>')
        f = ASSETS / "brands" / f"{name}.png"
        if f.exists():
            im = Image.open(f).convert("RGBA")
            im = im.crop(im.getbbox() or (0, 0, im.width, im.height))
            s = min((cw - 36) / im.width, (ch - 28) / im.height)
            iw, ih = max(1, round(im.width * s)), max(1, round(im.height * s))
            data = b64(im.resize((iw, ih), Image.LANCZOS), "PNG", optimize=True)
            parts.append(f'<img class="a" src="data:image/png;base64,{data}" style="left:{x+(cw-iw)//2}px;top:{top+3+(ch-3-ih)//2}px;width:{iw}px;height:{ih}px" alt="{esc(name)}">')
    parts += [split_cta(spec, pal), footer(spec, pal), "</div></body></html>"]
    return "\n".join(p for p in parts if p)


def main():
    spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    if len(str(spec.get("hero_word", "")).split()) != 1:
        sys.exit("hero_word must be exactly one word (premium standard).")
    pal = PALETTES.get(spec.get("palette", "navy"), PALETTES["navy"])
    doc = {"hero": hero, "brands": brands}[spec.get("layout", "hero")](spec, pal)
    if LOWRES[0]:
        doc = doc.replace('<div class="slide" ', f'<div class="slide" data-lowres="{LOWRES[0]}" ', 1)
    out = Path(sys.argv[2])
    out.write_text(doc, encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
