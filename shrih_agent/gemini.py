"""Low-level Gemini API client: image editing, search-grounded text, vision review.

Plain ``urllib`` REST calls against the Gemini API, mirroring the style of
``llm.OpenAIResponsesClient``: no SDK dependency, and every failure mode
(missing key, HTTP error, safety block, unparseable JSON) becomes a ``status``
field on the result instead of an exception, so callers never crash and never
have to guess whether a result is trustworthy.
"""

import base64
import json
import mimetypes
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"

# Statuses every Gemini call can end in. "ok" is the only one downstream code
# should treat as usable output.
STATUS_OK = "ok"
STATUS_UNAVAILABLE = "unavailable"  # no API key configured
STATUS_QUOTA_EXCEEDED = "quota_exceeded"  # 429, or 403 that reads like billing
STATUS_BLOCKED = "blocked"  # safety filter: HTTP 200, no content
STATUS_ERROR = "error"  # anything else (network, bad key, malformed response)


def _classify_error(status: int | None, message: str) -> str:
    lowered = message.lower()
    if status == 429:
        return STATUS_QUOTA_EXCEEDED
    if status in (402, 403) and any(
        word in lowered for word in ["billing", "quota", "exceeded", "permission"]
    ):
        return STATUS_QUOTA_EXCEEDED
    return STATUS_ERROR


@dataclass
class ImageEditResult:
    status: str
    image_bytes: bytes | None = None
    mime_type: str = "image/png"
    model_text: str = ""
    error_message: str = ""
    prompt_used: str = ""


@dataclass
class GroundedTextResult:
    status: str
    data: dict[str, Any] = field(default_factory=dict)
    grounding_sources: list[dict[str, str]] = field(default_factory=list)
    web_search_queries: list[str] = field(default_factory=list)
    error_message: str = ""


@dataclass
class ArchitectureVerdict:
    status: str
    approved: bool = False
    checklist: dict[str, bool] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    raw_text: str = ""
    error_message: str = ""


class GeminiClient:
    """Shared plumbing: auth, the generateContent call, and error classification."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def _post(self, model: str, body: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None, int | None]:
        """POST to {model}:generateContent. Returns (data, error_message, http_status)."""
        url = f"{GEMINI_API_BASE}/models/{model}:generateContent"
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "x-goog-api-key": self.api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.loads(response.read().decode("utf-8")), None, response.status
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")[:800]
            return None, detail, exc.code
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            return None, str(exc), None

    @staticmethod
    def _extract_text_parts(data: dict[str, Any]) -> str:
        chunks: list[str] = []
        for candidate in data.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                if "text" in part:
                    chunks.append(part["text"])
        return "\n".join(chunks).strip()

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any] | None:
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _inline_image_part(path: Path) -> dict[str, Any]:
        mime_type = mimetypes.guess_type(str(path))[0] or "image/jpeg"
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        return {"inlineData": {"mimeType": mime_type, "data": data}}


class GeminiImageClient(GeminiClient):
    """Edits a real reference photo instead of generating one from scratch."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        super().__init__(api_key)
        # "gemini-2.5-flash-image" (Nano Banana) still exists but is a preview
        # alias with its own free-tier quota row; 3.1 is the current generation.
        self.model = model or os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")

    def edit_image(self, reference_image_path: Path, prompt: str) -> ImageEditResult:
        if not self.available:
            return ImageEditResult(status=STATUS_UNAVAILABLE, prompt_used=prompt)
        if not reference_image_path.exists():
            return ImageEditResult(
                status=STATUS_ERROR,
                error_message=f"reference image not found: {reference_image_path}",
                prompt_used=prompt,
            )

        body = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        self._inline_image_part(reference_image_path),
                        {"text": prompt},
                    ],
                }
            ],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
        }
        data, error, status = self._post(self.model, body)
        if data is None:
            return ImageEditResult(
                status=_classify_error(status, error or ""),
                error_message=error or "unknown error",
                prompt_used=prompt,
            )

        block_reason = data.get("promptFeedback", {}).get("blockReason")
        if block_reason:
            return ImageEditResult(
                status=STATUS_BLOCKED,
                error_message=f"prompt blocked: {block_reason}",
                prompt_used=prompt,
            )

        candidates = data.get("candidates", [])
        if candidates and candidates[0].get("finishReason") not in (None, "STOP"):
            return ImageEditResult(
                status=STATUS_BLOCKED,
                error_message=f"generation stopped: {candidates[0].get('finishReason')}",
                prompt_used=prompt,
            )

        image_bytes: bytes | None = None
        mime_type = "image/png"
        model_text_parts: list[str] = []
        for candidate in candidates:
            for part in candidate.get("content", {}).get("parts", []):
                inline = part.get("inlineData")
                if inline and inline.get("data") and image_bytes is None:
                    image_bytes = base64.b64decode(inline["data"])
                    mime_type = inline.get("mimeType", "image/png")
                elif "text" in part:
                    model_text_parts.append(part["text"])

        if image_bytes is None:
            return ImageEditResult(
                status=STATUS_ERROR,
                error_message="no image returned in response",
                model_text="\n".join(model_text_parts),
                prompt_used=prompt,
            )

        return ImageEditResult(
            status=STATUS_OK,
            image_bytes=image_bytes,
            mime_type=mime_type,
            model_text="\n".join(model_text_parts),
            prompt_used=prompt,
        )


class GeminiSearchClient(GeminiClient):
    """Search-grounded JSON completion, for trend research."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        super().__init__(api_key)
        # "gemini-2.5-flash" is retired for new API keys as of this writing;
        # 3.6 is the current default text/vision model at the time of testing.
        self.model = model or os.getenv("GEMINI_TEXT_MODEL", "gemini-3.6-flash")

    def grounded_complete_json(
        self, system: str, user: str, fallback: dict[str, Any]
    ) -> GroundedTextResult:
        if not self.available:
            return GroundedTextResult(status=STATUS_UNAVAILABLE, data=fallback)

        body = {
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "systemInstruction": {
                "parts": [{"text": system + "\nReturn only valid JSON, no markdown fences."}]
            },
            "tools": [{"google_search": {}}],
        }
        data, error, status = self._post(self.model, body)
        if data is None:
            return GroundedTextResult(
                status=_classify_error(status, error or ""),
                data=fallback,
                error_message=error or "unknown error",
            )

        text = self._extract_text_parts(data)
        parsed = self._extract_json(text) if text else None
        if parsed is None:
            return GroundedTextResult(
                status=STATUS_ERROR,
                data=fallback,
                error_message="could not parse JSON from response",
            )

        grounding = {}
        candidates = data.get("candidates", [])
        if candidates:
            grounding = candidates[0].get("groundingMetadata", {})
        sources = [
            {"title": chunk.get("web", {}).get("title", ""), "uri": chunk.get("web", {}).get("uri", "")}
            for chunk in grounding.get("groundingChunks", [])
            if chunk.get("web")
        ]
        return GroundedTextResult(
            status=STATUS_OK,
            data=parsed,
            grounding_sources=sources,
            web_search_queries=grounding.get("webSearchQueries", []),
        )


class GeminiVisionJudgeClient(GeminiClient):
    """Compares two images against the architecture-preservation checklist."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        super().__init__(api_key)
        self.model = model or os.getenv("GEMINI_TEXT_MODEL", "gemini-3.6-flash")

    def check_architecture(
        self, original_path: Path, candidate_path: Path, checklist_prompt: str
    ) -> ArchitectureVerdict:
        if not self.available:
            return ArchitectureVerdict(status=STATUS_UNAVAILABLE)
        if not original_path.exists() or not candidate_path.exists():
            return ArchitectureVerdict(
                status=STATUS_ERROR,
                error_message="original or candidate image file not found",
            )

        body = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": "Original reference image:"},
                        self._inline_image_part(original_path),
                        {"text": "Candidate generated image:"},
                        self._inline_image_part(candidate_path),
                        {"text": checklist_prompt},
                    ],
                }
            ],
        }
        data, error, status = self._post(self.model, body)
        if data is None:
            return ArchitectureVerdict(
                status=_classify_error(status, error or ""),
                error_message=error or "unknown error",
            )

        text = self._extract_text_parts(data)
        parsed = self._extract_json(text) if text else None
        if parsed is None:
            return ArchitectureVerdict(
                status=STATUS_ERROR,
                error_message="could not parse JSON from response",
                raw_text=text,
            )

        checklist = dict(parsed.get("checklist", {}))
        approved = bool(parsed.get("approved")) and all(checklist.values())
        return ArchitectureVerdict(
            status=STATUS_OK,
            approved=approved,
            checklist=checklist,
            issues=list(parsed.get("issues", [])),
            raw_text=text,
        )
