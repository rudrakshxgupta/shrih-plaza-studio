from pathlib import Path
from typing import Any


def enhance_image_safe(input_path: Path, output_path: Path) -> dict[str, Any]:
    try:
        from PIL import Image, ImageEnhance, ImageFilter
    except ImportError as exc:
        raise RuntimeError("Pillow is required. Install with: pip install -r requirements.txt") from exc

    image = Image.open(input_path).convert("RGB")
    original_size = image.size

    enhanced = image.filter(ImageFilter.UnsharpMask(radius=1.2, percent=115, threshold=4))
    enhanced = ImageEnhance.Contrast(enhanced).enhance(1.06)
    enhanced = ImageEnhance.Color(enhanced).enhance(1.04)
    enhanced = ImageEnhance.Brightness(enhanced).enhance(1.02)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    enhanced.save(output_path, quality=95)

    return {
        "input": str(input_path),
        "output": str(output_path),
        "original_size": original_size,
        "enhanced_size": enhanced.size,
        "architecture_policy": "Only pixel-level quality adjustments were applied. No generative edits, inpainting, resizing, cropping, facade changes, structural changes, window changes, balcony changes or floor-count changes were performed.",
        "manual_review_required": True,
    }

