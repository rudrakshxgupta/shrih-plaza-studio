"""Design agent: builds a finished post from the brand kit and real assets.

Nothing here generates or edits the building. It composes the supplied real
renders, the original logo and the approved brand logos into an HTML layout,
then renders that HTML to a PNG with a headless browser.
"""

import base64
import io
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from . import mistake_memory
from .io import read_json
from .models import ContentDraft
from .paths import ASSETS_DIR, MEMORY_DIR, OUTPUTS_DIR

CANVAS = (1080, 1350)
LOGO_PATH = ASSETS_DIR / "original" / "logo-transparent.png"
BRAND_LOGO_DIR = ASSETS_DIR / "original" / "brands"
DEFAULT_SOURCE = ASSETS_DIR / "original" / "aerial-site-plan.jpg"
TYPEKIT_CSS = "https://use.typekit.net/nho3gjv.css"

# Order and display names follow memory/project_facts.json signed_brand_associations.
BRAND_LOGO_FILES = [
    ("dominos", "Domino's Pizza"),
    ("brew-estate", "The Brew Estate"),
    ("basant", "Basant Ice Cream & Dessert Bar"),
    ("vw-mart", "VW Mart 24x7 Cafe & Grocery Store"),
    ("octave", "Octave"),
    ("barista", "Barista"),
    ("sagar-ratna", "Sagar Ratna"),
    ("tress-lounge", "Tress Lounge Salon"),
    ("jockey", "Jockey"),
    ("elini", "Elini"),
    ("purple-kids", "Purple Kids"),
    ("baba-chicken", "Baba's Chicken"),
]

# The 3D elevation renders show shop signs for brands that are not approved,
# so they may not be used as the hero. The aerial is used with the north
# building masked or cropped out.
SIGNAGE_RISK_PREFIXES = ("elevation-",)

# Navy and gold is the default. The owner allows any colour, so every palette
# here keeps a dark ground, because the gold logo needs one to stay readable.
PALETTES = {
    "navy": {"n": "#0B1237", "n2": "#1B2F62", "g": "#D7B469", "g2": "#E6C877"},
    "emerald": {"n": "#0F2E2B", "n2": "#14453F", "g": "#D7B469", "g2": "#E6C877"},
    "maroon": {"n": "#3A0D18", "n2": "#5E1626", "g": "#E3BE6F", "g2": "#F0D28A"},
    "charcoal": {"n": "#141414", "n2": "#2A2A2A", "g": "#D7B469", "g2": "#E6C877"},
    "plum": {"n": "#26113A", "n2": "#3F1D63", "g": "#E0BC6E", "g2": "#EDD08A"},
}


def _rgb(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    return f"{int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)}"


CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def find_browser() -> str | None:
    override = os.getenv("SHRIH_BROWSER")
    if override and Path(override).exists():
        return override
    for candidate in CHROME_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome", "msedge"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _b64(image, fmt: str, **kwargs) -> str:
    buffer = io.BytesIO()
    image.save(buffer, fmt, **kwargs)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def cover_crop(image, width: int, height: int, anchor_x: float = 0.5, anchor_y: float = 0.5):
    """Scale to cover the target and crop inside the image, so it can never pad with black."""
    from PIL import Image

    scale = max(width / image.width, height / image.height)
    resized = image.resize((max(width, round(image.width * scale)), max(height, round(image.height * scale))), Image.LANCZOS)
    left = round((resized.width - width) * anchor_x)
    top = round((resized.height - height) * anchor_y)
    return resized.crop((left, top, left + width, top + height))


def _wrap(text: str, size: int, width: int = 952) -> list[str]:
    per_line = max(8, int(width / (size * 0.60)))
    lines: list[str] = []
    current = ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if len(trial) <= per_line or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class DesignAgent:
    def build(
        self,
        draft: ContentDraft,
        brand: dict[str, Any],
        project: dict[str, Any],
        layout: str = "hero",
        source_image: Path | None = None,
        safe_mode: bool = False,
        palette: str = "navy",
    ) -> dict[str, Any]:
        try:
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError("Pillow is required. Install with: pip install -r requirements.txt") from exc

        if layout not in {"hero", "tenants"}:
            raise ValueError("layout must be 'hero' or 'tenants'")

        source = source_image or DEFAULT_SOURCE
        if source.name.startswith(SIGNAGE_RISK_PREFIXES):
            return {"status": "blocked", "reason": f"{source.name} shows shop signs for brands that are not approved. Use the aerial render."}
        if not source.exists() or not LOGO_PATH.exists():
            return {"status": "blocked", "reason": "Source render or logo file is missing."}

        if palette not in PALETTES:
            return {"status": "blocked", "reason": f"Unknown palette '{palette}'. Choose from {sorted(PALETTES)}."}
        pal = PALETTES[palette]
        navy, navy2, gold, gold2 = pal["n"], pal["n2"], pal["g"], pal["g2"]
        self._rgb, self._gold2 = _rgb(navy), gold2
        phone = project.get("contact", {}).get("phone", "")

        logo = Image.open(LOGO_PATH).convert("RGBA")
        logo_w = 250 if layout == "hero" else 240
        logo = logo.resize((logo_w, round(logo_w * logo.height / logo.width)), Image.LANCZOS)
        logo_b64, logo_h = _b64(logo, "PNG", optimize=True), logo.height

        art = Image.open(source).convert("RGB")
        if layout == "hero":
            hero = cover_crop(art, 1080, 1350, anchor_x=0.45 if not safe_mode else 0.5, anchor_y=0.5)
            body = self._hero_html(draft, hero, logo_b64, logo_h, phone, navy, navy2, gold)
            signage = "north building darkened by top gradient"
        else:
            photo = cover_crop(art, 952, 398, anchor_x=0.5, anchor_y=0.85)
            body = self._tenants_html(draft, photo, logo_b64, logo_h, phone, navy, navy2, gold)
            signage = "north building cropped out"

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = OUTPUTS_DIR / "design"
        out_dir.mkdir(parents=True, exist_ok=True)
        html_path = out_dir / f"post_{layout}_{stamp}.html"
        png_path = out_dir / f"post_{layout}_{stamp}.png"
        html_path.write_text(body, encoding="utf-8")

        render = self.render_png(html_path, png_path)
        return {
            "status": "built" if render["ok"] else "render_failed",
            "layout": layout,
            "html": str(html_path),
            "png": str(png_path) if render["ok"] else None,
            "source_image": str(source),
            "signage_handling": signage,
            "safe_mode": safe_mode,
            "palette": palette,
            "render": render,
            "known_mistakes_applied": mistake_memory.avoid_instructions(),
        }

    def render_png(self, html_path: Path, png_path: Path) -> dict[str, Any]:
        browser = find_browser()
        if not browser:
            return {"ok": False, "error": "No Chrome or Edge found. Set SHRIH_BROWSER to a browser path."}
        command = [
            browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
            *(["--no-sandbox"] if os.name != "nt" else []),
            f"--window-size={CANVAS[0]},{CANVAS[1]}", "--virtual-time-budget=6000",
            f"--screenshot={png_path}", html_path.resolve().as_uri(),
        ]
        try:
            subprocess.run(command, capture_output=True, timeout=90, check=False)
        except (subprocess.TimeoutExpired, OSError) as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": png_path.exists(), "browser": Path(browser).name, "error": None if png_path.exists() else "browser produced no file"}

    def _head(self, navy: str, navy2: str) -> str:
        return (
            '<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8">\n'
            '<meta name="hz:slide-selector" content=".slide">\n'
            f'<link rel="stylesheet" href="{TYPEKIT_CSS}">\n'
            f"<style>html,body{{margin:0;padding:0;background:{navy}}}"
            f".slide{{position:relative;width:1080px;height:1350px;overflow:hidden;background:linear-gradient(180deg,{navy2} 0%,{navy} 100%)}}"
            ".abs{position:absolute;margin:0}</style></head><body>\n"
            '<div class="slide" data-canvas-width="1080" data-canvas-height="1350">\n'
        )

    def _cta(self, phone: str, cta: str, navy: str, gold: str, top: int = 1186, height: int = 100) -> str:
        p = "font-family:'poppins',sans-serif;"
        return (
            f'<div class="abs" style="left:64px;top:{top}px;width:952px;height:{height}px;background:{gold}"></div>\n'
            f'<p class="abs" style="left:96px;top:{top + 20}px;width:420px;{p}font-weight:600;font-size:30px;line-height:60px;color:{navy}">{_esc(cta)}</p>\n'
            f'<p class="abs" style="left:500px;top:{top + 20}px;width:484px;text-align:right;{p}font-weight:600;font-size:34px;line-height:60px;color:{navy}">{_esc(phone)}</p>\n'
        )

    def _headline_lines(self, draft: ContentDraft) -> tuple[list[str], int]:
        text = draft.hook.strip().rstrip(".").upper()
        if "LIMITED SCO" in text:
            text = "LIMITED SCO SPACES AVAILABLE"
        size = 96 if len(text) <= 30 else 72 if len(text) <= 46 else 56
        return _wrap(text, size)[:3], size

    def _hero_html(self, draft, hero, logo_b64, logo_h, phone, navy, navy2, gold) -> str:
        p = "font-family:'poppins',sans-serif;"
        lines, size = self._headline_lines(draft)
        line_h = size + 8
        head_top = 818
        head = "<br>".join(_esc(line) for line in lines)
        last = lines[-1].split()
        if last:
            prefix = " ".join(lines[-1].split()[:-1])
            head = "<br>".join(_esc(x) for x in lines[:-1])
            head += ("<br>" if lines[:-1] else "") + (_esc(prefix) + " " if prefix else "") + f'<span style="color:{gold};font-weight:400">{_esc(last[-1])}</span>'
        support_top = head_top + line_h * len(lines) + 24
        support = "Premium commercial spaces on SH-11, Dhuri.<br>Retail shops, SCO spaces and offices with central parking."
        return (
            self._head(navy, navy2)
            + f'<img class="abs" src="data:image/jpeg;base64,{_b64(hero, "JPEG", quality=84, optimize=True)}" style="left:0;top:0;width:1080px;height:1350px" alt="Aerial render of Shrih Plaza">\n'
            + f'<div class="abs" style="left:0;top:0;width:1080px;height:440px;background:linear-gradient(180deg,rgba({self._rgb},0.97) 0%,rgba({self._rgb},0.86) 55%,rgba({self._rgb},0) 100%)"></div>\n'
            + f'<div class="abs" style="left:0;top:520px;width:1080px;height:830px;background:linear-gradient(180deg,rgba({self._rgb},0) 0%,rgba({self._rgb},0.72) 24%,rgba({self._rgb},0.95) 44%,{navy} 100%)"></div>\n'
            + f'<img class="abs" src="data:image/png;base64,{logo_b64}" style="left:64px;top:54px;width:250px;height:{logo_h}px" alt="Shrih Plaza logo">\n'
            + f'<p class="abs" style="left:600px;top:84px;width:416px;text-align:right;{p}font-weight:400;font-size:20px;line-height:30px;letter-spacing:4px;color:#FFFFFF">RERA APPROVED<br>FULLY APPROVED PROJECT</p>\n'
            + f'<div class="abs" style="left:64px;top:{head_top - 83}px;width:96px;height:4px;background:{gold}"></div>\n'
            + f'<p class="abs" style="left:64px;top:{head_top - 54}px;width:952px;{p}font-weight:500;font-size:24px;line-height:32px;letter-spacing:6px;color:{self._gold2}">CONSTRUCTION NEARING COMPLETION</p>\n'
            + f'<p class="abs" style="left:64px;top:{head_top}px;width:952px;{p}font-weight:300;font-size:{size}px;line-height:{line_h}px;color:#FFFFFF">{head}</p>\n'
            + f'<p class="abs" style="left:64px;top:{support_top}px;width:952px;{p}font-weight:400;font-size:28px;line-height:40px;color:#E7EAF5">{support}</p>\n'
            + f'<p class="abs" style="left:64px;top:1150px;width:952px;text-align:right;{p}font-weight:400;font-size:15px;color:#AEB6D0">Artist\'s impression.</p>\n'
            + self._cta(phone, draft.cta or "Book a site visit", navy, gold)
            + "</div></body></html>"
        )

    def _tenants_html(self, draft, photo, logo_b64, logo_h, phone, navy, navy2, gold) -> str:
        from PIL import Image

        p = "font-family:'poppins',sans-serif;"
        tiles = ""
        tile_w, tile_h, gap = 148, 84, 12
        for index, (key, name) in enumerate(BRAND_LOGO_FILES):
            path = BRAND_LOGO_DIR / f"{key}.png"
            if not path.exists():
                continue
            logo = Image.open(path).convert("RGBA")
            flat = Image.new("RGBA", logo.size, (255, 255, 255, 255))
            flat.alpha_composite(logo)
            tile = flat.convert("RGB").resize((296, 155), Image.LANCZOS)
            x = 64 + (index % 6) * (tile_w + gap) + (952 - (6 * tile_w + 5 * gap)) // 2
            y = 950 + (index // 6) * (tile_h + gap)
            tiles += f'<img class="abs" src="data:image/jpeg;base64,{_b64(tile, "JPEG", quality=85, optimize=True)}" style="left:{x}px;top:{y}px;width:{tile_w}px;height:{tile_h}px;object-fit:cover" alt="{_esc(name)}">\n'
        lines, _ = self._headline_lines(draft)
        headline = "WHERE RETAIL, FOOD<br>&amp; BUSINESS MEET"
        return (
            self._head(navy, navy2)
            + f'<img class="abs" src="data:image/png;base64,{logo_b64}" style="left:64px;top:36px;width:240px;height:{logo_h}px" alt="Shrih Plaza logo">\n'
            + f'<p class="abs" style="left:600px;top:70px;width:416px;text-align:right;{p}font-weight:400;font-size:20px;line-height:30px;letter-spacing:3px;color:#FFFFFF">RERA APPROVED<br>FULLY APPROVED PROJECT</p>\n'
            + f'<div class="abs" style="left:64px;top:198px;width:952px;height:2px;background:{gold}"></div>\n'
            + f'<img class="abs" src="data:image/jpeg;base64,{_b64(photo, "JPEG", quality=80, optimize=True)}" style="left:64px;top:216px;width:952px;height:398px;border:3px solid {gold}" alt="Aerial render of Shrih Plaza">\n'
            + f'<p class="abs" style="left:64px;top:622px;width:952px;text-align:right;{p}font-weight:400;font-size:16px;color:#C5CBE0">Artist\'s impression.</p>\n'
            + f'<p class="abs" style="left:64px;top:660px;width:952px;{p}font-weight:300;font-size:56px;line-height:66px;color:{gold}">{headline}</p>\n'
            + f'<div class="abs" style="left:64px;top:806px;width:560px;height:52px;background:{gold}"></div>\n'
            + f'<p class="abs" style="left:64px;top:806px;width:560px;text-align:center;{p}font-weight:600;font-size:22px;line-height:52px;letter-spacing:2px;color:{navy}">LIMITED SCO SPACES AVAILABLE</p>\n'
            + f'<p class="abs" style="left:64px;top:874px;width:952px;{p}font-weight:400;font-size:24px;line-height:32px;color:#FFFFFF">Construction nearing completion. Signed brand associations across food, retail, lifestyle and daily convenience.</p>\n'
            + tiles
            + self._cta(phone, draft.cta or "Book a site visit", navy, gold, top=1180, height=104)
            + "</div></body></html>"
        )
