"""Design rules agent: checks a design against the owner's review rules and fixes what it can.

Owner direction (2026-10-01): every change the owner asks for in a review is a standing
rule, and the next design must resolve it automatically, not wait to be told again.
The rules live in memory/owner_design_rules.json; each one that can be measured has a
check here (the "check" field of the rule names it). Checks that can fix themselves
return the fix (a logo shade, a palette, a safe text zone) instead of just complaining.

    python run_agent.py design-check --image assets/renders/ai-14.jpg --canvas 1080x1350 \
        --logo-bg "#006491" --logo-width 390 --text "30-190,204-460,1200-1300"
"""

import re
from pathlib import Path
from typing import Any

from .paths import ASSETS_DIR, ROOT

RENDER_META = ASSETS_DIR / "render_meta.json"

LOGO_SHADES = {
    "official": ASSETS_DIR / "original" / "logo-official.png",
    "deep": ASSETS_DIR / "original" / "logo-official-deep.png",
    "light": ASSETS_DIR / "original" / "logo-official-light.png",
    "rich": ASSETS_DIR / "original" / "logo-official-rich.png",
    "champagne": ASSETS_DIR / "original" / "logo-official-champagne.png",
}
MIN_LOGO_CONTRAST = 3.0
LOGO_WIDTH_SHARE = (0.36, 0.54)   # of canvas width, owner rule 2026-10-01


def _hex(rgb) -> str:
    return "#%02X%02X%02X" % tuple(int(round(c)) for c in rgb)


def _rgb(value) -> tuple[float, float, float]:
    if isinstance(value, str):
        v = value.lstrip("#")
        return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))
    return tuple(value)


def luminance(rgb) -> float:
    out = []
    for c in _rgb(rgb):
        c = c / 255.0
        out.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]


def contrast(a, b) -> float:
    la, lb = sorted([luminance(a), luminance(b)], reverse=True)
    return round((la + 0.05) / (lb + 0.05), 2)


def logo_colour(path: Path) -> tuple[float, float, float]:
    from PIL import Image
    im = Image.open(path).convert("RGBA")
    px = [p[:3] for p in im.getdata() if p[3] > 200]
    return tuple(sum(c) / len(px) for c in zip(*px))


def pick_logo_shade(background) -> dict[str, Any]:
    """Rule: the logo must not fade. Keep the official gold when it already reads (>= 3:1),
    otherwise use the shade of the same logo with the best contrast on this background."""
    colours = {name: logo_colour(path) for name, path in LOGO_SHADES.items() if path.exists()}
    scores = {name: contrast(c, background) for name, c in colours.items()}
    if scores.get("official", 0) >= MIN_LOGO_CONTRAST:
        name = "official"
    else:
        # Owner review (Domino's reel): a pale shade that passes on contrast still looks washed out.
        # Among the shades that pass, prefer the crisp, saturated one.
        def saturation(c):
            return (max(c) - min(c)) / max(c) if max(c) else 0
        passing = [n for n in scores if scores[n] >= MIN_LOGO_CONTRAST] or list(scores)
        name = max(passing, key=lambda n: scores[n] * (0.5 + saturation(colours[n])))
    return {"shade": name, "file": str(LOGO_SHADES[name]), "contrast": scores[name], "all": scores,
            "ok": scores[name] >= MIN_LOGO_CONTRAST}


def logo_legibility(logo_path: Path, background_region) -> dict[str, Any]:
    """Owner rule: the logo's text must be clearly readable. Compares every logo pixel with the
    exact background pixel behind it (not an average), so thin letters over a busy sky are caught.
    background_region: a PIL image the size the logo is drawn at, showing what sits behind it."""
    import numpy as np
    from PIL import Image
    bg = background_region.convert("RGB")
    logo = Image.open(logo_path).convert("RGBA").resize(bg.size, Image.LANCZOS)
    a = np.asarray(logo).astype(float)
    b = np.asarray(bg).astype(float)
    mask = a[..., 3] > 160
    def lum(x):
        x = x / 255.0
        x = np.where(x <= 0.03928, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)
        return 0.2126 * x[..., 0] + 0.7152 * x[..., 1] + 0.0722 * x[..., 2]
    la, lb = lum(a[..., :3][mask]), lum(b[mask])
    ratio = (np.maximum(la, lb) + 0.05) / (np.minimum(la, lb) + 0.05)
    p10, median = float(np.percentile(ratio, 10)), float(np.median(ratio))
    return {"ok": median >= MIN_LOGO_CONTRAST and p10 >= 2.5, "median": round(median, 2), "weakest_10pct": round(p10, 2)}


VARIANT_DIR = ASSETS_DIR / "original" / "logo-variants"


def logo_variant(dark_hex: str, light_hex: str) -> Path:
    """The official logo recoloured to any colour ramp (dark to light), keeping its gradient
    and soft edges. Owner rule: any logo colour may be used if it looks best on that content."""
    import numpy as np
    from PIL import Image
    VARIANT_DIR.mkdir(parents=True, exist_ok=True)
    out = VARIANT_DIR / f"logo-{dark_hex.strip('#').lower()}-{light_hex.strip('#').lower()}.png"
    if out.exists():
        return out
    src = np.asarray(Image.open(LOGO_SHADES["official"]).convert("RGBA")).astype(float)
    lum = 0.299 * src[..., 0] + 0.587 * src[..., 1] + 0.114 * src[..., 2]
    vis = src[..., 3] > 30
    lo, hi = np.percentile(lum[vis], 2), np.percentile(lum[vis], 98)
    t = np.clip((lum - lo) / (hi - lo), 0, 1)[..., None]
    d, l = np.array(_rgb(dark_hex), float), np.array(_rgb(light_hex), float)
    rgb = d + (l - d) * t
    Image.fromarray(np.dstack([rgb, src[..., 3]]).astype(np.uint8), "RGBA").save(out)
    return out


GOLD_FAMILY = ("official", "deep", "light", "rich", "champagne")


# Deep antique gold for pale day skies, where the brighter golds wash out.
ANTIQUE_GOLD = ("#3D2706", "#7A5210")


def best_logo_for_region(background_region, palette: list[tuple[str, str]] | None = None) -> dict[str, Any]:
    """Owner rule: the logo may take any colour that looks best on that content. Tries every
    gold shade, white, and logo versions in the piece's own palette colours (dark, light hex
    pairs), keeps the ones that stay legible pixel by pixel, and picks the best-looking:
    crisp (not washed out), and gold when gold reads as well, to keep the brand's identity."""
    candidates = {name: path for name, path in LOGO_SHADES.items() if path.exists()}
    candidates["white"] = logo_variant("#E9EEF6", "#FFFFFF")
    candidates["antique"] = logo_variant(*ANTIQUE_GOLD)
    for dark, light in palette or []:
        candidates[f"palette {dark}"] = logo_variant(dark, light)
    results = {}
    for name, path in candidates.items():
        r = logo_legibility(path, background_region)
        c = logo_colour(path)
        sat = (max(c) - min(c)) / max(c) if max(c) else 0
        identity = 0.6 if name in GOLD_FAMILY or name == "antique" else 0.0
        r["score"] = round(min(r["weakest_10pct"], 6) * (0.6 + 0.4 * sat) + identity, 2)
        r["file"] = str(path)
        results[name] = r
    for name, path in candidates.items():
        c = logo_colour(path)
        results[name]["saturation"] = round((max(c) - min(c)) / max(c), 2) if max(c) else 0
    passing = {n: r for n, r in results.items() if r["ok"]}
    # Owner rules: gold and its shades come first, and the gold must LOOK gold. Champagne and light gold
    # are so pale they read as cream/white (owner, courtyard story), so only vivid golds count first.
    vivid = [n for n in passing if n in GOLD_FAMILY and passing[n]["saturation"] >= 0.5]
    comfy_vivid = [n for n in vivid if passing[n]["weakest_10pct"] >= 3.0]
    antique_ok = "antique" in passing and passing["antique"]["weakest_10pct"] >= 3.0
    if comfy_vivid:
        best = max(comfy_vivid, key=lambda n: passing[n]["saturation"])
    elif antique_ok:
        # Pale day sky (owner, 12-brands post): a deep antique gold reads without darkening the sky.
        best = "antique"
    else:
        # No vivid gold reads here: deepen the sky behind the logo with a soft halo in the image's own
        # colour until rich gold reads, instead of settling for a pale shade.
        halo = _halo_for_gold(background_region, candidates.get("rich"))
        if halo:
            return {"shade": "rich", "file": str(candidates["rich"]), "ok": True, "halo": halo, "all": results}
        passing_gold = [n for n in passing if n in GOLD_FAMILY]
        if passing_gold:
            best = max(passing_gold, key=lambda n: passing[n]["weakest_10pct"])
        else:
            pool = passing or results
            best = max(pool, key=lambda n: pool[n]["score"])
    return {"shade": best, "file": results[best]["file"], "ok": results[best]["ok"], "all": results}


def _halo_for_gold(background_region, gold_path) -> dict[str, Any] | None:
    """Smallest sky deepening (the region's own colour, darkened, full width) that lets a vivid gold logo read
    comfortably. Returns the colour and centre opacity to use, or None if 0.7 is not enough."""
    import numpy as np
    from PIL import Image
    if gold_path is None:
        return None
    base = np.asarray(background_region.convert("RGB")).astype(float)
    colour = tuple(int(c * 0.3) for c in base.reshape(-1, 3).mean(axis=0))
    for alpha in (0.1, 0.2, 0.3, 0.35, 0.4, 0.5, 0.6, 0.7):
        region = Image.fromarray((base * (1 - alpha) + np.array(colour) * alpha).astype(np.uint8))
        r = logo_legibility(gold_path, region)
        if r["ok"] and r["weakest_10pct"] >= 3.0:
            # Owner review (Dusk Issue carousel): an oval halo reads as a separate patch. Deepen the sky
            # edge to edge instead, strongest at the top and fading out below the logo, like a real dusk sky.
            top = round(min(0.8, alpha + 0.15), 2)
            return {"colour": _hex(colour), "alpha": alpha,
                    "css": f"linear-gradient(180deg, rgba{colour + (top,)} 0%, rgba{colour + (alpha,)} 50%, "
                           f"rgba{colour + (round(alpha / 2, 2),)} 75%, rgba{colour + (0,)} 100%)",
                    "placement": "full width, from the top edge to about 1.5x the logo's bottom",
                    "contrast": r}
    return None


def image_sharpness(asset_path: Path, display_width: int) -> dict[str, Any]:
    """Owner rule: logos and brand marks must never look blurry. The source file needs at least
    1.5x the pixels it is shown at (phones have dense screens), measured on its visible content."""
    from PIL import Image
    im = Image.open(asset_path).convert("RGBA")
    box = im.getchannel("A").point(lambda v: 255 if v > 10 else 0).getbbox() or (0, 0, im.width, im.height)
    content_w = box[2] - box[0]
    ratio = content_w / display_width
    return {"ok": ratio >= 1.5, "source_px": content_w, "display_px": display_width, "ratio": round(ratio, 2),
            "fix": None if ratio >= 1.5 else "Rebuild the logo at high resolution in flat brand colours "
                                             "(8x upscale, smooth, snap to brand colours, downsample) or get a vector file."}


def logo_size(logo_width: int, canvas_width: int) -> dict[str, Any]:
    lo, hi = LOGO_WIDTH_SHARE
    share = logo_width / canvas_width
    fix = None if lo <= share <= hi else round(canvas_width * (lo + hi) / 2)
    return {"ok": fix is None, "share": round(share, 2), "fix_width": fix}


def palette_from_image(path: Path) -> dict[str, str]:
    """Rule: take the post's colours from its own image. Samples the sky from top to horizon
    and the facade, and derives a dark text colour and a warm accent from them."""
    from PIL import Image
    im = Image.open(path).convert("RGB").resize((120, 120))
    def band(y0, y1):
        px = [im.getpixel((x, y)) for y in range(y0, y1) for x in range(120)]
        return tuple(sum(c) / len(px) for c in zip(*px))
    top, mid, horizon, facade = band(0, 8), band(20, 30), band(38, 46), band(60, 75)
    dark = tuple(c * 0.35 for c in top)
    warm = max((top, mid, horizon, facade), key=lambda c: c[0] - c[2])
    return {"sky_top": _hex(top), "sky_mid": _hex(mid), "horizon": _hex(horizon), "facade": _hex(facade),
            "text_dark": _hex(dark), "accent_warm": _hex(warm)}


def roofline(path: Path, canvas_w: int, canvas_h: int, pos_y: float = 0.5, top: int = 0,
             height: int | None = None) -> int:
    """Where the building starts, in canvas px, for an image drawn with object-fit: cover.
    Buildings are full of sharp vertical lines (columns, window frames); skies and clouds
    are not. The first row band with dense vertical edges is taken as the roofline."""
    from PIL import Image
    im = Image.open(path).convert("L")
    h = height or canvas_h
    scale = max(canvas_w / im.width, h / im.height)
    offset = (im.height * scale - h) * pos_y
    small = im.resize((240, int(240 * im.height / im.width)))
    W, H = small.size
    px = small.load()
    rows = []
    for y in range(H):
        strong = sum(1 for x in range(1, W - 1) if abs(px[x + 1, y] - px[x - 1, y]) > 28)
        rows.append(strong / W)
    smooth = [sum(rows[max(0, y - 2):y + 3]) / len(rows[max(0, y - 2):y + 3]) for y in range(H)]
    for y in range(3, H):
        if smooth[y] > 0.12:
            return int(top + (y / H * im.height) * scale - offset)
    return int(top + h * 0.35)


def building_band(path: Path, canvas_w: int, canvas_h: int, pos_y: float = 0.5, top: int = 0,
                  height: int | None = None) -> dict[str, Any]:
    """Top and bottom of the building in canvas px. Uses the measured values in
    assets/render_meta.json when the image is listed; otherwise estimates the roofline
    from vertical edges and says so, so a person or Claude can measure and add it."""
    import json
    from PIL import Image
    h = height or canvas_h
    im = Image.open(path)
    scale = max(canvas_w / im.width, h / im.height)
    offset = (im.height * scale - h) * pos_y
    meta = json.loads(RENDER_META.read_text(encoding="utf-8")).get("images", {}) if RENDER_META.exists() else {}
    try:
        key = Path(path).resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        key = Path(path).name
    entry = meta.get(key) or next((v for k, v in meta.items() if Path(k).name == Path(path).name), None)
    if entry:
        to_canvas = lambda f: int(top + f * im.height * scale - offset)
        return {"top": to_canvas(entry["building_top"]), "bottom": to_canvas(entry["building_bottom"]), "measured": True}
    est = roofline(path, canvas_w, canvas_h, pos_y, top, height)
    return {"top": est, "bottom": int(est + h * 0.3), "measured": False,
            "note": "Estimated. Measure this image (Adobe sky mask) and add it to assets/render_meta.json."}


def text_clear_of_building(text_bands: list[tuple[int, int]], building_top: int, building_bottom: int) -> dict[str, Any]:
    """Rule: the building is the hero; no text block may overlap it."""
    clashes = [b for b in text_bands if b[0] < building_bottom and b[1] > building_top]
    return {"ok": not clashes, "clashes": clashes, "safe_sky": (0, building_top), "safe_foreground": (building_bottom, None)}


BANNED_DESIGN_TEXT = ["artist's impression", "artist&#39;s impression", "artists impression",
                      # owner (2026-10-02): a brand is never "coming", it is "opening soon"
                      "coming soon", "is coming", "are coming", "coming to shrih"]


def banned_text(html_or_text: str) -> dict[str, Any]:
    """Owner rule: some wording never goes on content (e.g. "Artist's impression")."""
    low = html_or_text.lower()
    found = [t for t in BANNED_DESIGN_TEXT if t in low]
    return {"ok": not found, "found": found}


TWELVE_BRANDS = re.compile(r"\b(12|twelve)\b[^.]{0,30}\bbrands?\b", re.I)


def all_brand_logos(design_text: str, brand_logos: list[str] | None) -> dict[str, Any]:
    """Owner rule (2026-10-01): content that talks about the 12 brands shows all 12 brand logos."""
    if not TWELVE_BRANDS.search(design_text):
        return {"ok": True, "mentions_12_brands": False}
    shown = len(set(brand_logos or []))
    return {"ok": shown >= 12, "mentions_12_brands": True, "logos_shown": shown,
            "fix": None if shown >= 12 else "show all 12 brand logos, or drop the 12-brands wording"}


PHONE = "+91 90564 53575"


def phone_font(html: str) -> dict[str, Any]:
    """Owner rule (2026-10-02): the phone number is always set in a clean sans-serif with lining
    figures, never a decorative serif (old-style serif numerals read badly)."""
    bad = []
    for m in re.finditer(r'<(?:div|span)[^>]*style="([^"]*)"[^>]*>\s*' + re.escape(PHONE), html):
        style = m.group(1)
        if re.search(r"font-family:[^;]*\bserif\b", style) and "sans-serif" not in style:
            bad.append(style)
    return {"ok": not bad, "serif_phone_styles": bad,
            "fix": None if not bad else "set the phone in the post's sans-serif, weight 600-700, lining-nums"}


def review(image: Path, canvas: tuple[int, int], logo_bg=None, logo_width: int | None = None,
           text_bands: list[tuple[int, int]] | None = None, building_bottom: int | None = None,
           image_top: int = 0, image_height: int | None = None, pos_y: float = 0.5,
           design_text: str | None = None, logo_file: Path | None = None,
           brand_logos: list[str] | None = None) -> dict[str, Any]:
    """Run every measurable owner rule on one design and return verdicts with fixes."""
    w, h = canvas
    report: dict[str, Any] = {"palette_from_image": palette_from_image(image)}
    band = building_band(image, w, h, pos_y, image_top, image_height)
    report["building"] = band
    if text_bands:
        report["text_off_building"] = text_clear_of_building(text_bands, band["top"], building_bottom or band["bottom"])
    if logo_bg is not None:
        report["logo_shade"] = pick_logo_shade(logo_bg)
        if logo_file is not None:
            # Judge the logo actually used (e.g. a palette or antique-gold variant), not only the stock shades.
            used = round(contrast(logo_colour(logo_file), logo_bg), 2)
            report["logo_shade"]["used_contrast"] = used
            report["logo_shade"]["ok"] = used >= MIN_LOGO_CONTRAST
    if logo_width:
        report["logo_size"] = logo_size(logo_width, w)
    if design_text is not None:
        report["banned_text"] = banned_text(design_text)
        report["all_brand_logos"] = all_brand_logos(design_text, brand_logos)
    if logo_file is not None and logo_width:
        report["logo_sharpness"] = image_sharpness(logo_file, logo_width)
    report["ok"] = all(v.get("ok", True) for v in report.values() if isinstance(v, dict))
    return report
