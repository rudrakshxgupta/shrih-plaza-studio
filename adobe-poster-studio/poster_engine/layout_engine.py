"""Layout engine: a brand-new premium poster template every time.

Owner rule (2026-09-26): an approved design is a quality bar, never a template,
and every post gets a new template. Each poster is composed from independent
design choices (composition, photo and crop, type pairing, frame, fact boxes,
call to action, palette). Every design is recorded, and a new one must differ
from all earlier designs in composition + photo, and from recent ones in most
choices, so no two posts share a template.
"""

import base64
import html as htmllib
import io
import random
from pathlib import Path
from typing import Any

from .design_history import load_history
from .paths import ASSETS_DIR

W, H = 1080, 1350
TYPEKIT = "https://use.typekit.net/ubj2uch.css"
P = "font-family:'poppins',sans-serif;"
F = "font-family:'playfair-display',serif;"

COMPOSITIONS = ["cinematic-bottom", "top-headline", "split-panel", "framed-card", "arch-window", "band-center"]
TYPES = ["playfair-italic-hero", "playfair-caps", "poppins-bold-hero", "poppins-light-tracked"]
FRAMES = ["gold-inset-corners", "double-rule", "corner-marks", "clean"]
FACTS = ["tiles", "diamond-row", "stacked-list"]
CTAS = ["split", "full-bar", "outline"]
PALETTES = {
    "navy": {"n": "#0B1237", "n2": "#1B2F62", "g": "#D7B469", "g2": "#F1D89A"},
    "emerald": {"n": "#0B2622", "n2": "#14453F", "g": "#D7B469", "g2": "#F1D89A"},
    "maroon": {"n": "#2E0A13", "n2": "#5E1626", "g": "#E3BE6F", "g2": "#F4DDA2"},
    "charcoal": {"n": "#111111", "n2": "#2A2A2A", "g": "#D7B469", "g2": "#F1D89A"},
    "plum": {"n": "#1F0E30", "n2": "#3F1D63", "g": "#E0BC6E", "g2": "#F2D99C"},
}
FACT_BANK = [
    ("RETAIL SHOPS", "Retail-ready frontage"), ("SCO SPACES", "Limited availability"),
    ("OFFICES", "Upper-level spaces"), ("CENTRAL PARKING", "Surface parking"),
    ("SH-11 HIGHWAY", "High visibility"), ("SIGNED BRANDS", "Food, retail, lifestyle"),
    ("RERA APPROVED", "Fully approved project"),
]
NOVELTY_MIN_DIFF = 4  # of the 7 choices, vs each of the last 10 designs


def photo_pool() -> list[Path]:
    renders = sorted((ASSETS_DIR / "renders").glob("ai-*.jpg"))
    originals = sorted((ASSETS_DIR / "original").glob("elevation-*.jpg"))
    return renders + originals


def _esc(text: str) -> str:
    return htmllib.escape(str(text), quote=True)


def _rgb(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    return f"{int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)}"


def _b64(image, fmt: str, **kw) -> str:
    buf = io.BytesIO()
    image.save(buf, fmt, **kw)
    return base64.b64encode(buf.getvalue()).decode()


def _cover(image, w: int, h: int, fx: float):
    from PIL import Image
    s = max(w / image.width, h / image.height)
    r = image.resize((max(w, round(image.width * s)), max(h, round(image.height * s))), Image.LANCZOS)
    left = round((r.width - w) * fx)
    top = round((r.height - h) * 0.5)
    return r.crop((left, top, left + w, top + h))


def _wrap(text: str, size: float, width: float, ratio: float) -> list[str]:
    per = max(6, int(width / (size * ratio)))
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if len(trial) <= per or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    return lines + ([cur] if cur else [])


def split_hook(hook: str) -> tuple[str, str]:
    words = hook.strip().rstrip(".").split()
    n = 2 if words and len(words[0]) <= 4 and len(words) > 2 else 1
    return " ".join(words[:n]), " ".join(words[n:])


def _diff(a: dict[str, str], b: dict[str, str]) -> int:
    return sum(1 for k in ("composition", "photo", "type", "frame", "facts", "cta", "palette") if a.get(k) != b.get(k))


def choose_spec(seed: int | None = None, avoid: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Pick a design never used before: new composition + photo pair, and far from recent designs."""
    rng = random.Random(seed)
    history = avoid if avoid is not None else [d for d in load_history() if d.get("composition")]
    used_pairs = {(d.get("composition"), d.get("photo")) for d in history}
    recent = history[-10:]
    photos = photo_pool()
    for _ in range(4000):
        photo = rng.choice(photos)
        spec = {
            "composition": rng.choice(COMPOSITIONS), "photo": photo.stem, "photo_path": str(photo),
            "focus": rng.choice([0.3, 0.5, 0.7]), "type": rng.choice(TYPES), "frame": rng.choice(FRAMES),
            "facts": rng.choice(FACTS), "cta": rng.choice(CTAS), "palette": rng.choice(list(PALETTES)),
            "fact_set": rng.sample(range(len(FACT_BANK)), 3),
        }
        if (spec["composition"], spec["photo"]) in used_pairs:
            continue
        if all(_diff(spec, d) >= NOVELTY_MIN_DIFF for d in recent):
            return spec
    raise RuntimeError("No new design combination left; add compositions or photos.")


class Poster:
    def __init__(self, spec: dict[str, Any], hook: str, support: str, phone: str, logo_path: Path):
        from PIL import Image
        self.s, self.pal = spec, PALETTES[spec["palette"]]
        self.hero, self.sub = split_hook(hook)
        self.support, self.phone = support, phone
        self.photo = Image.open(spec["photo_path"]).convert("RGB")
        logo = Image.open(logo_path).convert("RGBA")
        self.logo_img = logo
        self.parts: list[str] = []

    # ---------- primitives ----------
    def add(self, html: str) -> None:
        self.parts.append(html)

    def img(self, x, y, w, h, radius="0", border="", fx=None):
        pic = _cover(self.photo, w, h, self.s["focus"] if fx is None else fx)
        self.add(f'<img class="a" src="data:image/jpeg;base64,{_b64(pic, "JPEG", quality=84, optimize=True)}" '
                 f'style="left:{x}px;top:{y}px;width:{w}px;height:{h}px;border-radius:{radius};{border}" alt="Render of Shrih Plaza">')

    def box(self, x, y, w, h, style):
        self.add(f'<div class="a" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px;{style}"></div>')

    def text(self, x, y, w, content, style, align="left"):
        self.add(f'<p class="a" style="left:{x}px;top:{y}px;width:{w}px;text-align:{align};{style}">{content}</p>')

    def logo(self, x, y, w, center=False):
        from PIL import Image
        lg = self.logo_img.resize((w, round(w * self.logo_img.height / self.logo_img.width)), Image.LANCZOS)
        if center:
            x = (W - w) // 2
        self.add(f'<img class="a" src="data:image/png;base64,{_b64(lg, "PNG", optimize=True)}" '
                 f'style="left:{x}px;top:{y}px;width:{w}px;height:{lg.height}px" alt="Shrih Plaza logo">')
        return lg.height

    def seal(self, x, y, d=140):
        g, g2, n = self.pal["g"], self.pal["g2"], self.pal["n"]
        self.box(x, y, d, d, f"border-radius:{d // 2}px;border:2px solid {g};background:rgba({_rgb(n)},0.6)")
        self.box(x + 9, y + 9, d - 18, d - 18, f"border-radius:{(d - 18) // 2}px;border:1px solid rgba({_rgb(g)},0.55)")
        self.text(x, y + d * 0.28, d, "RERA", f"{P}font-weight:600;font-size:{max(18, round(d * 0.17))}px;line-height:1.1;letter-spacing:3px;color:{g2}", "center")
        self.box(x + d * 0.3, y + d * 0.5, d * 0.4, 1, f"background:{g}")
        self.text(x, y + d * 0.56, d, "APPROVED", f"{P}font-weight:500;font-size:{max(14, round(d * 0.105))}px;line-height:1.2;letter-spacing:3px;color:#FFFFFF", "center")

    def frame(self):
        g, st = self.pal["g"], self.s["frame"]
        if st in ("gold-inset-corners", "corner-marks"):
            if st == "gold-inset-corners":
                self.box(28, 28, W - 56, H - 56, f"border:1.5px solid rgba({_rgb(g)},0.7)")
            for (x, y) in [(20, 20), (W - 64, 20), (20, H - 23), (W - 64, H - 23)]:
                self.box(x, y, 44, 3, f"background:{g}")
            for (x, y) in [(20, 20), (W - 23, 20), (20, H - 64), (W - 23, H - 64)]:
                self.box(x, y, 3, 44, f"background:{g}")
        elif st == "double-rule":
            self.box(24, 24, W - 48, H - 48, f"border:2px solid {g}")
            self.box(36, 36, W - 72, H - 72, f"border:1px solid rgba({_rgb(g)},0.5)")

    def headline(self, x, y, w, align="left", scale=1.0) -> int:
        """Draw the hero word and subline; return the bottom y."""
        g, g2, t = self.pal["g"], self.pal["g2"], self.s["type"]
        hero, sub = self.hero, self.sub
        if t == "playfair-italic-hero":
            size = min(176 * scale, w / (max(len(hero), 4) * 0.52))
            self.text(x, y, w, _esc(hero), f"{F}font-style:italic;font-weight:700;font-size:{size:.0f}px;line-height:{size * 1.02:.0f}px;color:{g}", align)
            y += size * 1.02
            ssize = 46 * scale
            for line in _wrap(sub.upper(), ssize, w, 0.78)[:2]:
                self.text(x, y, w, _esc(line), f"{P}font-weight:300;font-size:{ssize:.0f}px;line-height:{ssize * 1.2:.0f}px;letter-spacing:9px;color:#FFFFFF", align)
                y += ssize * 1.2
        elif t == "playfair-caps":
            full = f"{hero} {sub}".upper()
            size = 92 * scale
            lines = _wrap(full, size, w, 0.66)
            while len(lines) > 3 and size > 50:
                size -= 6
                lines = _wrap(full, size, w, 0.66)
            for i, line in enumerate(lines[:3]):
                color = g if i == 0 else "#FFFFFF"
                self.text(x, y, w, _esc(line), f"{F}font-weight:400;font-size:{size:.0f}px;line-height:{size * 1.08:.0f}px;letter-spacing:2px;color:{color}", align)
                y += size * 1.08
        elif t == "poppins-bold-hero":
            size = min(150 * scale, w / (max(len(hero), 4) * 0.72))
            self.text(x, y, w, _esc(hero.upper()), f"{P}font-weight:600;font-size:{size:.0f}px;line-height:{size:.0f}px;letter-spacing:4px;color:{g}", align)
            y += size + 6
            ssize = 52 * scale
            for line in _wrap(sub.upper(), ssize, w, 0.7)[:2]:
                self.text(x, y, w, _esc(line), f"{P}font-weight:300;font-size:{ssize:.0f}px;line-height:{ssize * 1.2:.0f}px;letter-spacing:4px;color:#FFFFFF", align)
                y += ssize * 1.2
        else:  # poppins-light-tracked
            ssize = 36 * scale
            self.text(x, y, w, _esc(hero.upper()), f"{P}font-weight:600;font-size:{ssize * 1.1:.0f}px;line-height:{ssize * 1.5:.0f}px;letter-spacing:14px;color:{g2}", align)
            y += ssize * 1.6
            size = 84 * scale
            lines = _wrap(sub.upper() or hero.upper(), size, w, 0.74)
            while len(lines) > 2 and size > 48:
                size -= 6
                lines = _wrap(sub.upper() or hero.upper(), size, w, 0.74)
            for line in lines[:2]:
                self.text(x, y, w, _esc(line), f"{P}font-weight:300;font-size:{size:.0f}px;line-height:{size * 1.12:.0f}px;letter-spacing:6px;color:#FFFFFF", align)
                y += size * 1.12
        return int(y)

    def fit_block(self, x, y, w, align, scale, limit_y) -> int:
        """Headline plus support line, shrunk until the block ends 30px above limit_y."""
        while True:
            mark = len(self.parts)
            end = self.support_line(x, self.headline(x, y, w, align, scale) + 8, w, align)
            if end <= limit_y - 30 or scale <= 0.45:
                return end
            del self.parts[mark:]
            scale -= 0.06

    def support_line(self, x, y, w, align="left") -> int:
        if not self.support:
            return y
        self.text(x, y, w, _esc(self.support), f"{F}font-style:italic;font-weight:400;font-size:24px;line-height:32px;color:#E4E7F2", align)
        return y + 32 * len(_wrap(self.support, 24, w, 0.46))

    def facts_height(self) -> int:
        return {"tiles": 84, "diamond-row": 61, "stacked-list": 108}[self.s["facts"]]

    def facts_above(self, x, cta_y, w, min_y=0) -> int:
        """Place the fact boxes just above the call to action, never overlapping it."""
        return self.facts(x, max(min_y, cta_y - self.facts_height() - 26), w)

    def facts(self, x, y, w) -> int:
        g, st = self.pal["g"], self.s["facts"]
        items = [FACT_BANK[i] for i in self.s["fact_set"]]
        if st == "tiles":
            tw = (w - 32) // 3
            for i, (t, sub) in enumerate(items):
                tx = x + i * (tw + 16)
                self.box(tx, y, tw, 84, f"background:rgba(255,255,255,0.07);border:1px solid rgba({_rgb(g)},0.35)")
                self.box(tx, y, tw, 3, f"background:{g}")
                self.text(tx, y + 14, tw, _esc(t), f"{P}font-weight:600;font-size:18px;line-height:26px;letter-spacing:3px;color:#FFFFFF", "center")
                self.text(tx, y + 42, tw, _esc(sub), f"{P}font-weight:400;font-size:15px;line-height:22px;color:#C9CEE3", "center")
            return y + 84
        if st == "diamond-row":
            row = f" <span style='color:{g}'>&#9670;</span> ".join(_esc(t) for t, _ in items)
            self.box(x, y, w, 1, f"background:rgba({_rgb(g)},0.6)")
            self.text(x, y + 16, w, row, f"{P}font-weight:500;font-size:19px;line-height:28px;letter-spacing:3px;color:#FFFFFF", "center")
            self.box(x, y + 60, w, 1, f"background:rgba({_rgb(g)},0.6)")
            return y + 61
        for i, (t, sub) in enumerate(items):  # stacked-list
            ly = y + i * 36
            self.box(x, ly + 12, 10, 10, f"background:{g};transform:rotate(45deg)")
            self.text(x + 26, ly, w - 26, f"<b style='font-weight:600;letter-spacing:2px'>{_esc(t)}</b> &nbsp;<span style='color:#C9CEE3'>{_esc(sub)}</span>",
                      f"{P}font-weight:400;font-size:18px;line-height:34px;color:#FFFFFF")
        return y + 108

    def cta(self, x, y, w) -> int:
        g, g2, n, st = self.pal["g"], self.pal["g2"], self.pal["n"], self.s["cta"]
        if st == "split":
            lw = int(w * 0.57)
            self.box(x, y, lw, 80, f"background:{g}")
            self.text(x + 30, y + 14, lw - 40, "BOOK A SITE VISIT", f"{P}font-weight:600;font-size:24px;line-height:52px;letter-spacing:2px;color:{n}")
            self.box(x + lw, y, w - lw, 80, f"background:rgba({_rgb(n)},0.88);border:1.5px solid {g}")
            self.text(x + lw, y + 8, w - lw, "CALL", f"{P}font-weight:500;font-size:12px;line-height:16px;letter-spacing:4px;color:{g2}", "center")
            self.text(x + lw, y + 26, w - lw, _esc(self.phone), f"{P}font-weight:600;font-size:28px;line-height:40px;color:#FFFFFF", "center")
        elif st == "full-bar":
            self.box(x, y, w, 80, f"background:{g}")
            self.text(x + 32, y + 14, w * 0.5, "Book a site visit", f"{P}font-weight:600;font-size:28px;line-height:52px;color:{n}")
            self.text(x + w * 0.45, y + 14, w * 0.55 - 32, _esc(self.phone), f"{P}font-weight:600;font-size:32px;line-height:52px;color:{n}", "right")
        else:  # outline
            self.box(x, y, w, 80, f"border:2px solid {g};background:rgba({_rgb(n)},0.35)")
            self.text(x, y + 10, w, f"BOOK A SITE VISIT &nbsp;<span style='color:{g}'>|</span>&nbsp; {_esc(self.phone)}",
                      f"{P}font-weight:600;font-size:26px;line-height:60px;letter-spacing:2px;color:{g2}", "center")
        return y + 80

    def note(self, y=None, align="right", color="#AEB6D0"):
        self.text(66, H - 52 if y is None else y, W - 132, "Artist's impression.", f"{P}font-weight:400;font-size:14px;line-height:18px;color:{color}", align)

    # ---------- compositions ----------
    def build(self) -> str:
        getattr(self, "c_" + self.s["composition"].replace("-", "_"))()
        self.frame()
        n, n2 = self.pal["n"], self.pal["n2"]
        return ("<!DOCTYPE html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">\n"
                "<meta name=\"hz:slide-selector\" content=\".slide\">\n"
                f"<link rel=\"stylesheet\" href=\"{TYPEKIT}\">\n"
                f"<style>html,body{{margin:0;padding:0;background:{n}}}"
                f".slide{{position:relative;width:{W}px;height:{H}px;overflow:hidden;background:linear-gradient(180deg,{n2} 0%,{n} 100%)}}"
                ".a{position:absolute;margin:0}</style></head><body>\n"
                f"<div class=\"slide\" data-canvas-width=\"{W}\" data-canvas-height=\"{H}\">\n"
                + "\n".join(self.parts) + "\n</div></body></html>")

    def _shade(self, top, height, stops):
        rgb = _rgb(self.pal["n"])
        grad = ",".join(f"rgba({rgb},{a}) {p}%" for p, a in stops)
        self.box(0, top, W, height, f"background:linear-gradient(180deg,{grad})")

    def c_cinematic_bottom(self):
        mark = len(self.parts)
        block = self.headline(62, 0, 956)
        block = self.support_line(66, block + 10, 948)
        del self.parts[mark:]
        facts_y = 1200 - self.facts_height() - 26
        top = max(560, facts_y - 24 - block)
        self.img(0, 0, W, H)
        self._shade(0, 300, [(0, 0.88), (60, 0.45), (100, 0)])
        start = top - 200
        self._shade(start, H - start, [(0, 0), (28, 0.82), (50, 0.95), (100, 1)])
        self.logo(66, 60, 210)
        self.seal(W - 66 - 140, 62)
        y = self.headline(62, top, 956)
        self.support_line(66, y + 10, 948)
        self.facts(66, facts_y, 948)
        self.cta(66, 1200, 948)
        self.note()

    def c_top_headline(self):
        self.img(0, 0, W, H)
        self._shade(0, 760, [(0, 0.97), (55, 0.82), (100, 0)])
        self._shade(980, 370, [(0, 0), (45, 0.9), (100, 1)])
        self.logo(0, 56, 190, center=True)
        self.fit_block(80, 270, 920, "center", 0.92, 760)
        self.facts_above(66, 1206, 948)
        self.cta(66, 1206, 948)
        self.note(1296)

    def c_split_panel(self):
        pw = 560
        self.img(0, 0, pw, H)
        self.box(pw, 0, W - pw, H, f"background:linear-gradient(180deg,{self.pal['n2']} 0%,{self.pal['n']} 100%)")
        self.box(pw, 0, 4, H, f"background:{self.pal['g']}")
        self.logo(pw + 50, 70, 180)
        self.seal(W - 50 - 110, 70, 110)
        y = self.headline(pw + 50, 330, W - pw - 100, "left", 0.62)
        y = self.support_line(pw + 50, y + 16, W - pw - 100)
        if self.s["facts"] != "stacked-list":
            self.s = {**self.s, "facts": "stacked-list"}  # tiles and rows do not fit the narrow panel
        self.facts(pw + 50, min(max(y + 30, 800), 1100 - 108 - 40), W - pw - 100)
        self._cta_stack(pw + 50, 1100, W - pw - 100)
        self.note(H - 44, "right", "#AEB6D0")

    def _cta_stack(self, x, y, w):
        g, n = self.pal["g"], self.pal["n"]
        self.box(x, y, w, 70, f"background:{g}")
        self.text(x, y + 10, w, "BOOK A SITE VISIT", f"{P}font-weight:600;font-size:22px;line-height:50px;letter-spacing:2px;color:{n}", "center")
        self.text(x, y + 84, w, _esc(self.phone), f"{P}font-weight:600;font-size:30px;line-height:40px;color:#FFFFFF", "center")

    def c_framed_card(self):
        g = self.pal["g"]
        self.box(0, 0, W, H, f"background:radial-gradient(circle at 50% 30%,{self.pal['n2']} 0%,{self.pal['n']} 70%)")
        self.logo(0, 50, 170, center=True)
        self.box(76, 226, W - 152, 588, f"border:2px solid {g}")
        self.img(90, 240, W - 180, 560)
        self.seal(W - 90 - 120, 250, 120)
        self.fit_block(80, 850, 920, "center", 0.72, 1206 - self.facts_height() - 26)
        self.facts_above(66, 1206, 948)
        self.cta(66, 1206, 948)
        self.note(1296, "center")

    def c_arch_window(self):
        g = self.pal["g"]
        self.box(0, 0, W, H, f"background:linear-gradient(180deg,{self.pal['n2']} 0%,{self.pal['n']} 60%)")
        self.logo(66, 56, 170)
        self.seal(W - 66 - 120, 56, 120)
        aw, ah, ax, ay = 700, 660, 190, 170
        self.box(ax - 14, ay - 14, aw + 28, ah + 14, f"border:2px solid {g};border-bottom:0;border-radius:{(aw + 28) // 2}px {(aw + 28) // 2}px 0 0")
        self.img(ax, ay, aw, ah, radius=f"{aw // 2}px {aw // 2}px 0 0")
        self.box(ax - 60, ay + ah, aw + 120, 2, f"background:{g}")
        self.fit_block(80, ay + ah + 36, 920, "center", 0.7, 1206 - self.facts_height() - 26)
        self.facts_above(66, 1206, 948)
        self.cta(66, 1206, 948)
        self.note(1296, "center")

    def c_band_center(self):
        self.img(0, 0, W, H)
        self._shade(0, 380, [(0, 0.96), (60, 0.7), (100, 0)])
        self.box(0, 470, W, 470, f"background:rgba({_rgb(self.pal['n'])},0.82)")
        self.box(0, 470, W, 3, f"background:{self.pal['g']}")
        self.box(0, 937, W, 3, f"background:{self.pal['g']}")
        self.logo(0, 56, 200, center=True)
        self.fit_block(80, 520, 920, "center", 0.86, 940)
        self._shade(1000, 350, [(0, 0), (40, 0.9), (100, 1)])
        self.facts_above(66, 1204, 948)
        self.cta(66, 1204, 948)
        self.note(1294)


def compose(hook: str, support: str, phone: str, logo_path: Path, seed: int | None = None,
            spec: dict[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
    spec = spec or choose_spec(seed)
    return Poster(spec, hook, support, phone, logo_path).build(), spec
