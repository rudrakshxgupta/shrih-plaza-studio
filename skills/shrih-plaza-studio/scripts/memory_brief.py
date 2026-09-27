"""Print everything the agents must obey for this run, from the repo's live memory.

Usage: python memory_brief.py
"""
import json
import os
import sys
from pathlib import Path

REPO = Path(os.environ.get("SHRIH_REPO", "/home/claude/shrih-plaza-studio"))
sys.path.insert(0, str(REPO))
from shrih_agent import decisions, mistake_memory  # noqa: E402


def load(name):
    p = REPO / "memory" / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


facts, brand, prefs = load("project_facts.json"), load("brand_identity.json"), load("preference_memory.json")
recent = []
for folder in sorted((REPO / "outputs" / "daily").glob("20*"), reverse=True)[:14]:
    r = folder / "report.json"
    if r.exists():
        d = json.loads(r.read_text(encoding="utf-8"))
        recent.append(f"{folder.name}: {d.get('hook','')} [{d.get('layout','')}/{d.get('palette','')}/{d.get('pillar','')}]")

avoid = list(dict.fromkeys(mistake_memory.avoid_instructions()))
brief = {
    "APPROVED CLAIMS (only these facts may appear)": facts.get("approved_claims", []),
    "SIGNED BRANDS (only these 12)": facts.get("signed_brand_associations", []),
    "CONTACT": facts.get("contact", {}),
    "FORBIDDEN CLAIMS / WORDING": facts.get("forbidden_claims", []) + facts.get("construction_and_availability", {}).get("still_forbidden_wording", []),
    "NOT APPROVED FOR USE": {"pricing": facts.get("pricing", {}).get("status"), "possession": facts.get("possession", {}).get("status"),
                              "rera_number": facts.get("approval_status", {}).get("rera_number")},
    "BRAND": {k: brand.get(k) for k in ("tone_of_voice", "colors", "fonts", "cta_preferences", "brand_messages")},
    "OWNER LESSONS (newest denials)": decisions.lessons(),
    "BANNED PHRASES": decisions.banned_phrases(),
    "REJECTED LAYOUT+PALETTE COMBOS": sorted(list(c) for c in decisions.rejected_combos()),
    "APPROVED EXAMPLES": decisions.approved_examples(),
    "PAST MISTAKES, DO NOT REPEAT": avoid,
    "PREFERENCES": prefs,
    "RECENT DAILY POSTS (don't repeat hooks/angles)": recent,
}
print(json.dumps(brief, indent=1, ensure_ascii=False))
