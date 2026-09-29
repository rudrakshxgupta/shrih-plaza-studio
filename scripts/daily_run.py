"""One daily run: pick today's content pillar, run the full pipeline, save the post.

Runs the same on your PC or on GitHub's servers. If SMTP_USER, SMTP_PASSWORD and
DAILY_EMAIL_TO are set it also emails the finished post as an attachment.
Nothing is ever posted to Instagram.
"""

import json
import os
import shutil
import smtplib
import sys
from datetime import date
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shrih_agent import decisions as owner_decisions  # noqa: E402
from shrih_agent.paths import INPUTS_DIR, OUTPUTS_DIR  # noqa: E402
from shrih_agent.pipeline import ContentPipeline  # noqa: E402

# The seven content pillars from the brand kit. Layout and palette rotate with them.
PALETTE_ORDER = ["navy", "emerald", "charcoal", "plum", "maroon"]

PILLARS = [
    ("Highway visibility", "Highlight the high-visibility SH-11 highway address in Dhuri for retail brands.", "hero", "navy"),
    ("Retail and SCO opportunity", "Invite retailers and investors to the premium SCO spaces and retail shops. Limited SCO spaces are available.", "hero", "emerald"),
    ("Signed brands", "Show that SHRIH PLAZA has signed brand associations across food, retail, lifestyle and daily convenience.", "tenants", "navy"),
    ("Central parking", "Highlight the central surface parking and easy access for visitors and shoppers.", "hero", "charcoal"),
    ("Premium frontage", "Highlight premium SCO facades and retail frontage built for footfall.", "hero", "plum"),
    ("Construction update", "Share that construction is nearing completion and limited SCO spaces are available.", "hero", "maroon"),
    ("Site visit", "Invite business owners to book a site visit and see the project.", "hero", "navy"),
]


def send_email(folder: Path, subject: str, body: str) -> str:
    user, password, to = os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD"), os.getenv("DAILY_EMAIL_TO")
    if not (user and password and to):
        return "not configured (set SMTP_USER, SMTP_PASSWORD, DAILY_EMAIL_TO)"
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = user, to, subject
    message.set_content(body)
    png = folder / "post.png"
    if png.exists():
        message.add_attachment(png.read_bytes(), maintype="image", subtype="png", filename="shrih-plaza-post.png")
    with smtplib.SMTP_SSL(os.getenv("SMTP_HOST", "smtp.gmail.com"), int(os.getenv("SMTP_PORT", "465"))) as server:
        server.login(user, password)
        server.send_message(message)
    return f"sent to {to}"


def main() -> int:
    today = date.today()
    name, brief, layout, palette = PILLARS[today.toordinal() % len(PILLARS)]
    denied = owner_decisions.rejected_combos()
    if (layout, palette) in denied:
        palette = next((p for p in PALETTE_ORDER if (layout, p) not in denied), palette)
    brief_path = INPUTS_DIR / "trends" / "daily_brief.md"
    brief_path.write_text(f"# Daily brief {today.isoformat()}\n\nPillar: {name}\n\n{brief}\n", encoding="utf-8")

    # Owner rule (2026-09-30): AI real-estate content, not posters. The building stays exactly as the render.
    post_id = f"daily-{today.isoformat()}"
    result = ContentPipeline().run(brief_path, ai_content=True, post_id=post_id)
    layout = f"ai:{(result.get('design') or {}).get('concept')}"
    design, content = result.get("design") or {}, result["final_content"]

    folder = OUTPUTS_DIR / "daily" / today.isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    if design.get("png"):
        shutil.copyfile(design["png"], folder / "post.png")
    caption = f"{content['hook']}\n\n{content['caption']}\n\nArtist's impression.\n\n{' '.join(content.get('hashtags', []))}\n"
    (folder / "caption.txt").write_text(caption, encoding="utf-8")
    if os.getenv("GEMINI_API_KEY"):
        llm = "gemini"
    elif os.getenv("OPENAI_API_KEY"):
        llm = "openai"
    else:
        llm = "local fallback (same default copy every day)"
    report = {
        "post_id": post_id, "kind": "ai_content",
        "date": today.isoformat(), "pillar": name, "layout": layout, "palette": palette,
        "concept": design.get("concept"), "scene": design.get("scene"), "source_image": design.get("source_image"),
        "architecture_score": design.get("architecture_score"), "model": design.get("model"), "image_error": design.get("error"),
        "hook": content["hook"], "caption": content["caption"], "hashtags": content.get("hashtags", []),
        "lessons_applied": len(owner_decisions.lessons()), "banned_phrases": owner_decisions.banned_phrases(),
        "status": result["status"], "design_status": design.get("status"),
        "visual_checks": {"image_made": bool(design.get("png")), "building_unchanged": design.get("status") == "approved"}, "trend_mode": (result.get("trend_report") or {}).get("mode"),
        "llm": llm,
    }

    subject = f"Shrih Plaza daily post for approval - {today.isoformat()} ({name})"
    body = (f"Status: {result['status']}\nPillar: {name} | concept {layout}\n\n{caption}\n"
            "To approve, reply APPROVE, or write what to change.\n"
            "The system never posts to Instagram; publish it by hand after approval.\n")
    report["email"] = send_email(folder, subject, body)
    (folder / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0  # a missing image (no OPENAI_API_KEY secret, budget reached) still saves the caption for review


if __name__ == "__main__":
    raise SystemExit(main())
