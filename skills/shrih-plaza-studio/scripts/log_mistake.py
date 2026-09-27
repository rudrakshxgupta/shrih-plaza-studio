"""Automatic learning: log a mistake the review panel caught, so future runs avoid it.

Usage: python log_mistake.py --category design_defect|misleading_completion|fact|legal|other \
         --what "Headline overflowed the frame" --avoid "Keep the hero word under 9 letters"

Every auto-fix loop calls this for each failure it fixed (guard rejects, preview issues,
fact/legal fails, critic fails). memory_brief.py shows these as PAST MISTAKES on every run.
Updated memory is staged in /mnt/user-data/outputs/memory-update/ for upload to the repo.
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

REPO = Path(os.environ.get("SHRIH_REPO", "/home/claude/shrih-plaza-studio"))
sys.path.insert(0, str(REPO))
from shrih_agent import mistake_memory  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--category", default="other")
ap.add_argument("--what", required=True)
ap.add_argument("--avoid", required=True)
a = ap.parse_args()
existing = [m.get("avoid_instruction", "").lower() for m in mistake_memory.load_mistakes().get("mistakes", [])]
if a.avoid.lower() in existing:
    print("already known, not duplicated")
else:
    mistake_memory.append_mistake(a.category, a.what, a.avoid, "claude_review_panel")
    print("logged")
out = Path("/mnt/user-data/outputs/memory-update")
out.mkdir(parents=True, exist_ok=True)
shutil.copy(REPO / "memory" / "mistake_memory.json", out / "mistake_memory.json")
