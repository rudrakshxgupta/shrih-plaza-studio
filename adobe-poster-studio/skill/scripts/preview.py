"""Render poster HTML to PNG and run automatic layout checks.

Usage:  python preview.py poster.html poster.png

The Adobe Fonts kit can't load inside the sandbox, so Poppins and Playfair
Display are pulled from @fontsource npm packages (cached in /tmp) for the preview only.
Prints JSON: {"png": ..., "issues": [...]}. Any issue must be fixed before export.
"""

import base64
import json
import subprocess
import sys
import tarfile
from pathlib import Path

CACHE = Path("/tmp/shrih-fonts")


FONTS = [  # (npm package, css family, file stem, weights, style)
    ("@fontsource/poppins", "poppins", "poppins-latin-{w}-normal", (300, 400, 500, 600), "normal"),
    ("@fontsource/playfair-display", "playfair-display", "playfair-display-latin-{w}-italic", (400, 700), "italic"),
]


def fonts_css():
    """Adobe Fonts can't load in the sandbox; pull the same families from npm for the preview only."""
    css = []
    for pkg, family, stem, weights, style in FONTS:
        d = CACHE / family
        d.mkdir(parents=True, exist_ok=True)
        if not list(d.glob("package/files/*.woff2")):
            try:
                subprocess.run(["npm", "pack", pkg, "--silent"], cwd=d, check=True, capture_output=True, timeout=120)
                with tarfile.open(next(d.glob("*.tgz"))) as t:
                    t.extractall(d, filter="data")
            except Exception as exc:
                print(f"warning: {family} not available for preview ({exc})", file=sys.stderr)
                continue
        for w in weights:
            f = d / "package/files" / (stem.format(w=w) + ".woff2")
            if f.exists():
                data = base64.b64encode(f.read_bytes()).decode()
                css.append(f"@font-face{{font-family:'{family}';font-weight:{w};font-style:{style};"
                           f"src:url(data:font/woff2;base64,{data}) format('woff2')}}")
    return "<style>" + "".join(css) + "</style>"


CHECK_JS = """() => {
  const slide = document.querySelector('.slide');
  const sr = slide.getBoundingClientRect();
  const issues = [];
  for (const el of slide.querySelectorAll('p')) {
    const txt = el.textContent.trim();
    if (!txt) continue;
    const r = el.getBoundingClientRect();
    if (el.scrollWidth > el.clientWidth + 2)
      issues.push(`text too wide for its box: "${txt}" (${el.scrollWidth}px > ${el.clientWidth}px)`);
    if (r.right > sr.right - 28 || r.left < sr.left + 28 || r.bottom > sr.bottom - 28)
      issues.push(`text crosses the frame edge: "${txt}"`);
  }
  const ps = [...slide.querySelectorAll('p')].filter(p => p.textContent.trim());
  for (let i = 0; i < ps.length; i++) for (let j = i + 1; j < ps.length; j++) {
    const a = ps[i].getBoundingClientRect(), b = ps[j].getBoundingClientRect();
    const ox = Math.min(a.right, b.right) - Math.max(a.left, b.left);
    const oy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
    if (ox > 8 && oy > 6) issues.push(`text overlaps: "${ps[i].textContent.trim()}" / "${ps[j].textContent.trim()}"`);
  }
  // props must not cover text, the logo or the seal
  const props = [...slide.querySelectorAll('img[data-prop]')];
  const guarded = [...ps, ...slide.querySelectorAll('img[alt="Shrih Plaza logo"]')];
  for (const pr of props) {
    const a = pr.getBoundingClientRect();
    for (const g of guarded) {
      const b = g.getBoundingClientRect();
      const ox = Math.min(a.right, b.right) - Math.max(a.left, b.left);
      const oy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      if (ox > 4 && oy > 4) { issues.push(`prop ${pr.dataset.prop} covers "${(g.textContent || g.alt).trim()}"`); break; }
    }
    if (a.left < 862 + 150 && a.right > 862 && a.top < 208 && a.bottom > 58 && slide.innerHTML.includes('>RERA<'))
      issues.push(`prop ${pr.dataset.prop} covers the RERA seal`);
  }
  const lowres = slide.dataset.lowres;
  if (lowres) issues.push(`photo upscaled ${lowres}x: will look soft. Lower zoom or use a higher-resolution render`);
  return issues;
}"""


def main():
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    html = src.read_text(encoding="utf-8").replace("</head>", fonts_css() + "</head>", 1)
    tmp = src.with_suffix(".preview.html")
    tmp.write_text(html, encoding="utf-8")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1080, "height": 1350})
        placeholder = ('<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400"><rect x="4" y="4" width="392" '
                       'height="392" fill="rgba(215,180,105,0.25)" stroke="#D7B469" stroke-width="8" stroke-dasharray="24 16"/>'
                       '<text x="200" y="215" font-size="44" text-anchor="middle" fill="#F1D89A">PROP</text></svg>')

        def remote(route):
            url = route.request.url
            if not url.startswith("http"):
                return route.continue_()
            if "typekit" in url or "fonts." in url:
                return route.abort()
            # Adobe Stock / hosted props can't load in the sandbox: show a gold placeholder box
            return route.fulfill(status=200, content_type="image/svg+xml", body=placeholder)

        pg.route("**/*", remote)
        pg.goto(tmp.resolve().as_uri())
        pg.wait_for_timeout(400)
        issues = pg.evaluate(CHECK_JS)
        pg.locator(".slide").screenshot(path=str(out))
        b.close()
    tmp.unlink(missing_ok=True)
    print(json.dumps({"png": str(out), "issues": issues}, indent=2))


if __name__ == "__main__":
    main()
