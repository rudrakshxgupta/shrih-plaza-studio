import json
import os
import urllib.error
import urllib.request
from typing import Any

from .gemini import GeminiClient


class LLMClient:
    def complete_json(self, system: str, user: str, fallback: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class LocalLLMClient(LLMClient):
    def complete_json(self, system: str, user: str, fallback: dict[str, Any]) -> dict[str, Any]:
        return fallback


class OpenAIResponsesClient(LLMClient):
    def __init__(self, model: str | None = None) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-5.5")

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def complete_json(self, system: str, user: str, fallback: dict[str, Any]) -> dict[str, Any]:
        if not self.available:
            return fallback

        payload = {
            "model": self.model,
            "input": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": system + "\nReturn only valid JSON."
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": user
                        }
                    ],
                },
            ],
        }
        request = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return fallback

        text = self._extract_text(data)
        if not text:
            return fallback
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return fallback

    def _extract_text(self, data: dict[str, Any]) -> str:
        chunks: list[str] = []
        for item in data.get("output", []):
            for content in item.get("content", []):
                if content.get("type") in {"output_text", "text"} and content.get("text"):
                    chunks.append(content["text"])
        return "\n".join(chunks).strip()


class GeminiTextClient(LLMClient):
    """JSON completion through Gemini. Plain (ungrounded) text calls need no billing."""

    def __init__(self, model: str | None = None) -> None:
        self.gemini = GeminiClient()
        self.model = model or os.getenv("GEMINI_TEXT_MODEL", "gemini-3.6-flash")

    @property
    def available(self) -> bool:
        return self.gemini.available

    def complete_json(self, system: str, user: str, fallback: dict[str, Any]) -> dict[str, Any]:
        if not self.available:
            return fallback
        body = {
            "systemInstruction": {"parts": [{"text": system + "\nReturn only valid JSON."}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        data, _error, _status = self.gemini._post(self.model, body)
        if not data:
            return fallback
        parsed = GeminiClient._extract_json(GeminiClient._extract_text_parts(data))
        if not isinstance(parsed, dict) or not str(parsed.get("hook", "")).strip() or not str(parsed.get("caption", "")).strip():
            return fallback
        return parsed


def default_client() -> LLMClient:
    client = OpenAIResponsesClient()
    if client.available:
        return client
    gemini = GeminiTextClient()
    if gemini.available:
        return gemini
    return LocalLLMClient()

