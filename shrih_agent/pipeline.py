from datetime import datetime
from pathlib import Path
from typing import Any

from .agents import (
    AgentContext,
    ArchitectureGuardAgent,
    AutoFixAgent,
    ContentStrategistAgent,
    CriticAgent,
    FactCheckerAgent,
    LegalReraAgent,
    PreferenceLearningAgent,
    TrendResearchAgent,
)
from .design_agent import DesignAgent
from .gemini import GeminiImageClient
from .image_prompt import build_image_edit_prompt
from .io import read_text, write_json, write_text
from .llm import default_client
from .memory import load_memory, save_preferences
from .models import ContentDraft
from .paths import OUTPUTS_DIR
from .renderer import render_instagram_post
from .visual_review import VisualReviewerAgent


class ContentPipeline:
    def __init__(self) -> None:
        self.context = AgentContext(memory=load_memory(), llm=default_client())
        self.trend_research = TrendResearchAgent()
        self.strategy = ContentStrategistAgent()
        self.critic = CriticAgent()
        self.fact_checker = FactCheckerAgent()
        self.legal = LegalReraAgent()
        self.architecture = ArchitectureGuardAgent()
        self.auto_fix = AutoFixAgent()
        self.preference_learning = PreferenceLearningAgent()
        self.image_client = GeminiImageClient()
        self.designer = DesignAgent()
        self.visual_reviewer = VisualReviewerAgent()

    def run(
        self,
        brief_path: Path,
        platform: str = "Instagram",
        content_format: str = "post",
        max_attempts: int = 3,
        render_image: bool = False,
        image_path: Path | None = None,
        generate_image: bool = False,
        max_image_attempts: int = 3,
        design_layout: str | None = None,
        palette: str = "navy",
    ) -> dict[str, Any]:
        brief = read_text(brief_path)
        trend_report = self.trend_research.run(self.context, brief, platform)
        draft = self.strategy.run(self.context, brief, platform, content_format, trend_report=trend_report)

        draft, text_history, text_approved = self._text_review_loop(draft, max_attempts)

        image_generation = None
        if generate_image and image_path:
            image_generation = self.generate_and_verify_image(draft, image_path, max_image_attempts)

        design = None
        if design_layout:
            design = self.design_and_review(draft, design_layout, palette=palette)

        status = self._overall_status(text_approved, image_generation, design)
        hero_image = image_path
        if image_generation and image_generation.get("status") == "approved":
            hero_image = Path(image_generation["final_image"])

        return self._save(status, draft, text_history, render_image, hero_image, trend_report, image_generation, design)

    def design_and_review(self, draft: ContentDraft, layout: str, source_image: Path | None = None,
                          max_attempts: int = 2, palette: str = "navy") -> dict[str, Any]:
        """Design agent builds the post, the visual reviewer inspects the render.
        A failed review retries once in safe mode; defects are logged to mistake memory."""
        attempts: list[dict[str, Any]] = []
        for attempt in range(1, max_attempts + 1):
            built = self.designer.build(draft, self.context.memory.brand, self.context.memory.project,
                                        layout=layout, source_image=source_image, safe_mode=attempt > 1, palette=palette)
            review = self.visual_reviewer.run(built, self.context.memory.project)
            attempts.append({"attempt": attempt, "design": built, "review": review})
            if review["approved"]:
                if built.get("spec"):
                    from .design_history import record_spec
                    record_spec(Path(built["png"]).stem, built["spec"], "produced")
                return {"status": "approved", "layout": layout, "png": built["png"], "html": built["html"],
                        "spec": built.get("spec"), "attempts": attempts}
            if built.get("status") == "blocked":
                break
        return {"status": "needs_human_review", "layout": layout,
                "png": attempts[-1]["design"].get("png"), "attempts": attempts}

    def generate_and_verify_image(
        self,
        draft: ContentDraft,
        reference_image_path: Path,
        max_attempts: int = 3,
        extra_corrective_instructions: list[str] | None = None,
    ) -> dict[str, Any]:
        """Edit the real reference photo, then verify the result didn't hallucinate
        the building's structure. Retries with corrective instructions on failure;
        stops immediately (without burning retries) on a non-retryable status
        like a missing key, quota, or a safety block."""
        attempts: list[dict[str, Any]] = []
        corrective = list(extra_corrective_instructions or [])

        for attempt in range(1, max_attempts + 1):
            prompt = build_image_edit_prompt(
                draft.image_edit_brief, self.context.memory.brand, extra_corrective_instructions=corrective
            )
            edit_result = self.image_client.edit_image(reference_image_path, prompt)

            if edit_result.status != "ok":
                attempts.append({"attempt": attempt, "stage": "edit", "status": edit_result.status,
                                  "error": edit_result.error_message, "prompt": prompt})
                return {
                    "status": "unavailable" if edit_result.status == "unavailable" else "failed",
                    "reason": edit_result.status,
                    "error": edit_result.error_message,
                    "attempts": attempts,
                }

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            candidate_path = OUTPUTS_DIR / "generated" / f"candidate_{timestamp}.png"
            candidate_path.parent.mkdir(parents=True, exist_ok=True)
            candidate_path.write_bytes(edit_result.image_bytes)

            verdict = self.architecture.run(reference_image_path, candidate_path)
            attempts.append({
                "attempt": attempt, "stage": "verify", "prompt": prompt,
                "candidate_image": str(candidate_path), "verdict": verdict,
            })

            if verdict.get("approved"):
                return {"status": "approved", "final_image": str(candidate_path), "attempts": attempts}

            if verdict.get("mode") == "manual_required":
                return {"status": "needs_manual_checklist", "final_image": str(candidate_path),
                        "checklist_items": verdict.get("checklist_items"), "attempts": attempts}

            if verdict.get("mode", "").startswith("gemini_") and verdict.get("mode") not in ("gemini_vision",):
                # unavailable / quota_exceeded / blocked / error on the vision call itself -- not retryable
                return {"status": "unavailable", "reason": verdict.get("mode"), "error": verdict.get("error"),
                        "final_image": str(candidate_path), "attempts": attempts}

            corrective = list(verdict.get("issues", [])) or ["The previous attempt changed the building's structure. Preserve it exactly."]

        return {"status": "needs_human_review", "attempts": attempts,
                "final_image": attempts[-1].get("candidate_image") if attempts else None}

    def regenerate_from_feedback(
        self,
        previous_content: dict[str, Any],
        feedback: str,
        decision: str,
        reference_image_path: Path | None = None,
        max_attempts: int = 3,
        max_image_attempts: int = 3,
        render_image: bool = True,
    ) -> dict[str, Any]:
        """The actual auto-regenerate-on-rejection loop: takes what the human
        didn't like about THIS draft and immediately tries again, rather than
        only remembering the feedback for next time."""
        updated_preferences = self.preference_learning.learn(self.context.memory.preferences, decision, feedback)
        save_preferences(updated_preferences)
        self.context.memory.preferences = updated_preferences

        draft = ContentDraft.from_dict(previous_content)
        synthetic_review = {
            "agent": "human_feedback", "approved": False,
            "issues": [feedback], "fix_instructions": [feedback],
        }
        draft = self.auto_fix.run(draft, [synthetic_review], self.context)

        draft, text_history, text_approved = self._text_review_loop(draft, max_attempts)

        image_generation = None
        if reference_image_path:
            image_generation = self.generate_and_verify_image(
                draft, reference_image_path, max_image_attempts, extra_corrective_instructions=[feedback]
            )

        base_status = self._overall_status(text_approved, image_generation)
        status = f"regenerated_{base_status}"
        hero_image = reference_image_path
        if image_generation and image_generation.get("status") == "approved":
            hero_image = Path(image_generation["final_image"])

        return self._save(status, draft, text_history, render_image, hero_image, None, image_generation)

    def _text_review_loop(self, draft: ContentDraft, max_attempts: int) -> tuple[ContentDraft, list[dict[str, Any]], bool]:
        history: list[dict[str, Any]] = []
        for attempt in range(1, max_attempts + 1):
            reviews = [
                self.critic.run(draft, self.context),
                self.fact_checker.run(draft, self.context),
                self.legal.run(draft, self.context),
            ]
            history.append({"attempt": attempt, "draft": draft.to_dict(), "reviews": reviews})
            if all(review.get("approved") for review in reviews):
                return draft, history, True
            draft = self.auto_fix.run(draft, reviews, self.context)
        return draft, history, False

    @staticmethod
    def _overall_status(text_approved: bool, image_generation: dict[str, Any] | None,
                        design: dict[str, Any] | None = None) -> str:
        if not text_approved:
            return "needs_human_review"
        if design is not None and design.get("status") != "approved":
            return "needs_human_review"
        if image_generation is None:
            return "approved_internal_review"
        if image_generation.get("status") == "approved":
            return "approved_internal_review"
        return "needs_human_review"

    def _save(
        self,
        status: str,
        draft: ContentDraft,
        history: list[dict[str, Any]],
        render_image: bool,
        image_path: Path | None,
        trend_report: dict[str, Any] | None,
        image_generation: dict[str, Any] | None,
        design: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        rendered_image = None
        if design and design.get("png"):
            rendered_image = {"created": True, "output": design["png"], "size": [1080, 1350],
                              "source_image": "design agent (real renders, no generated building)",
                              "architecture_note": "Real render composed into a layout. No generative edits."}
        elif render_image:
            rendered_image = render_instagram_post(
                draft.to_dict(),
                self.context.memory.brand,
                self.context.memory.project,
                image_path=image_path,
                output_path=OUTPUTS_DIR / "final" / f"instagram_post_{timestamp}.png",
            )
        package = {
            "status": status,
            "final_content": draft.to_dict(),
            "trend_report": trend_report,
            "image_generation": image_generation,
            "design": design,
            "rendered_image": rendered_image,
            "review_history": history,
            "next_step": "Human approval required before posting.",
        }
        write_json(OUTPUTS_DIR / "drafts" / f"agent_content_pack_{timestamp}.json", package)
        write_json(OUTPUTS_DIR / "reviews" / f"agent_review_{timestamp}.json", history[-1]["reviews"])
        write_text(OUTPUTS_DIR / "final" / f"agent_content_pack_{timestamp}.md", self._to_markdown(package))
        return package

    def _to_markdown(self, package: dict[str, Any]) -> str:
        content = package["final_content"]
        hashtags = " ".join(content.get("hashtags", []))
        image_line = ""
        if package.get("rendered_image"):
            image_line = f"Image: {package['rendered_image']['output']}"
        return "\n".join([
            f"# Shrih Plaza Content Pack",
            "",
            f"Status: {package['status']}",
            "",
            f"Platform: {content.get('platform')}",
            f"Format: {content.get('format')}",
            "",
            "## Hook",
            "",
            content.get("hook", ""),
            "",
            "## Caption",
            "",
            content.get("caption", ""),
            "",
            "## Visual Direction",
            "",
            content.get("visual_direction", ""),
            "",
            "## CTA",
            "",
            content.get("cta", ""),
            "",
            "## Hashtags",
            "",
            hashtags,
            "",
            "## Rendered Image",
            "",
            image_line or "No image rendered.",
            "",
        ])
