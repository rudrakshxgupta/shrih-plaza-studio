import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import mistake_memory
from .gemini import GeminiSearchClient, GeminiVisionJudgeClient
from .image_prompt import CHECKLIST_ITEMS, build_architecture_checklist_prompt, category_for_checklist_key
from .llm import LLMClient
from .memory import BrandMemory, approved_facts
from .models import ContentDraft
from . import decisions as owner_decisions
from .trend_scout import merged_scout_notes


FORBIDDEN_PATTERNS = [
    r"\bguaranteed returns?\b",
    r"\bassured profits?\b",
    r"\b100% appreciation\b",
    r"\blowest price guaranteed\b",
    r"\bbest project\b",
    r"\bpossession soon\b",
    r"\blimited units only\b",
    r"\bbuy now\b",
    r"\bbest investment\b",
    r"\b100% returns?\b",
    r"\bguaranteed profits?\b",
    r"\bdouble your money\b",
    # owner (2026-10-02): brands are "opening soon", never "coming" / "coming soon"
    r"\bcoming soon\b",
    r"\b(is|are) coming\b",
]

STRATEGY_PATH = Path(__file__).resolve().parents[1] / "brand-kit" / "content-strategy.md"
OWNERSHIP_WORDS = ("own ", "owning", "ownership", "own your", "own a", "commercial space", "shop availability",
                   "available shops", "enquire", "enquiry")


def content_strategy() -> str:
    """The owner's content strategy: brand -> location -> commercial activity -> ownership -> enquiry."""
    return STRATEGY_PATH.read_text(encoding="utf-8") if STRATEGY_PATH.exists() else ""


@dataclass
class AgentContext:
    memory: BrandMemory
    llm: LLMClient


class ContentStrategistAgent:
    def run(
        self,
        context: AgentContext,
        brief: str,
        platform: str,
        content_format: str,
        trend_report: dict[str, Any] | None = None,
    ) -> ContentDraft:
        brand = context.memory.brand
        project = context.memory.project
        preferences = context.memory.preferences
        project_name = project.get("project_name") or brand.get("brand_name") or "SHRIH PLAZA"
        cta = (brand.get("cta_preferences") or ["Book a site visit"])[0]
        facts = approved_facts(project)

        fallback = {
            "platform": platform,
            "format": content_format,
            "hook": "Where brands arrive, businesses follow.",
            "caption": (
                f"Signed brands are choosing {project_name} on SH-11, Dhuri, a RERA approved commercial destination "
                "with retail shops, offices and central parking. Customers will come for the brands. "
                "You could own the space. Limited SCO spaces are available. "
                f"Enquire for shop availability: {project.get('contact', {}).get('phone', '')}"
            ).strip(),
            "visual_direction": (
                "Use one approved elevation image. Keep the layout minimal with warm ivory space, "
                "deep green panels, gold accent lines, and a clear CTA footer."
            ),
            "cta": "Enquire for shop availability",
            "taglines": [
                "Don't just visit the destination. Own a part of it.",
                "Where recognised brands meet your next opportunity.",
                "See the brands. See the opportunity. Own the space.",
                "Where brands create destinations, and destinations create opportunity.",
                "Be where the next commercial destination takes shape.",
            ],
            "hashtags": ["#ShrihPlaza", "#Dhuri", "#CommercialProperty", "#SCOSpaces", "#PunjabRealEstate"],
            "claims_used": [
                "RERA approved",
                "SH-11, Dhuri",
                "Construction is nearing completion.",
                "Limited SCO spaces are available.",
            ],
            "image_edit_brief": {
                "scene_direction": "Same building, same angle, premium daylight commercial photography feel.",
                "lighting": "Clear daylight with a warm golden-hour tone.",
                "seasonal_elements": [],
                "framing": "Keep the original framing and camera angle.",
            },
        }

        system = (
            "You are the Content Strategy & Real Estate Marketing AI for Shrih Plaza. Follow the owner's content "
            "strategy below exactly: every post moves the viewer BRAND -> LOCATION -> COMMERCIAL ACTIVITY -> "
            "SHOP OWNERSHIP -> ENQUIRY, and the caption must end on Shrih Plaza + commercial space + ownership + "
            "enquiry, never on visiting or enjoying a brand. Premium and confident, never salesy. Also return "
            "5-10 'taglines' across ownership, brand association, location, aspiration, commercial activity and "
            "(only if supported) scarcity. Create original social content using only "
            "approved project facts. Do not invent prices, dates, unit sizes, ROI, distances or brands. "
            "Also produce an image_edit_brief describing only lighting/sky/ambience/seasonal styling for "
            "the building photo -- never describe changing the building's structure, floors, windows, "
            "balconies, entrance or facade."
        )
        user = json.dumps({
            "brief": brief,
            "platform": platform,
            "format": content_format,
            "brand": brand,
            "approved_facts": facts,
            "preferences": preferences,
            "trend_report": trend_report or {},
            "owner_content_strategy": content_strategy(),
            "owner_lessons_never_repeat": owner_decisions.lessons(),
            "owner_banned_phrases": owner_decisions.banned_phrases(),
            "owner_approved_examples": owner_decisions.approved_examples(),
            "required_json_fields": list(fallback.keys()),
        }, ensure_ascii=False)
        result = context.llm.complete_json(system, user, fallback)
        result.setdefault("metadata", {})["taglines"] = result.get("taglines") or fallback["taglines"]
        return ContentDraft.from_dict(result)


class CriticAgent:
    def run(self, draft: ContentDraft, context: AgentContext) -> dict[str, Any]:
        issues: list[str] = []
        score = 10
        data = draft.to_dict()
        text = json.dumps(data, ensure_ascii=False).lower()

        if len(draft.hook) > 72:
            issues.append("Hook is too long for a premium social creative.")
            score -= 1
        if len(draft.caption) > 420:
            issues.append("Caption is too long for first-screen social attention.")
            score -= 1
        if not draft.cta.strip():
            issues.append("CTA is missing.")
            score -= 2
        if "premium" not in text and "commercial" not in text:
            issues.append("Creative does not strongly express premium commercial positioning.")
            score -= 1
        # Owner strategy: the post must end by turning attention into shop ownership and an enquiry.
        tail = draft.caption.lower()[-220:]
        if not any(w in tail for w in OWNERSHIP_WORDS):
            issues.append("Caption does not end on shop ownership and an enquiry (owner content strategy).")
            score -= 2

        approved = score >= 8 and not issues
        return {
            "agent": "critic",
            "score": max(score, 0),
            "approved": approved,
            "issues": issues,
            "fix_instructions": [
                "Make the hook shorter, cleaner and more commercially premium.",
                "Keep one clear CTA and remove low-value wording."
            ] if issues else [],
        }


class FactCheckerAgent:
    def run(self, draft: ContentDraft, context: AgentContext) -> dict[str, Any]:
        project = context.memory.project
        approved_text = " ".join(approved_facts(project)).lower()
        allowed_soft_words = {
            "premium", "commercial", "modern", "visibility", "convenience", "trust",
            "destination", "business", "retail", "food", "leisure", "family", "spaces",
        }
        text_parts = [draft.hook, draft.caption, draft.cta]
        claims: list[dict[str, Any]] = []
        approved = True

        for claim in self._split_claims(" ".join(text_parts)):
            lowered = claim.lower()
            has_number = bool(re.search(r"\b\d+(\.\d+)?\b", lowered))
            risky_fact_word = any(word in lowered for word in [
                "price", "possession", "roi", "return", "rental", "km", "minute", "sq", "rera",
                "approved", "brand", "signed", "domino", "barista", "sagar", "jockey",
                # owner (2026-10-02): no unverified layout claims such as which floor holds shops or offices
                "floor", "storey", "basement", "mezzanine",
            ])
            verified = self._is_verified(lowered, approved_text, project)
            soft = not has_number and any(word in lowered for word in allowed_soft_words)

            if verified:
                status = "verified"
                action = "keep"
            elif risky_fact_word or has_number:
                status = "missing_source"
                action = "rewrite"
                approved = False
            elif soft:
                status = "allowed_soft_marketing"
                action = "keep"
            else:
                status = "allowed_generic"
                action = "keep"

            claims.append({
                "claim": claim,
                "status": status,
                "action": action,
            })

        return {
            "agent": "fact_checker",
            "score": 10 if approved else 0,
            "approved": approved,
            "claims": claims,
        }

    def _split_claims(self, text: str) -> list[str]:
        return [item.strip() for item in re.split(r"(?<=[.!?])\s+", text) if item.strip()]

    def _is_verified(self, lowered: str, approved_text: str, project: dict[str, Any]) -> bool:
        if "shrih plaza" in lowered:
            return True
        if "sh-11" in lowered or "dhuri" in lowered:
            return "sh-11" in approved_text and "dhuri" in approved_text
        if "rera" in lowered:
            return bool(project.get("approval_status", {}).get("rera_approved"))
        phone = str(project.get("contact", {}).get("phone", "")).lower()
        compact_phone = re.sub(r"\D", "", phone)
        compact_claim = re.sub(r"\D", "", lowered)
        if compact_phone and compact_phone in compact_claim:
            return True
        if "sco" in lowered or "retail" in lowered or "office" in lowered:
            return "sco" in approved_text and "retail" in approved_text
        if "parking" in lowered:
            return "parking" in approved_text
        signed_brands = [brand.lower() for brand in project.get("signed_brand_associations", [])]
        count = re.search(r"\b(\d+)\s+(?:signed\s+)?brands?\b", lowered)
        if count and signed_brands:
            return int(count.group(1)) == len(signed_brands)
        return any(brand in lowered for brand in signed_brands)


class LegalReraAgent:
    def run(self, draft: ContentDraft, context: AgentContext) -> dict[str, Any]:
        text = json.dumps(draft.to_dict(), ensure_ascii=False).lower()
        project = context.memory.project
        issues: list[str] = []

        for claim in project.get("forbidden_claims", []):
            if str(claim).lower() in text:
                issues.append(str(claim))
        for pattern in FORBIDDEN_PATTERNS:
            if re.search(pattern, text):
                issues.append(pattern)
        for phrase in owner_decisions.banned_phrases():
            if phrase.lower() in text:
                issues.append(f"owner_banned: {phrase}")

        approved = not issues
        return {
            "agent": "legal_rera",
            "score": 10 if approved else 0,
            "approved": approved,
            "issues": sorted(set(issues)),
            "fix_instructions": ["Remove risky sales/legal wording and replace with verified facts."] if issues else [],
        }


class ArchitectureGuardAgent:
    """Verifies a generated image did not hallucinate the building's structure.

    Three modes:
    - no images given: not applicable to this run (text-only content).
    - images given + Gemini available: a real vision-based checklist comparison.
      Any failed item is logged to mistake_memory so future prompts avoid it.
    - images given + no Gemini key: there is no way to actually check, so this
      NEVER silently approves -- it hands back the checklist for a human to
      confirm instead.
    """

    def __init__(self, vision_client: GeminiVisionJudgeClient | None = None) -> None:
        self.vision_client = vision_client or GeminiVisionJudgeClient()

    def run(self, original_image: Path | None = None, candidate_image: Path | None = None) -> dict[str, Any]:
        if not original_image or not candidate_image:
            return {
                "agent": "architecture_guard",
                "mode": "not_applicable",
                "score": 10,
                "approved": True,
                "note": "No image pair supplied for this run.",
            }

        if not self.vision_client.available:
            return {
                "agent": "architecture_guard",
                "mode": "manual_required",
                "score": 0,
                "approved": False,
                "checklist_items": [{"key": key, "label": label} for key, label in CHECKLIST_ITEMS],
                "requires_manual_review": True,
                "note": "No GEMINI_API_KEY configured -- a human must confirm the checklist before this can be approved.",
            }

        verdict = self.vision_client.check_architecture(
            original_image, candidate_image, build_architecture_checklist_prompt()
        )

        if verdict.status != "ok":
            return {
                "agent": "architecture_guard",
                "mode": f"gemini_{verdict.status}",
                "score": 0,
                "approved": False,
                "requires_manual_review": True,
                "error": verdict.error_message,
                "note": "Vision check failed or was unavailable -- treat as unverified, do not auto-post.",
            }

        for key, label in CHECKLIST_ITEMS:
            if verdict.checklist.get(key) is False:
                mistake_memory.append_mistake(
                    category=category_for_checklist_key(key),
                    description=f"{label} failed on a generated image.",
                    avoid_instruction=f"Do not let this happen again: {label.lower()} must match the original reference exactly.",
                    source="architecture_guard_auto",
                )

        return {
            "agent": "architecture_guard",
            "mode": "gemini_vision",
            "score": 10 if verdict.approved else 0,
            "approved": verdict.approved,
            "checklist": verdict.checklist,
            "issues": verdict.issues,
        }


class TrendResearchAgent:
    """Researches current social content patterns before the strategist writes anything.

    With no Gemini key, this is exactly today's behavior: the human-written
    brief IS the trend input. With a key, it grounds a real web search in the
    brief's topic and extracts reusable patterns -- never copying exact text,
    per agents/trend_research_agent.md.
    """

    def __init__(self, search_client: GeminiSearchClient | None = None) -> None:
        self.search_client = search_client or GeminiSearchClient()

    def run(self, context: AgentContext, raw_brief: str, platform: str) -> dict[str, Any]:
        fallback = {
            "trend_summary": raw_brief.strip(),
            "usable_patterns": [],
            "avoid_copying": [],
            "recommended_content_formats": [platform],
            "content_angles": [],
            "sources": [],
            "mode": "manual_brief",
        }

        scout = merged_scout_notes()
        if scout["files"]:
            fallback["usable_patterns"] = list(scout["usable_patterns"])
            fallback["content_angles"] = list(scout["content_angles"])
            fallback["avoid_copying"] = list(scout["avoid_copying"])
            fallback["recommended_content_formats"] = scout["recommended_content_formats"] or [platform]
            fallback["scout_snapshots"] = scout["files"]
            fallback["mode"] = "manual_brief+scout"

        if not self.search_client.available:
            return fallback

        system = (
            "You are the Shrih Plaza trend research agent. Use live web search to find current social "
            "media content patterns (reels, ads, campaigns) for premium commercial real estate or retail "
            "brands. Extract reusable creative patterns -- never copy exact text, layout, or a specific "
            "competitor's brand creative."
        )
        user = json.dumps({
            "platform": platform,
            "brief_or_topic": raw_brief,
            "required_json_fields": [
                "trend_summary", "usable_patterns", "avoid_copying",
                "recommended_content_formats", "content_angles",
            ],
        }, ensure_ascii=False)
        result = self.search_client.grounded_complete_json(system, user, fallback)

        if result.status != "ok":
            merged = dict(fallback)
            merged["mode"] = f"fallback_{result.status}"
            if result.error_message:
                merged["error"] = result.error_message
            return merged

        data = dict(result.data)
        data["sources"] = result.grounding_sources
        data["mode"] = "gemini_grounded"
        return data


class AutoFixAgent:
    def run(self, draft: ContentDraft, reviews: list[dict[str, Any]], context: AgentContext) -> ContentDraft:
        data = draft.to_dict()
        issue_text = json.dumps(reviews, ensure_ascii=False).lower()

        if "hook is too long" in issue_text:
            data["hook"] = _shorten_hook(data["hook"])
        if "missing_source" in issue_text:
            data["caption"] = self._remove_risky_numbers(data["caption"])
            data["caption"] = data["caption"].replace("guaranteed", "").replace("assured", "")
        for pattern in FORBIDDEN_PATTERNS:
            data["caption"] = re.sub(pattern, "premium commercial opportunity", data["caption"], flags=re.IGNORECASE)

        for phrase in owner_decisions.banned_phrases():
            for key in ("hook", "caption"):
                data[key] = _remove_phrase(data[key], phrase)

        if "RERA approved" not in data["caption"] and context.memory.project.get("approval_status", {}).get("rera_approved"):
            data["caption"] = "RERA approved. " + data["caption"]

        return ContentDraft.from_dict(data)

    def _remove_risky_numbers(self, value: str) -> str:
        return re.sub(
            r"\b\d+(\.\d+)?\s*(km|minutes|min|sq\.?\s*ft\.?|%|percent|crore|cr|lakh|lac)\b",
            "",
            value,
            flags=re.IGNORECASE,
        )


def _shorten_hook(hook: str, limit: int = 60) -> str:
    """Cut a long hook at a word or clause boundary, never mid-word, and never end on a joining word."""
    first_clause = hook.split(",")[0].strip()
    if 3 <= len(first_clause.split()) and len(first_clause) <= limit:
        return first_clause.rstrip(".") + "."
    words, kept = hook.split(), []
    for word in words:
        if len(" ".join(kept + [word])) > limit:
            break
        kept.append(word)
    joins = {"and", "or", "with", "on", "in", "the", "a", "of", "for"}
    cut = max((i for i, w in enumerate(kept) if w.lower().strip(",") in joins and i >= 3), default=None)
    if cut is not None and len(words) > len(kept):
        kept = kept[:cut]
    while kept and kept[-1].lower().strip(",") in joins:
        kept.pop()
    return " ".join(kept).rstrip(",") + "."


def _remove_phrase(text: str, phrase: str) -> str:
    """Remove a banned phrase with its joining word, then repair the leftover punctuation."""
    p = re.escape(phrase)
    text = re.sub(rf"(,\s*|\s+(and|with|or)\s+)(an?\s+|the\s+)?{p}", "", text, flags=re.IGNORECASE)
    text = re.sub(rf"(an?\s+|the\s+)?{p}[!?.]?(\s*,|\s+and\b)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r",(\s*,)+", ",", text)
    text = re.sub(r"(,|\s+(and|with|or))\s*([.!?])", r"\3", text)
    text = re.sub(r"\s+([.,!?])", r"\1", text)
    text = re.sub(r"^[\s.,!?]+", "", text)
    text = re.sub(r"([.!?])\s*[.!?]+", r"\1", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text[:1].upper() + text[1:] if text else text


class PreferenceLearningAgent:
    def learn(self, preferences: dict[str, Any], decision: str, feedback: str) -> dict[str, Any]:
        lowered = feedback.lower()
        if any(word in lowered for word in ["flashy", "loud", "crowded", "too much"]):
            lesson = "Prefer cleaner, more premium layouts with less visual noise and less text."
            confidence = 0.8
        elif any(word in lowered for word in ["premium", "luxury", "clean", "minimal"]):
            lesson = "Use a premium, clean, minimal visual direction for future creatives."
            confidence = 0.75
        elif decision == "approved":
            lesson = "User approved this direction; reuse similar structure, tone and restraint."
            confidence = 0.7
        else:
            lesson = "Avoid repeating this rejected direction unless the user asks for it."
            confidence = 0.65

        record = {
            "decision": decision,
            "feedback": feedback,
            "lesson": lesson,
            "applies_to": ["real estate social content"],
            "confidence": confidence,
        }
        if decision == "approved":
            preferences.setdefault("approved_patterns", []).append(feedback)
        else:
            preferences.setdefault("rejected_patterns", []).append(feedback)
        preferences.setdefault("learned_lessons", []).append(record)
        return preferences
