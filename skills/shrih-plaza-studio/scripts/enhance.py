"""Image enhancement agent: re-light a REAL Shrih Plaza render without touching the architecture.

Usage:
  python enhance.py SOURCE OUT.jpg --look dusk|golden|night|day-clean
                    [--sky REAL_SKY_PHOTO] [--brand-signs signs.json]

Allowed changes (owner, 2026-09-27):
  * sky replaced (dusk / golden / night / clean day, or a real sky photo)
  * lighting and colour (evening grade, warm window glow, soft bloom)
  * a signed brand's logo placed on an existing signboard when the post is about that brand
Never changed: the position of any pixel of the building. Every edit is sky replacement,
a per-pixel tone change, or a declared signboard. verify_architecture.py proves it.

signs.json: [{"brand": "dominos", "quad": [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]}, ...]
  corners of the existing signboard (top-left, top-right, bottom-right, bottom-left) as
  fractions 0..1 of the image, picked by looking at the photo. Brand = file stem in
  repo assets/original/brands/ (one of the 12 signed brands only).
Writes OUT.jpg + OUT.sky.png + OUT.edits.json (read by the verifier).
"""
import argparse
import json
import os
from pathlib import Path

import cv2
import numpy as np
from scipy import ndimage as ndi

REPO = Path(os.environ.get("SHRIH_REPO", "/home/claude/shrih-plaza-studio"))
BRANDS = REPO / "assets" / "original" / "brands"


def sky_mask(img):
    """Sky = smooth region connected to the top edge whose colour matches the top strip."""
    h, w = img.shape[:2]
    blur = cv2.GaussianBlur(img, (5, 5), 0)
    lab = cv2.cvtColor(blur, cv2.COLOR_BGR2LAB).astype(np.float32)
    g = cv2.cvtColor(blur, cv2.COLOR_BGR2GRAY).astype(np.float32)
    gm = np.hypot(cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3))
    gm = cv2.GaussianBlur(gm, (9, 9), 0)
    ref = np.median(lab[: max(4, h // 40)].reshape(-1, 3), axis=0)
    dist = np.linalg.norm((lab - ref) * [0.5, 1, 1], axis=2)
    cand = (gm < 14) & (dist < 60)
    cand[:2] = True
    m = ndi.binary_opening(cand, iterations=2)
    lbl, _ = ndi.label(m)
    m = np.isin(lbl, list(set(np.unique(lbl[0])) - {0}))
    m = ndi.binary_fill_holes(m | np.pad(np.ones((1, w), bool), ((0, h - 1), (0, 0))))
    return m


def sky_alpha(img, sky):
    """Soft sky matte with defringing: pixels along the skyline that still carry the OLD sky's
    colour (anti-aliasing) get a partial alpha, so they take the new sky's colour instead of
    glowing as a white rim. Building pixels well inside the edge are never touched."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32)
    sk = sky.astype(np.float32)
    num = cv2.GaussianBlur(lab * sk[..., None], (0, 0), 12)
    den = cv2.GaussianBlur(sk, (0, 0), 12)[..., None] + 1e-4
    local_sky = num / den                                   # old sky colour extended over the edge
    band = cv2.dilate(sky.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool) & ~sky
    dist = np.linalg.norm((lab - local_sky) * [0.7, 1, 1], axis=2)
    fringe = np.clip(1 - dist / 38.0, 0, 1) * band
    a = np.maximum(sk, fringe)
    return np.clip(cv2.GaussianBlur(a, (0, 0), 0.8), 0, 1)


def fbm(h, w, seed=11, octaves=6):
    """Horizontally stretched noise: reads as thin evening cloud streaks, not smoke."""
    rng = np.random.default_rng(seed)
    out, amp, total = np.zeros((h, w), np.float32), 1.0, 0.0
    for o in range(octaves):
        s = 2 ** (o + 1)
        small = rng.random((s * 3 + 2, s + 2)).astype(np.float32)
        out += amp * cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC)
        total += amp
        amp *= 0.5
    return out / total


SKIES = {  # top -> horizon, RGB
    "dusk": [(14, 20, 58), (58, 40, 96), (170, 80, 110), (245, 150, 90), (255, 205, 140)],
    "golden": [(40, 70, 130), (120, 120, 160), (235, 160, 110), (255, 190, 120), (255, 225, 170)],
    "night": [(4, 6, 22), (10, 14, 40), (22, 26, 64), (48, 40, 80), (90, 60, 90)],
    "day-clean": [(60, 120, 200), (95, 150, 215), (140, 185, 230), (185, 210, 238), (215, 228, 242)],
}


def make_sky(h, w, look, horizon):
    stops = np.array(SKIES[look], np.float32)
    ys = np.clip(np.arange(h, dtype=np.float32) / max(horizon, 1), 0, 1) ** 0.85
    pos = ys * (len(stops) - 1)
    i0 = np.floor(pos).astype(int).clip(0, len(stops) - 2)
    t = (pos - i0)[:, None]
    sky = np.repeat((stops[i0] * (1 - t) + stops[i0 + 1] * t)[:, None, :], w, axis=1)
    if look == "night":
        stars = (np.random.default_rng(3).random((h, w)) > 0.9993) & (ys[:, None] < 0.7)
        sky[stars] = 235
    else:
        band = np.exp(-((ys - 0.55) / 0.3) ** 2)[:, None, None]  # clouds sit in a band above the horizon
        clouds = np.clip((fbm(h, w) - 0.5) * 3.0, 0, 1)[..., None] * band
        clouds = cv2.GaussianBlur(clouds[..., 0], (0, 0), 1.2)[..., None]
        glow_c = np.array(SKIES[look][-2], np.float32)          # underside lit by the setting sun
        shade_c = np.array(SKIES[look][1], np.float32) * 0.9     # top of cloud in shadow
        mix = ys[:, None, None]
        cloud_col = shade_c * (1 - mix) + glow_c * mix
        sky = sky * (1 - clouds * 0.5) + cloud_col * clouds * 0.5
    return sky[..., ::-1]


def real_sky(path, h, w):
    s = cv2.imread(str(path))
    sc = max(w / s.shape[1], h / s.shape[0])
    s = cv2.resize(s, (int(s.shape[1] * sc) + 1, int(s.shape[0] * sc) + 1))
    x0 = (s.shape[1] - w) // 2
    return s[:h, x0:x0 + w].astype(np.float32)


def relight(img, look, building):
    f = img.astype(np.float32) / 255.0
    if look == "day-clean":
        return np.clip(f * 1.03 + 0.01, 0, 1) * 255
    lum = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    exp, tint = {"dusk": (0.62, (0.95, 0.97, 1.08)), "golden": (0.9, (0.9, 1.0, 1.12)),
                 "night": (0.55, (1.1, 1.0, 0.95))}[look]
    out = f * exp * np.array(tint, np.float32)
    glow = np.clip((lum - 0.55) / 0.35, 0, 1)[..., None] * building  # already-lit windows only
    warm = np.array([0.55, 0.8, 1.0], np.float32)
    out = out * (1 - glow * 0.6) + (f * 0.6 + warm * 0.4) * glow * 0.6
    out += cv2.GaussianBlur((glow * warm).astype(np.float32), (0, 0), 6) * (0.15 if look == "golden" else 0.35)
    return np.clip(out, 0, 1) * 255


def place_brand_signs(img, signs):
    """Put signed brands' logos on existing signboards (perspective-correct, board stays in place)."""
    out = img.astype(np.float32)
    h, w = img.shape[:2]
    for s in signs:
        f = BRANDS / f"{s['brand']}.png"
        if not f.exists():
            raise SystemExit(f"Unknown brand '{s['brand']}'. Use one of: {sorted(p.stem for p in BRANDS.glob('*.png'))}")
        quad = np.float32([[x * w, y * h] for x, y in s["quad"]])
        bw = int(max(np.linalg.norm(quad[1] - quad[0]), np.linalg.norm(quad[2] - quad[3])))
        bh = int(max(np.linalg.norm(quad[3] - quad[0]), np.linalg.norm(quad[2] - quad[1])))
        logo = cv2.imread(str(f), cv2.IMREAD_UNCHANGED)
        if logo.shape[2] == 3:
            logo = np.dstack([logo, np.full(logo.shape[:2], 255, np.uint8)])
        ys, xs = np.where(logo[..., 3] > 10)
        logo = logo[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        board = np.dstack([np.full((bh, bw, 3), 250, np.uint8), np.full((bh, bw), 255, np.uint8)])  # clean white panel
        sc = min(bw * 0.86 / logo.shape[1], bh * 0.78 / logo.shape[0])
        lg = cv2.resize(logo, (max(1, int(logo.shape[1] * sc)), max(1, int(logo.shape[0] * sc))), interpolation=cv2.INTER_AREA)
        oy, ox = (bh - lg.shape[0]) // 2, (bw - lg.shape[1]) // 2
        a = lg[..., 3:4] / 255.0
        board[oy:oy + lg.shape[0], ox:ox + lg.shape[1], :3] = (lg[..., :3] * a + board[oy:oy + lg.shape[0], ox:ox + lg.shape[1], :3] * (1 - a)).astype(np.uint8)
        M = cv2.getPerspectiveTransform(np.float32([[0, 0], [bw, 0], [bw, bh], [0, bh]]), quad)
        warped = cv2.warpPerspective(board, M, (w, h), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0)).astype(np.float32)
        al = warped[..., 3:4] / 255.0
        out = out * (1 - al) + warped[..., :3] * al
    return out.astype(np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("out")
    ap.add_argument("--look", default="dusk", choices=list(SKIES))
    ap.add_argument("--sky")
    ap.add_argument("--brand-signs")
    a = ap.parse_args()

    img = cv2.imread(a.source)
    h, w = img.shape[:2]
    signs = json.loads(Path(a.brand_signs).read_text()) if a.brand_signs else []
    sky = sky_mask(img)
    horizon = int(np.percentile(np.where(sky)[0], 98)) if sky.any() else h // 3
    alpha = sky_alpha(img, sky)[..., None]
    lit = relight(img, a.look, 1 - alpha)
    if signs:  # signs are lit boards: place after relighting, then match the scene brightness a little
        dim = {"dusk": 0.85, "golden": 0.95, "night": 0.75, "day-clean": 1.0}[a.look]
        lit = place_brand_signs(np.clip(lit, 0, 255).astype(np.uint8), signs).astype(np.float32) * 1.0
        mask = np.zeros((h, w), np.float32)
        for s in signs:
            cv2.fillConvexPoly(mask, np.int32([[x * w, y * h] for x, y in s["quad"]]), 1.0)
        lit = lit * (1 - mask[..., None] * (1 - dim))
    new_sky = real_sky(a.sky, h, w) if a.sky else make_sky(h, w, a.look, horizon)
    out = lit * (1 - alpha) + new_sky * alpha
    p = Path(a.out)
    cv2.imwrite(str(p), np.clip(out, 0, 255).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 93])
    cv2.imwrite(str(p.with_suffix(".sky.png")), (sky * 255).astype(np.uint8))
    p.with_suffix(".edits.json").write_text(json.dumps({
        "source": str(Path(a.source).resolve()), "look": a.look, "sky_mask": str(p.with_suffix(".sky.png").resolve()),
        "sky_fraction": round(float(sky.mean()), 3), "brand_signs": signs, "real_sky": a.sky}, indent=1))
    print(f"wrote {p} (sky {sky.mean():.0%} of frame, {len(signs)} brand signboard(s))")


if __name__ == "__main__":
    main()
