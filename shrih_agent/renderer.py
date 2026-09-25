from __future__ import annotations

import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any

from .paths import ASSETS_DIR, OUTPUTS_DIR


CANVAS_SIZE = (1080, 1350)


def _hex(value: str, fallback: str) -> str:
    value = (value or "").strip()
    return value if value.startswith("#") and len(value) in {4, 7} else fallback


def _load_font(size: int, bold: bool = False):
    from PIL import ImageFont

    candidates = [
        "C:/Windows/Fonts/georgia.ttf",
        "C:/Windows/Fonts/georgiab.ttf" if bold else "C:/Windows/Fonts/georgia.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for path in candidates:
        if path and Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default(size=size)


def _wrap_text(draw, text: str, font, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        attempt = " ".join(current + [word])
        bbox = draw.textbbox((0, 0), attempt, font=font)
        if bbox[2] - bbox[0] <= max_width or not current:
            current.append(word)
        else:
            lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines


def _fit_cover(image, size: tuple[int, int]):
    from PIL import Image

    target_w, target_h = size
    image = image.convert("RGB")
    scale = max(target_w / image.width, target_h / image.height)
    resized = image.resize((int(image.width * scale), int(image.height * scale)), Image.Resampling.LANCZOS)
    left = (resized.width - target_w) // 2
    top = (resized.height - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


def _latest_original_image() -> Path | None:
    candidates: list[Path] = []
    for pattern in ["*.jpg", "*.jpeg", "*.png", "*.webp"]:
        candidates.extend((ASSETS_DIR / "original").glob(pattern))
    if not candidates:
        return None
    return sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)[0]


def render_instagram_post(
    content: dict[str, Any],
    brand: dict[str, Any],
    project: dict[str, Any],
    image_path: Path | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    try:
        from PIL import Image, ImageDraw, ImageEnhance
    except ImportError as exc:
        raise RuntimeError("Pillow is required. Install with: pip install -r requirements.txt") from exc

    colors = brand.get("colors", {})
    primary = _hex(colors.get("primary", ""), "#0F2E2B")
    gold = _hex(colors.get("secondary", ""), "#C8A24A")
    ivory = _hex(colors.get("neutral", ""), "#F7F3EA")
    ink = _hex(colors.get("ink", ""), "#171717")
    muted = _hex(colors.get("muted", ""), "#6B6B6B")

    canvas = Image.new("RGB", CANVAS_SIZE, ivory)
    draw = ImageDraw.Draw(canvas)

    image_path = image_path or _latest_original_image()
    if image_path and image_path.exists():
        hero = Image.open(image_path)
        hero = _fit_cover(hero, (1080, 760))
        hero = ImageEnhance.Contrast(hero).enhance(1.03)
        hero = ImageEnhance.Color(hero).enhance(1.02)
        canvas.paste(hero, (0, 0))
        draw.rectangle((0, 0, 1080, 760), outline=gold, width=0)
        source_note = str(image_path)
    else:
        draw.rectangle((0, 0, 1080, 760), fill=primary)
        source_note = "No image supplied. Used brand background placeholder."
        placeholder_font = _load_font(54, bold=True)
        draw.text((90, 315), "SHRIH PLAZA", fill=gold, font=placeholder_font)
        draw.line((90, 390, 420, 390), fill=gold, width=4)
        draw.text((90, 420), "Premium Commercial Destination", fill=ivory, font=_load_font(30))

    footer_top = 760
    draw.rectangle((0, footer_top, 1080, 1350), fill=ivory)
    draw.rectangle((0, footer_top, 1080, footer_top + 12), fill=gold)
    draw.rectangle((0, 1228, 1080, 1350), fill=primary)

    logo_font = _load_font(34, bold=True)
    small_font = _load_font(28)
    hook_font = _load_font(62, bold=True)
    caption_font = _load_font(30)
    cta_font = _load_font(34, bold=True)
    tiny_font = _load_font(24)

    draw.text((72, 812), "SHRIH PLAZA", fill=primary, font=logo_font)
    draw.text((72, 858), "RERA approved commercial project", fill=muted, font=small_font)

    hook = str(content.get("hook", "")).strip() or "Premium Commercial Spaces"
    y = 930
    for line in _wrap_text(draw, hook, hook_font, 900)[:3]:
        draw.text((72, y), line, fill=ink, font=hook_font)
        y += 72

    caption = str(content.get("caption", "")).strip()
    caption = caption.replace(str(content.get("cta", "")), "").strip()
    caption = caption[:185]
    y += 14
    for line in _wrap_text(draw, caption, caption_font, 920)[:3]:
        draw.text((72, y), line, fill=ink, font=caption_font)
        y += 42

    phone = project.get("contact", {}).get("phone", "")
    cta = str(content.get("cta", "Book a site visit"))
    draw.text((72, 1265), cta, fill=ivory, font=cta_font)
    if phone:
        bbox = draw.textbbox((0, 0), phone, font=cta_font)
        draw.text((1080 - 72 - (bbox[2] - bbox[0]), 1265), phone, fill=gold, font=cta_font)
    draw.text((72, 1315), "SH-11, Dhuri", fill="#D9CBA9", font=tiny_font)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_path or OUTPUTS_DIR / "final" / f"instagram_post_{timestamp}.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, quality=95)

    return {
        "created": True,
        "output": str(output_path),
        "size": CANVAS_SIZE,
        "source_image": source_note,
        "architecture_note": "If a source elevation image was used, it was only cropped to fit the post and lightly enhanced. No generative architecture edits were made.",
    }

