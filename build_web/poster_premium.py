"""Premium redesign of poster #1 (Limited SCO spaces) from the golden-hour render.

Art direction: cinematic full-bleed photo, warm grade and vignette, thin gold inset
frame with corner marks, gold RERA seal, oversized headline, glass fact bar, CTA pill.
Everything is plain HTML/CSS so it imports cleanly into Adobe Express.
"""

import base64
import io
import sys
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter

S = "C:/Users/STAR/AppData/Local/Temp/claude/C--AIProject-MarketingCampaignGenerator/c71bc632-b1bc-4d2f-a292-dc2d1d37c290/scratchpad/"
SRC = Path("D:/shrih plaza/ai images/ai final/5..png")
LOGO = Path("E:/Shrih plaza/assets/original/logo-transparent.png")


def b64(img, fmt, **kw):
    buf = io.BytesIO()
    img.save(buf, fmt, **kw)
    return base64.b64encode(buf.getvalue()).decode()


src = Image.open(SRC).convert("RGB")
w, h = src.size
cw = round(h * 1080 / 1350)
x0 = (w - cw) // 2
photo = src.crop((x0, 0, x0 + cw, h)).resize((1080, 1350), Image.LANCZOS)
photo = photo.filter(ImageFilter.UnsharpMask(radius=1.4, percent=90, threshold=3))
photo = ImageEnhance.Contrast(photo).enhance(1.06)
photo = ImageEnhance.Color(photo).enhance(1.08)
hero = b64(photo, "JPEG", quality=86, optimize=True)

logo = Image.open(LOGO).convert("RGBA")
logo = logo.resize((210, round(210 * logo.height / logo.width)), Image.LANCZOS)
logo_b64, lh = b64(logo, "PNG", optimize=True), logo.height

G, G2, N = "#D7B469", "#F1D89A", "#0B1237"
P = "font-family:'poppins',sans-serif;"
html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="hz:slide-selector" content=".slide">
<link rel="stylesheet" href="https://use.typekit.net/nho3gjv.css">
<style>html,body{{margin:0;padding:0;background:{N}}}
.slide{{position:relative;width:1080px;height:1350px;overflow:hidden;background:{N}}}
.a{{position:absolute;margin:0}}</style></head><body>
<div class="slide" data-canvas-width="1080" data-canvas-height="1350">
<img class="a" src="data:image/jpeg;base64,{hero}" style="left:0;top:0;width:1080px;height:1350px" alt="Golden-hour render of the Shrih Plaza courtyard">
<div class="a" style="left:0;top:0;width:1080px;height:300px;background:linear-gradient(180deg,rgba(8,12,38,0.88) 0%,rgba(8,12,38,0.45) 60%,rgba(8,12,38,0) 100%)"></div>
<div class="a" style="left:0;top:600px;width:1080px;height:750px;background:linear-gradient(180deg,rgba(8,12,38,0) 0%,rgba(8,12,38,0.72) 22%,rgba(8,12,38,0.93) 42%,#080C26 100%)"></div>
<div class="a" style="left:28px;top:28px;width:1024px;height:1294px;border:1.5px solid rgba(215,180,105,0.75)"></div>
<div class="a" style="left:20px;top:20px;width:44px;height:3px;background:{G}"></div><div class="a" style="left:20px;top:20px;width:3px;height:44px;background:{G}"></div>
<div class="a" style="left:1016px;top:20px;width:44px;height:3px;background:{G}"></div><div class="a" style="left:1057px;top:20px;width:3px;height:44px;background:{G}"></div>
<div class="a" style="left:20px;top:1327px;width:44px;height:3px;background:{G}"></div><div class="a" style="left:20px;top:1286px;width:3px;height:44px;background:{G}"></div>
<div class="a" style="left:1016px;top:1327px;width:44px;height:3px;background:{G}"></div><div class="a" style="left:1057px;top:1286px;width:3px;height:44px;background:{G}"></div>
<img class="a" src="data:image/png;base64,{logo_b64}" style="left:66px;top:60px;width:210px;height:{lh}px" alt="Shrih Plaza logo">
<div class="a" style="left:862px;top:58px;width:150px;height:150px;border-radius:75px;border:2px solid {G};background:rgba(8,12,38,0.55)"></div>
<div class="a" style="left:872px;top:68px;width:130px;height:130px;border-radius:65px;border:1px solid rgba(215,180,105,0.55)"></div>
<p class="a" style="left:862px;top:92px;width:150px;text-align:center;{P}font-weight:600;font-size:22px;line-height:26px;letter-spacing:3px;color:{G2}">RERA</p>
<p class="a" style="left:862px;top:120px;width:150px;text-align:center;{P}font-weight:500;font-size:14px;line-height:18px;letter-spacing:3px;color:#FFFFFF">APPROVED</p>
<div class="a" style="left:912px;top:146px;width:50px;height:1px;background:{G}"></div>
<p class="a" style="left:862px;top:153px;width:150px;text-align:center;{P}font-weight:400;font-size:11px;line-height:14px;letter-spacing:2px;color:#D9DDEE">FULLY APPROVED</p>
<p class="a" style="left:66px;top:800px;width:948px;{P}font-weight:500;font-size:20px;line-height:28px;letter-spacing:9px;color:{G2}">SH-11 &nbsp;·&nbsp; DHURI &nbsp;·&nbsp; PUNJAB</p>
<p class="a" style="left:60px;top:836px;width:960px;{P}font-weight:600;font-size:150px;line-height:150px;letter-spacing:6px;color:{G}">LIMITED</p>
<p class="a" style="left:66px;top:990px;width:948px;{P}font-weight:300;font-size:58px;line-height:66px;letter-spacing:4px;color:#FFFFFF">SCO SPACES AVAILABLE</p>
<div class="a" style="left:66px;top:1074px;width:120px;height:3px;background:{G}"></div>
<p class="a" style="left:206px;top:1062px;width:808px;{P}font-weight:400;font-size:20px;line-height:28px;letter-spacing:2px;color:#D9DDEE">Construction nearing completion</p>
<div class="a" style="left:66px;top:1112px;width:948px;height:64px;background:rgba(255,255,255,0.08);border:1px solid rgba(215,180,105,0.45)"></div>
<p class="a" style="left:66px;top:1130px;width:316px;text-align:center;{P}font-weight:500;font-size:19px;line-height:28px;letter-spacing:2px;color:#FFFFFF">RETAIL SHOPS</p>
<div class="a" style="left:381px;top:1128px;width:1px;height:32px;background:rgba(215,180,105,0.6)"></div>
<p class="a" style="left:382px;top:1130px;width:316px;text-align:center;{P}font-weight:500;font-size:19px;line-height:28px;letter-spacing:2px;color:#FFFFFF">SCO SPACES</p>
<div class="a" style="left:697px;top:1128px;width:1px;height:32px;background:rgba(215,180,105,0.6)"></div>
<p class="a" style="left:698px;top:1130px;width:316px;text-align:center;{P}font-weight:500;font-size:19px;line-height:28px;letter-spacing:2px;color:#FFFFFF">OFFICES</p>
<div class="a" style="left:66px;top:1200px;width:948px;height:84px;background:{G}"></div>
<p class="a" style="left:100px;top:1216px;width:460px;{P}font-weight:600;font-size:28px;line-height:52px;letter-spacing:1px;color:{N}">BOOK A SITE VISIT</p>
<p class="a" style="left:540px;top:1216px;width:440px;text-align:right;{P}font-weight:600;font-size:34px;line-height:52px;color:{N}">+91 90564 53575</p>
<p class="a" style="left:66px;top:1296px;width:948px;text-align:right;{P}font-weight:400;font-size:14px;line-height:18px;color:#AEB6D0">Artist's impression.</p>
</div></body></html>"""
Path(S + "poster1_premium.html").write_text(html, encoding="utf-8")
print(len(html))
