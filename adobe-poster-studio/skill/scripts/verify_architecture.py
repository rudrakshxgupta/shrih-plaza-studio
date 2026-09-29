"""Architecture guard: prove the building in an edited image is the same real building.

Usage:  python verify_architecture.py ORIGINAL EDITED [--edits EDITED.edits.json] [--min-score 0.9]

Architecture is made of long straight lines: rooflines, columns, floor slabs, window frames,
signboard edges. The guard finds every long straight line in the original render and checks it
is still in the edited image at the same place, and that the edited image has no long straight
lines the original lacks. New sky, relighting and declared brand signboards are excluded.
Grass, cars and paving texture don't matter here, lines do.
Second check: tone-invariant gradient correlation over the facade, area by area. Relighting
scales gradients but keeps their direction; a redrawn, shifted or copied facade doesn't.
Calibration (2026-09-27, real renders): genuine dusk/golden/night/brand-sign edits score
0.98-1.00 in every area; stretched, shifted, copied-wing and swapped buildings drop below 0.45.
Pass = line score >= 0.9, overall >= 0.95, every area >= 0.9.
Verify at full photo size BEFORE cropping into a poster. Exit code 1 = reject.
"""
import argparse
import json
import sys

import cv2
import numpy as np
from skimage.exposure import match_histograms


def edges(gray):
    g = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    g = cv2.bilateralFilter(g, 7, 40, 7)
    v = np.median(g)
    return cv2.Canny(g, int(max(10, 0.66 * v)), int(min(255, 1.33 * v)))


def segments(edge, region, min_len):
    e = edge.copy()
    e[~region] = 0
    L = cv2.HoughLinesP(e, 1, np.pi / 360, threshold=40, minLineLength=min_len, maxLineGap=4)
    return [] if L is None else [tuple(map(int, s[0])) for s in L]


def support(segs, other_edges, tol=3):
    """Length-weighted fraction of segments that the other image's edges still trace."""
    d = cv2.dilate((other_edges > 0).astype(np.uint8), np.ones((2 * tol + 1, 2 * tol + 1), np.uint8)) > 0
    h, w = d.shape
    tot = ok = 0.0
    bad = []
    for x1, y1, x2, y2 in segs:
        n = max(int(np.hypot(x2 - x1, y2 - y1)), 2)
        xs = np.linspace(x1, x2, n).round().astype(int).clip(0, w - 1)
        ys = np.linspace(y1, y2, n).round().astype(int).clip(0, h - 1)
        frac = d[ys, xs].mean()
        tot += n
        ok += n * (frac >= 0.7)
        if frac < 0.7:
            bad.append(((x1 + x2) / 2 / w, (y1 + y2) / 2 / h, n))
    return (ok / tot if tot else 1.0), bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("original")
    ap.add_argument("edited")
    ap.add_argument("--edits")
    ap.add_argument("--min-score", type=float, default=0.9)
    a = ap.parse_args()

    o, e = cv2.imread(a.original), cv2.imread(a.edited)
    if e.shape[:2] != o.shape[:2]:
        e = cv2.resize(e, (o.shape[1], o.shape[0]), interpolation=cv2.INTER_AREA)
    h, w = o.shape[:2]
    info = json.load(open(a.edits)) if a.edits else {}
    region = np.ones((h, w), bool)
    if info.get("sky_mask"):
        sky = cv2.imread(info["sky_mask"], cv2.IMREAD_GRAYSCALE) > 127
        region &= ~(cv2.dilate(sky.astype(np.uint8), np.ones((11, 11), np.uint8)) > 0)
    signs = np.zeros((h, w), np.uint8)
    for s in info.get("brand_signs", []):
        cv2.fillConvexPoly(signs, np.int32([[x * w, y * h] for x, y in s["quad"]]), 1)
    region &= ~(cv2.dilate(signs, np.ones((9, 9), np.uint8)) > 0)

    go, ge = cv2.cvtColor(o, cv2.COLOR_BGR2GRAY), cv2.cvtColor(e, cv2.COLOR_BGR2GRAY)
    ge_m = ge.copy()
    ge_m[region] = match_histograms(ge[region], go[region]).astype(np.uint8)  # undo relight
    eo, ee = edges(go), edges(ge_m)
    min_len = max(25, int(0.035 * w))
    so, se = segments(eo, region, min_len), segments(ee, region, min_len)
    recall, missing = support(so, ee)       # original lines still there
    precision, invented = support(se, eo)   # no new lines
    line_score = 2 * recall * precision / max(recall + precision, 1e-6)

    # Detail check: tone-invariant gradient correlation, cell by cell, over the building (skyline
    # band excluded: a new sky legitimately changes contrast right at the roof edge). Relighting
    # scales gradients but keeps their direction; a redrawn, shifted or copied facade does not.
    skyband = np.zeros((h, w), bool)
    if info.get("sky_mask"):
        skyband = cv2.dilate(sky.astype(np.uint8), np.ones((31, 31), np.uint8)) > 0
    zone = region & ~skyband
    fo, fe = go.astype(np.float32), cv2.GaussianBlur(ge_m, (3, 3), 0).astype(np.float32)
    fo = cv2.GaussianBlur(fo, (3, 3), 0)
    gxo, gyo = cv2.Sobel(fo, cv2.CV_32F, 1, 0), cv2.Sobel(fo, cv2.CV_32F, 0, 1)
    gxe, gye = cv2.Sobel(fe, cv2.CV_32F, 1, 0), cv2.Sobel(fe, cv2.CV_32F, 0, 1)
    mag_o = np.hypot(gxo, gyo)
    strong = zone & (mag_o > np.percentile(mag_o[zone], 70) if zone.any() else zone)
    cells_bad, allcells, gh, gw = [], [], 6, 8
    for r in range(gh):
        for c in range(gw):
            sl = (slice(r * h // gh, (r + 1) * h // gh), slice(c * w // gw, (c + 1) * w // gw))
            m = strong[sl]
            if m.sum() < 400:
                continue
            dot = (gxo[sl][m] * gxe[sl][m] + gyo[sl][m] * gye[sl][m]).sum()
            nrm = np.sqrt(((gxo[sl][m] ** 2 + gyo[sl][m] ** 2).sum()) * ((gxe[sl][m] ** 2 + gye[sl][m] ** 2).sum())) + 1e-6
            f = float(dot / nrm)
            allcells.append(round(f, 3))
            if f < 0.9:
                cells_bad.append((f"x {(c + .5) / gw:.0%}, y {(r + .5) / gh:.0%}", round(f, 3)))
    m = strong
    pixel_score = float((gxo[m] * gxe[m] + gyo[m] * gye[m]).sum() /
                        (np.sqrt((gxo[m] ** 2 + gyo[m] ** 2).sum() * (gxe[m] ** 2 + gye[m] ** 2).sum()) + 1e-6))
    score = min(line_score, pixel_score)
    ok = line_score >= a.min_score and pixel_score >= 0.95 and not cells_bad

    def where(items):
        items = sorted(items, key=lambda t: -t[2])[:5]
        return [f"x {x:.0%}, y {y:.0%} ({n}px)" for x, y, n in items]

    print(json.dumps({"pass": bool(ok), "score": round(float(score), 3), "line_score": round(float(line_score), 3),
                      "pixel_score": round(float(pixel_score), 3),  "changed_areas": sorted(cells_bad, key=lambda t: t[1])[:6],
                      "lines_kept": round(float(recall), 3), "lines_not_invented": round(float(precision), 3),
                      "lines_checked": len(so), "missing_lines_at": where(missing), "new_lines_at": where(invented)}, indent=1))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
