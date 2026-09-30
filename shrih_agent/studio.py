"""Studio HQ: runs one post through the whole team and reports every step live.

Each agent has a job title so the owner can watch the studio work like a manager:
the Content Head assigns the brief, the team writes, checks, designs and reviews,
and the finished post waits for the owner's approval on the Studio HQ page.
Events go to an in-memory feed (streamed to the page) and to outputs/live/events.jsonl.
"""

import importlib.util
import json
import shutil
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from . import decisions as owner_decisions
from .paths import INPUTS_DIR, OUTPUTS_DIR, ROOT

TEAM = [
    {"id": "owner", "title": "Managing Director", "who": "You", "does": "Final approval. Nothing is published without you."},
    {"id": "head", "title": "Content Head", "who": "Orchestrator", "does": "Assigns the brief, guards the image budget, sends the content to you."},
    {"id": "trend", "title": "Trend Scout", "who": "Trend Research Agent", "does": "Brings in current content patterns and angles."},
    {"id": "copy", "title": "Copy Lead", "who": "Content Strategist Agent", "does": "Writes the hook, caption and hashtags in the brand voice."},
    {"id": "critic", "title": "Copy Editor", "who": "Critic Agent", "does": "Checks the hook, length and clarity."},
    {"id": "facts", "title": "Fact Checker", "who": "Fact Checker Agent", "does": "Every claim must be an approved project fact."},
    {"id": "legal", "title": "Legal & RERA Officer", "who": "Legal RERA Agent", "does": "Blocks forbidden claims and banned phrases."},
    {"id": "fix", "title": "Fix-it Editor", "who": "Auto-Fix Agent", "does": "Repairs whatever the reviewers flag."},
    {"id": "art", "title": "AI Visual Artist", "who": "GPT Image 2.5 Flare · OpenAI", "does": "Creates bold, new AI imagery around the real building."},
    {"id": "qa", "title": "Architecture Guard", "who": "Building check", "does": "Lines the AI image up with the real render; the building must not change."},
    {"id": "cd", "title": "Creative Director", "who": "Self-Review Agent", "does": "Scores the post the way you would before you see it."},
    {"id": "memory", "title": "Brand Memory Keeper", "who": "Preference Learning", "does": "Turns your decisions into rules for every next post."},
]

_lock = threading.Lock()
_events: list[dict[str, Any]] = []
_running = {"active": False, "run_id": None}
LOG_PATH = OUTPUTS_DIR / "live" / "events.jsonl"


def emit(agent: str, state: str, message: str, run_id: str | None = None, **data: Any) -> dict[str, Any]:
    """state: working | done | flagged | waiting | idle | error"""
    with _lock:
        event = {"seq": len(_events) + 1, "time": datetime.now().strftime("%H:%M:%S"), "run_id": run_id or _running["run_id"],
                 "agent": agent, "state": state, "message": message, **({"data": data} if data else {})}
        _events.append(event)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def events_since(seq: int) -> list[dict[str, Any]]:
    with _lock:
        return _events[seq:]


def budget() -> dict[str, Any]:
    from .openai_images import budget_left, usage
    u = usage()
    return {"left": budget_left(), "today": u["today"], "daily_limit": u["daily_limit"],
            "month": u["month"], "monthly_limit": u["monthly_limit"]}


def status() -> dict[str, Any]:
    return {"running": _running["active"], "run_id": _running["run_id"], "team": TEAM, "last_seq": len(_events),
            "budget": budget()}


def start_run() -> tuple[bool, str]:
    with _lock:
        if _running["active"]:
            return False, "The team is already working on a post."
        if budget()["left"] <= 0:
            b = budget()
            return False, (f"Image budget reached ({b['today']}/{b['daily_limit']} today, "
                           f"{b['month']}/{b['monthly_limit']} this month). No credits were spent.")
        run_id = datetime.now().strftime("%Y-%m-%d-studio-%H%M%S")
        _running.update(active=True, run_id=run_id)
    threading.Thread(target=_run_safely, args=(run_id,), daemon=True).start()
    return True, run_id


def _run_safely(run_id: str) -> None:
    try:
        _run(run_id)
    except Exception as exc:  # the page must always learn the run ended
        emit("head", "error", f"The run stopped: {exc}", run_id, trace=traceback.format_exc()[-800:])
    finally:
        _running.update(active=False)


def _pillars():
    spec = importlib.util.spec_from_file_location("daily_run", ROOT / "scripts" / "daily_run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.PILLARS, module.PALETTE_ORDER


def _verdict_text(review: dict[str, Any]) -> str:
    issues = review.get("issues") or []
    if review.get("approved"):
        return "Passed."
    first = issues[0] if issues else "Flagged."
    return first if isinstance(first, str) else json.dumps(first, ensure_ascii=False)[:160]


def _run(run_id: str) -> None:
    from .models import ContentDraft  # noqa: F401  (keeps import errors inside the run)
    from .pipeline import ContentPipeline
    from .self_review import SelfReviewAgent
    from .ai_content import ARCHITECTURE_PASS, make_content

    emit("head", "working", "New post started. Opening the brief and the owner's rules.", run_id)
    pillars, palette_order = _pillars()
    index = (datetime.now().toordinal() + int(time.time() // 60)) % len(pillars)
    name, brief, _layout, _palette = pillars[index]
    lessons, banned = owner_decisions.lessons(), owner_decisions.banned_phrases()
    brief_path = INPUTS_DIR / "trends" / "studio_brief.md"
    brief_path.write_text(f"# Studio brief {run_id}\n\nPillar: {name}\n\n{brief}\n", encoding="utf-8")
    emit("head", "done", f"Brief assigned: {name}. {len(lessons)} owner lessons and {len(banned)} banned phrases apply.",
         run_id, pillar=name, brief=brief)
    emit("memory", "done", f"Handed the team {len(lessons)} lessons from your past decisions.", run_id,
         lessons=lessons[-5:], banned=banned)

    pipe = ContentPipeline()
    ctx = pipe.context

    emit("trend", "working", "Reading scout notes and current content patterns.", run_id)
    trend = pipe.trend_research.run(ctx, brief_path.read_text(encoding="utf-8"), "Instagram")
    angles = (trend.get("content_angles") or [])[:3]
    emit("trend", "done", f"Trend report ready ({trend.get('mode')}). " + (f"Top angle: {angles[0]}" if angles else "Using the brief."),
         run_id, angles=angles, patterns=(trend.get("usable_patterns") or [])[:3])

    emit("copy", "working", "Writing the hook and caption in the brand voice.", run_id)
    draft = pipe.strategy.run(ctx, brief_path.read_text(encoding="utf-8"), "Instagram", "post", trend_report=trend)
    emit("copy", "done", f"Draft ready: “{draft.hook}”", run_id, hook=draft.hook, caption=draft.caption)

    text_ok, history = False, []
    for attempt in range(1, 4):
        reviews = []
        for agent_id, agent in (("critic", pipe.critic), ("facts", pipe.fact_checker), ("legal", pipe.legal)):
            emit(agent_id, "working", f"Round {attempt}: reviewing the draft.", run_id)
            review = agent.run(draft, ctx)
            reviews.append(review)
            emit(agent_id, "done" if review.get("approved") else "flagged", f"Round {attempt}: {_verdict_text(review)}", run_id)
        history.append({"attempt": attempt, "reviews": reviews})
        if all(r.get("approved") for r in reviews):
            text_ok = True
            break
        emit("fix", "working", "Fixing what the reviewers flagged.", run_id)
        draft = pipe.auto_fix.run(draft, reviews, ctx)
        emit("fix", "done", f"Revised hook: “{draft.hook}”", run_id, hook=draft.hook)
    if not text_ok:
        emit("head", "flagged", "Copy still has open flags after 3 rounds. Sending it with the flags shown.", run_id)

    left = budget()["left"]
    emit("art", "working", f"Picking a new creative concept and a real render ({left} paid image(s) left today).", run_id)

    def on_step(kind, attempt, *info):
        if kind == "generating":
            emit("art", "working", f"Creating concept “{info[0]}” from render {info[1]} (try {attempt}).", run_id)
        else:
            ok = info[0] >= info[1]
            emit("qa", "done" if ok else "flagged",
                 f"Building match {info[0]:.2f} (pass {info[1]:.2f}). " + ("The building is unchanged." if ok else "The building drifted; retrying."),
                 run_id, score=info[0])

    made = make_content(f"daily-{run_id}", mood=f"Theme of the post: {name}.", attempts=min(2, max(1, left)), on_step=on_step)
    if made.get("status") in ("ok", "architecture_failed"):
        emit("art", "done", f"Image ready: {made['concept']} on {Path(made['source_image']).name}.", run_id, png=made.get("png"))
    else:
        emit("art", "error", f"No image: {made.get('error') or made.get('status')}", run_id)

    folder = OUTPUTS_DIR / "daily" / run_id
    folder.mkdir(parents=True, exist_ok=True)
    png = folder / "post.png"
    if made.get("png"):
        shutil.copyfile(made["png"], png)
    caption = f"{draft.hook}\n\n{draft.caption}\n\n{' '.join(draft.hashtags)}\n"
    (folder / "caption.txt").write_text(caption, encoding="utf-8")

    building_ok = made.get("status") == "ok"
    report = {"post_id": f"daily-{run_id}", "date": run_id[:10], "source": "studio", "kind": "ai_content", "pillar": name,
              "layout": f"ai:{made.get('concept')}", "concept": made.get("concept"), "scene": made.get("scene"),
              "source_image": made.get("source_image"), "architecture_score": made.get("architecture_score"),
              "model": made.get("model"),
              "hook": draft.hook, "caption": draft.caption, "hashtags": draft.hashtags,
              "text_guards": [(r["agent"], r["approved"]) for r in history[-1]["reviews"]] if history else [],
              "text_approved": text_ok, "design_status": "approved" if building_ok else "needs_human_review",
              "visual_checks": {"image_made": bool(made.get("png")), "building_unchanged": building_ok},
              "trend_mode": trend.get("mode"), "lessons_applied": len(lessons), "banned_phrases": banned}

    emit("cd", "working", "Scoring the finished post the way you would.", run_id)
    self_review = SelfReviewAgent().run(report, None)
    report["agent_review"] = self_review
    emit("cd", "done" if self_review["decision"] == "approved" else "flagged",
         f"{self_review['decision'].title()} at {self_review['score']}/10. {self_review['reason']}", run_id,
         score=self_review["score"], scores=self_review["scores"])
    (folder / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    emit("head", "done", "Post is ready and sent to you for approval.", run_id, post_id=report["post_id"])
    emit("owner", "waiting", "Waiting for your approval.", run_id, post_id=report["post_id"])


def record_owner_decision(post_id: str, decision: str, reason: str, category: str, banned_phrase: str) -> dict[str, Any]:
    """Owner's verdict from Studio HQ: saved, learned from, and shown live to the team."""
    from .design_history import record_spec

    folder = OUTPUTS_DIR / "daily" / post_id.removeprefix("daily-")
    report = json.loads((folder / "report.json").read_text(encoding="utf-8")) if (folder / "report.json").exists() else {}
    context = {k: report.get(k) for k in ("hook", "caption", "layout", "palette", "pillar", "date")}
    entry = owner_decisions.add_decision(post_id, decision, reason, category, banned_phrase, context)
    if entry["decision"] == "approved" and report.get("design_spec"):
        record_spec(post_id, report["design_spec"], "approved")
    if entry["decision"] == "approved" and report.get("concept"):
        from . import design_history
        design_history.record(post_id, {"layout": f"ai:{report['concept']}", "photo": Path(report.get("source_image") or "").stem,
                                        "type_treatment": "ai-content", "concept": report["concept"]}, "approved")
    run_id = post_id.removeprefix("daily-")
    if entry["decision"] == "approved":
        emit("owner", "done", "Approved. Ready to publish by hand.", run_id, post_id=post_id)
        emit("memory", "done", "Saved as a quality bar. The next post must still be a completely new design.", run_id)
    else:
        emit("owner", "flagged", f"Denied ({category}): {reason}", run_id, post_id=post_id)
        note = "Queued for a brand-new AI image (uses paid credits only when you run it). " if category in owner_decisions.POSTER_CATEGORIES else ""
        emit("memory", "done", f"{note}Lesson saved; every future post will avoid it.", run_id,
             lessons=len(owner_decisions.lessons()))
    return entry


def history_posts(limit: int = 12) -> list[dict[str, Any]]:
    by_id = {d["post_id"]: d for d in owner_decisions.load_decisions()}
    posts = []
    for folder in sorted((OUTPUTS_DIR / "daily").glob("*"), key=lambda p: p.name, reverse=True):
        path = folder / "report.json"
        if not path.exists():
            continue
        report = json.loads(path.read_text(encoding="utf-8"))
        post_id = report.get("post_id") or f"daily-{folder.name}"
        posts.append({"post_id": post_id, "folder": folder.name, "pillar": report.get("pillar"), "hook": report.get("hook"),
                      "caption": report.get("caption"), "hashtags": report.get("hashtags", []),
                      "image": f"/api/studio/image/{folder.name}" if (folder / "post.png").exists() else None,
                      "agent_review": report.get("agent_review"), "visual_checks": report.get("visual_checks"),
                      "design_spec": report.get("design_spec"), "decision": by_id.get(post_id),
                      "kind": report.get("kind", "poster"), "concept": report.get("concept"), "scene": report.get("scene"),
                      "architecture_score": report.get("architecture_score"), "model": report.get("model"),
                      "source_url": f"/api/studio/source/{Path(report['source_image']).name}" if report.get("source_image") else None})
        if len(posts) >= limit:
            break
    return posts


def image_path(folder_name: str) -> Path | None:
    path = (OUTPUTS_DIR / "daily" / Path(folder_name).name / "post.png")
    return path if path.exists() else None


def source_path(name: str) -> Path | None:
    """A real render the AI started from, for the side-by-side building check."""
    from .paths import ASSETS_DIR
    for folder in (ASSETS_DIR / "renders", ASSETS_DIR / "original"):
        path = folder / Path(name).name
        if path.exists():
            return path
    return None
