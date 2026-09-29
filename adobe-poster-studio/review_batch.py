"""Make a batch of posts for a joint review: the self-review agent, Claude and the owner.

Each variant uses only approved claims. Every post goes through the critic, fact
checker, legal guard, design agent, visual reviewer and self-review agent, and is
saved under outputs/review_batch/<batch>/<nn>/.
"""

import json
import shutil
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shrih_agent.models import ContentDraft  # noqa: E402
from shrih_agent.paths import OUTPUTS_DIR  # noqa: E402
from shrih_agent.pipeline import ContentPipeline  # noqa: E402
from shrih_agent.self_review import SelfReviewAgent  # noqa: E402

PHONE = "+91 90564 53575"
TAGS = ["#ShrihPlaza", "#Dhuri", "#SCOSpaces", "#CommercialProperty", "#RetailSpace", "#PunjabRealEstate"]

VARIANTS = [
    dict(pillar="Construction update", layout="hero", palette="navy", eyebrow="Construction nearing completion",
         hook="Limited SCO spaces available.", support="Premium commercial spaces on SH-11, Dhuri.",
         caption=f"Construction is nearing completion at SHRIH PLAZA on SH-11, Dhuri. Limited SCO spaces are available. Book a site visit: {PHONE}"),
    dict(pillar="Highway visibility", layout="hero", palette="navy", eyebrow="SH-11 highway, Dhuri",
         hook="A high-visibility address for growing brands.", support="Premium SCO spaces and retail shops on SH-11, Dhuri.",
         caption=f"SHRIH PLAZA gives your brand a high-visibility commercial address on the SH-11 highway in Dhuri. Premium SCO spaces and retail shops. Book a site visit: {PHONE}"),
    dict(pillar="Retail and SCO opportunity", layout="hero", palette="emerald", eyebrow="RERA approved commercial project",
         hook="Where retail, food and business meet.", support="Retail shops, SCO spaces and offices under one roof.",
         caption=f"SHRIH PLAZA brings retail shops, SCO spaces and offices together on SH-11, Dhuri. RERA approved. Book a site visit: {PHONE}"),
    dict(pillar="Signed brands", layout="tenants", palette="navy", tenant_headline="SIGNED BRANDS.<br>PREMIUM ADDRESS.",
         hook="Signed brands. Premium frontage.", support="",
         caption=f"SHRIH PLAZA features signed brand associations across food, retail, lifestyle and daily convenience on SH-11, Dhuri. Book a site visit: {PHONE}"),
    dict(pillar="Central parking", layout="hero", palette="charcoal", eyebrow="Built for visitors",
         hook="Central parking. Easy visits.", support="Central surface parking at SHRIH PLAZA, SH-11, Dhuri.",
         caption=f"SHRIH PLAZA includes central surface parking, so shoppers and clients reach your retail shop with ease. SH-11, Dhuri. Book a site visit: {PHONE}"),
    dict(pillar="Premium frontage", layout="hero", palette="plum", eyebrow="Premium SCO facades",
         hook="Frontage built for footfall.", support="Premium SCO facades and retail frontage on SH-11.",
         caption=f"Premium SCO facades and retail frontage at SHRIH PLAZA are built for footfall on SH-11, Dhuri. Limited SCO spaces are available. Book a site visit: {PHONE}"),
    dict(pillar="Site visit", layout="hero", palette="maroon", eyebrow="Visit SHRIH PLAZA",
         hook="See it before you decide.", support="Book a site visit to SHRIH PLAZA, SH-11, Dhuri.",
         caption=f"See the premium SCO spaces and retail shops at SHRIH PLAZA for yourself. SH-11, Dhuri. RERA approved. Book a site visit: {PHONE}"),
    dict(pillar="Everything in one post", layout="hero", palette="navy", eyebrow="RERA approved, fully approved project",
         hook="Premium SCO spaces, retail shops, offices, central parking and signed brands on SH-11, Dhuri.",
         support="Retail shops, SCO spaces, offices, central parking and signed brands.",
         caption=f"SHRIH PLAZA on SH-11, Dhuri offers premium SCO spaces, retail shops and office spaces with central surface parking, premium SCO facades and retail frontage, and signed brand associations across food, retail, lifestyle and daily convenience. Construction is nearing completion and limited SCO spaces are available. RERA approved. Book a site visit: {PHONE}"),
    dict(pillar="Investor", layout="hero", palette="emerald", eyebrow="For business owners and investors",
         hook="Your next commercial address.", support="Premium SCO spaces on SH-11, Dhuri. RERA approved.",
         caption=f"Looking for a commercial address with highway visibility? SHRIH PLAZA offers premium SCO spaces on SH-11, Dhuri. RERA approved. Book a site visit: {PHONE}"),
    dict(pillar="Signed brands (warm)", layout="tenants", palette="maroon", tenant_headline="GREAT BRANDS<br>ARE MOVING IN",
         hook="Great brands are moving in.", support="",
         caption=f"SHRIH PLAZA features signed brand associations across food, retail, lifestyle and daily convenience. Limited SCO spaces are available on SH-11, Dhuri. Book a site visit: {PHONE}"),
]


def main() -> int:
    batch = date.today().isoformat()
    root = OUTPUTS_DIR / "review_batch" / batch
    if root.exists():
        shutil.rmtree(root)
    pipeline, reviewer = ContentPipeline(), SelfReviewAgent()
    summary = []
    for n, v in enumerate(VARIANTS, start=1):
        post_id = f"batch-{batch}-{n:02d}"
        draft = ContentDraft(platform="Instagram", format="post", hook=v["hook"], caption=v["caption"],
                             visual_direction="", cta="Book a site visit", hashtags=TAGS,
                             metadata={k: v.get(k, "") for k in ("eyebrow", "support", "tenant_headline")})
        draft, history, text_ok = pipeline._text_review_loop(draft, 3)
        design = pipeline.design_and_review(draft, v["layout"], palette=v["palette"])
        folder = root / f"{n:02d}"
        folder.mkdir(parents=True, exist_ok=True)
        if design.get("png"):
            shutil.copyfile(design["png"], folder / "post.png")
        checks = design["attempts"][-1]["review"].get("checks", {})
        report = {"post_id": post_id, "batch": batch, "number": n, "pillar": v["pillar"], "layout": v["layout"],
                  "palette": v["palette"], "hook": draft.hook, "caption": draft.caption, "hashtags": draft.hashtags,
                  "text_guards": [(r["agent"], r["approved"]) for r in history[-1]["reviews"]],
                  "text_approved": text_ok, "design_status": design["status"], "visual_checks": checks,
                  "date": batch}
        report["agent_review"] = reviewer.run(report, folder / "post.png")
        (folder / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        summary.append((n, v["pillar"], report["agent_review"]["decision"], report["agent_review"]["score"], text_ok, design["status"]))
    for row in summary:
        print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
