"""Reads trend snapshots written by the Instagram trend scout.

The scout itself runs in a Claude session: it opens Instagram's Explore and
Reels pages in the signed-in browser, looks only (no likes, follows or comments)
and writes a dated Markdown snapshot into inputs/trends/scout/. Scripted,
unattended scraping of Instagram is deliberately not built: it breaks
Instagram's terms and would need the owner's login.
"""

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .paths import INPUTS_DIR

SCOUT_DIR = INPUTS_DIR / "trends" / "scout"


def _section(text: str, heading: str) -> list[str]:
    match = re.search(rf"^##\s+{re.escape(heading)}\s*$([\s\S]*?)(?=^##\s|\Z)", text, re.MULTILINE | re.IGNORECASE)
    if not match:
        return []
    return [line[2:].strip() for line in match.group(1).splitlines() if line.startswith("- ") and line[2:].strip()]


def load_snapshots(max_age_days: int = 30) -> list[dict[str, Any]]:
    if not SCOUT_DIR.exists():
        return []
    cutoff = datetime.now() - timedelta(days=max_age_days)
    snapshots: list[dict[str, Any]] = []
    for path in sorted(SCOUT_DIR.glob("*.md"), reverse=True):
        if path.name.lower().startswith("readme"):
            continue
        if datetime.fromtimestamp(path.stat().st_mtime) < cutoff:
            continue
        text = path.read_text(encoding="utf-8")
        snapshots.append({
            "file": path.name,
            "usable_patterns": _section(text, "Usable patterns"),
            "content_angles": _section(text, "Content angles"),
            "avoid_copying": _section(text, "Avoid copying"),
            "recommended_content_formats": _section(text, "Formats"),
        })
    return snapshots


def merged_scout_notes(max_age_days: int = 30) -> dict[str, Any]:
    merged: dict[str, Any] = {"files": [], "usable_patterns": [], "content_angles": [], "avoid_copying": [],
                              "recommended_content_formats": []}
    for snap in load_snapshots(max_age_days):
        merged["files"].append(snap["file"])
        for key in ("usable_patterns", "content_angles", "avoid_copying", "recommended_content_formats"):
            for item in snap[key]:
                if item not in merged[key]:
                    merged[key].append(item)
    return merged
