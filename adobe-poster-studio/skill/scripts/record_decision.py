"""Record the owner's approve/deny so the whole system learns, then stage files for GitHub.

Usage:
  python record_decision.py --post-id claude-2026-09-26-01 --decision denied \
      --reason "too plain, needs bolder layout" --category design \
      --context '{"hook":"...","caption":"...","layout":"hero","palette":"navy","pillar":"...","date":"2026-09-26"}' \
      [--banned-phrase "hurry"] [--express-url URL]

Categories: see shrih_agent/decisions.py CATEGORIES (design, layout, copy, fact, ... other).
Updated memory files are copied to /mnt/user-data/outputs/memory-update/ for the owner
to upload to the repo's memory/ folder (GitHub web: Add file -> Upload files).
"""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

REPO = Path(os.environ.get("SHRIH_REPO", "/home/claude/shrih-plaza-studio"))
sys.path.insert(0, str(REPO))
from shrih_agent import decisions  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--post-id", required=True)
ap.add_argument("--decision", required=True, choices=["approved", "denied"])
ap.add_argument("--reason", default="")
ap.add_argument("--category", default="other")
ap.add_argument("--banned-phrase", default="")
ap.add_argument("--context", default="{}")
ap.add_argument("--express-url", default="")
a = ap.parse_args()

ctx = json.loads(a.context)
entry = decisions.add_decision(a.post_id, a.decision, a.reason, a.category, a.banned_phrase, ctx)
if a.express_url and a.decision == "approved":
    queue = decisions.load_redesign_queue()
    if any(q.get("post_id") == a.post_id for q in queue):
        decisions.complete_redesign(a.post_id, a.express_url)

out = Path("/mnt/user-data/outputs/memory-update")
out.mkdir(parents=True, exist_ok=True)
for name in ("decisions.json", "mistake_memory.json", "redesign_queue.json", "preference_memory.json"):
    src = REPO / "memory" / name
    if src.exists():
        shutil.copy(src, out / name)
print(json.dumps({"recorded": entry, "upload_these_to_repo_memory_folder": sorted(p.name for p in out.iterdir())}, indent=1))
