"""The owner's approve / deny decisions, and what the pipeline learns from them.

Every decision is stored in memory/decisions.json. From it the pipeline derives:
- lessons the strategist must respect (why past posts were denied),
- phrases the owner banned, which the legal guard and auto-fix enforce,
- layout and palette combinations the owner denied for design reasons,
- approved examples to imitate.
A denial with a category is also written to mistake memory, so the existing
"do not repeat" mechanism picks it up as well.
"""

from datetime import datetime
from typing import Any

from . import mistake_memory
from .io import read_json, write_json
from .paths import MEMORY_DIR

DECISIONS_PATH = MEMORY_DIR / "decisions.json"
CATEGORIES = {"copy", "design", "claim", "layout", "other"}
_MISTAKE_CATEGORY = {"copy": "other", "design": "design_defect", "claim": "misleading_completion",
                     "layout": "design_defect", "other": "other"}


def load_decisions() -> list[dict[str, Any]]:
    if not DECISIONS_PATH.exists():
        return []
    return list(read_json(DECISIONS_PATH).get("decisions", []))


def _save(decisions: list[dict[str, Any]]) -> None:
    write_json(DECISIONS_PATH, {"decisions": decisions})


def add_decision(
    post_id: str,
    decision: str,
    reason: str = "",
    category: str = "other",
    banned_phrase: str = "",
    context: dict[str, Any] | None = None,
    created: str | None = None,
) -> dict[str, Any]:
    """Record a decision. Deny requires a reason. Re-deciding the same post replaces it."""
    decision = "approved" if decision in {"approve", "approved"} else "denied"
    reason = reason.strip()
    if decision == "denied" and len(reason) < 5:
        raise ValueError("A denial needs a reason of at least 5 characters, so the pipeline can learn from it.")
    category = category if category in CATEGORIES else "other"
    entry = {
        "post_id": post_id,
        "decision": decision,
        "reason": reason,
        "category": category,
        "banned_phrase": banned_phrase.strip(),
        "context": context or {},
        "created": created or datetime.now().isoformat(timespec="seconds"),
    }
    decisions = [d for d in load_decisions() if d.get("post_id") != post_id]
    decisions.append(entry)
    _save(decisions)
    if decision == "denied":
        mistake_memory.append_mistake(
            category=_MISTAKE_CATEGORY[category],
            description=f"Owner denied {post_id}: {reason}",
            avoid_instruction=f"Owner feedback, do not repeat: {reason}",
            source="owner_decision",
        )
    return entry


def import_decisions(items: list[dict[str, Any]]) -> int:
    """Merge decisions exported from the web review page. Returns how many were new or changed."""
    known = {d["post_id"]: d for d in load_decisions()}
    changed = 0
    for item in items:
        post_id = str(item.get("post_id") or item.get("id") or "").strip()
        if not post_id:
            continue
        old = known.get(post_id)
        if old and old.get("created") == item.get("created") and old.get("decision") == item.get("decision"):
            continue
        add_decision(
            post_id, str(item.get("decision", "")), str(item.get("reason", "")),
            str(item.get("category", "other")), str(item.get("banned_phrase", "")),
            item.get("context") or {}, item.get("created"),
        )
        changed += 1
    return changed


def lessons(limit: int = 12) -> list[str]:
    """Plain-language rules from the newest denials, for the strategist prompt."""
    denied = [d for d in load_decisions() if d["decision"] == "denied"]
    denied.sort(key=lambda d: d.get("created", ""), reverse=True)
    return [f"The owner denied a {d['category']} on a past post: {d['reason']}" for d in denied[:limit]]


def approved_examples(limit: int = 3) -> list[str]:
    approved = [d for d in load_decisions() if d["decision"] == "approved" and d.get("context", {}).get("hook")]
    approved.sort(key=lambda d: d.get("created", ""), reverse=True)
    return [f"{d['context']['hook']} | {d['context'].get('caption', '')}"[:260] for d in approved[:limit]]


def banned_phrases() -> list[str]:
    seen: list[str] = []
    for d in load_decisions():
        phrase = str(d.get("banned_phrase", "")).strip()
        if d["decision"] == "denied" and phrase and phrase.lower() not in (p.lower() for p in seen):
            seen.append(phrase)
    return seen


def rejected_combos() -> set[tuple[str, str]]:
    """Layout and palette pairs the owner denied for a design or layout reason."""
    combos: set[tuple[str, str]] = set()
    for d in load_decisions():
        ctx = d.get("context", {})
        if d["decision"] == "denied" and d.get("category") in {"design", "layout"} and ctx.get("layout") and ctx.get("palette"):
            combos.add((ctx["layout"], ctx["palette"]))
    return combos
