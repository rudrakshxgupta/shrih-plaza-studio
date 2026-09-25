"""Self-review agent: judges a finished post the way the owner would, before the owner sees it.

It scores six criteria from 0 to 10, from the post's text, its automatic check
results and the rendered pixels, then gives approve or deny with the main reasons.
Deterministic on purpose: the same post always gets the same verdict, so its
judgement can be compared with the owner's and with Claude's over time.
"""

import re
from pathlib import Path
from typing import Any

from . import decisions as owner_decisions

APPROVE_AT = 7.5
FACILITY_WORDS = ["parking", "retail shops", "offices", "sco", "brands", "frontage", "highway", "water", "family"]


def _text_zone_brightness(png: Path, layout: str = "hero") -> float | None:
    """Mean brightness (0-255) of the area where the headline and support text sit."""
    try:
        from PIL import Image
    except ImportError:
        return None
    image = Image.open(png).convert("L")
    box = (64, 650, 1016, 900) if layout == "tenants" else (64, 740, 1016, 1150)
    zone = image.crop(box)
    pixels = list(zone.getdata())
    return sum(pixels) / len(pixels)


class SelfReviewAgent:
    def run(self, post: dict[str, Any], png: Path | None) -> dict[str, Any]:
        hook = str(post.get("hook", "")).strip()
        caption = str(post.get("caption", "")).strip()
        checks = post.get("visual_checks") or {}
        scores: dict[str, float] = {}
        notes: list[str] = []

        failed = [k for k, v in checks.items() if not v]
        scores["compliance"] = 10.0 if checks and not failed else 0.0
        if failed:
            notes.append("Failed automatic checks: " + ", ".join(k.replace("_", " ") for k in failed) + ".")
        if post.get("text_approved") is False:
            scores["compliance"] = 0.0
            failed_guards = [a for a, ok in post.get("text_guards", []) if not ok]
            notes.append("Text guards flagged it: " + ", ".join(failed_guards) + ".")
        banned = [b for b in owner_decisions.banned_phrases() if b.lower() in (hook + " " + caption).lower()]
        if banned:
            scores["compliance"] = 0.0
            notes.append(f"Uses a phrase the owner banned: {', '.join(banned)}.")

        words = len(hook.split())
        scores["headline"] = 10.0 if 3 <= words <= 7 else 7.0 if words <= 9 else 4.0
        if words > 9:
            notes.append(f"Headline has {words} words; short headlines work better on a phone.")

        facts = sum(1 for w in FACILITY_WORDS if w in caption.lower())
        scores["one_clear_idea"] = 10.0 if facts <= 3 else 7.0 if facts == 4 else 4.0
        if facts > 3:
            notes.append(f"Caption covers {facts} different selling points; one idea per post reads stronger.")

        length = len(caption)
        scores["caption_length"] = 10.0 if 90 <= length <= 300 else 7.0 if length <= 380 else 4.0
        if length > 300:
            notes.append(f"Caption is {length} characters; aim for under 300.")

        has_cta = "book a site visit" in caption.lower() or "request" in caption.lower() or "call" in caption.lower()
        scores["call_to_action"] = 10.0 if has_cta else 3.0
        if not has_cta:
            notes.append("Caption has no call to action.")

        brightness = _text_zone_brightness(png, str(post.get("layout", "hero"))) if png and png.exists() else None
        if brightness is None:
            scores["text_contrast"] = 7.0
        else:
            scores["text_contrast"] = 10.0 if brightness < 60 else 7.0 if brightness < 90 else 4.0
            if brightness >= 60:
                notes.append(f"Background behind the text is bright (level {brightness:.0f}); white text may be hard to read.")

        weights = {"compliance": 3, "headline": 1.5, "one_clear_idea": 1.5, "caption_length": 1, "call_to_action": 1, "text_contrast": 2}
        total = sum(scores[k] * w for k, w in weights.items()) / sum(weights.values())
        weakest = min(scores.values())
        approved = scores["compliance"] == 10.0 and total >= APPROVE_AT and weakest > 4.0
        reason = " ".join(notes) if notes else "Compliant, short headline, one clear idea, readable text and a call to action."
        return {"agent": "self_review", "decision": "approved" if approved else "denied",
                "score": round(total, 1), "scores": scores, "reason": reason}
