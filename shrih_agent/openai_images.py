"""OpenAI image client: GPT Image 2.5 Flare edits of the real renders.

Owner decisions (2026-09-30): images come from the OpenAI API (Azure AI Foundry is no
longer used). Flare at medium quality is the default: in a side-by-side test it kept the
building as exactly as the premium Sunburst model, faster and cheaper. OpenAI is for
images only; captions, reviews and checks are done by Claude.

Credits are paid and limited, so every image counts against a daily and a monthly cap
(OPENAI_IMAGE_DAILY_LIMIT, OPENAI_IMAGE_MONTHLY_LIMIT), and a call over the cap never
reaches OpenAI. Settings come from the environment or the git-ignored .env file.
"""

import base64
import json
import mimetypes
import os
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .paths import ROOT

API_URL = "https://api.openai.com/v1/images/edits"
USAGE_PATH = ROOT / "memory" / "image_usage.json"

ARCHITECTURE_LOCK = (
    "This is a real commercial building, Shrih Plaza. Keep the building exactly as it is: same outline, "
    "floor count, window grid, columns, facade materials, signboard positions, entrance, proportions, "
    "camera angle and framing. Do not redraw, move, add or remove any part of the building. "
    "Change only what is asked below."
)


def load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def usage() -> dict:
    """Paid images made today and this month, with the caps."""
    load_dotenv()
    today = date.today().isoformat()
    days = json.loads(USAGE_PATH.read_text(encoding="utf-8")).get("days", {}) if USAGE_PATH.exists() else {}
    return {"today": days.get(today, 0), "month": sum(n for d, n in days.items() if d[:7] == today[:7]),
            "daily_limit": int(os.getenv("OPENAI_IMAGE_DAILY_LIMIT", "3")),
            "monthly_limit": int(os.getenv("OPENAI_IMAGE_MONTHLY_LIMIT", "60")), "days": days}


def budget_left() -> int:
    u = usage()
    return max(0, min(u["daily_limit"] - u["today"], u["monthly_limit"] - u["month"]))


def _count_image() -> None:
    days = usage()["days"]
    today = date.today().isoformat()
    days[today] = days.get(today, 0) + 1
    USAGE_PATH.write_text(json.dumps({"note": "Paid OpenAI images per day. Caps: OPENAI_IMAGE_DAILY_LIMIT, "
                                               "OPENAI_IMAGE_MONTHLY_LIMIT.", "days": days}, indent=2), encoding="utf-8")


@dataclass
class ImageResult:
    status: str  # ok | unavailable | budget_exceeded | no_credits | quota_exceeded | blocked | error
    image_bytes: bytes | None = None
    error: str = ""
    prompt: str = ""


class OpenAIImageClient:
    def __init__(self) -> None:
        load_dotenv()
        self.key = os.getenv("OPENAI_API_KEY", "")
        self.deployment = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2.5-flare")
        self.quality = os.getenv("OPENAI_IMAGE_QUALITY", "medium")

    @property
    def available(self) -> bool:
        return bool(self.key)

    def edit(self, image_path: Path, instruction: str, size: str = "auto", quality: str | None = None,
             raw_prompt: bool = False) -> ImageResult:
        """Edit a real render. The architecture lock is prepended unless the caller's prompt
        carries its own building rule (raw_prompt), as the AI content prompt does."""
        prompt = instruction if raw_prompt else f"{ARCHITECTURE_LOCK}\n\nEdit: {instruction}"
        if not self.available:
            return ImageResult("unavailable", error="OPENAI_API_KEY not set", prompt=prompt)
        if budget_left() <= 0:
            u = usage()
            return ImageResult("budget_exceeded", prompt=prompt, error=(
                f"Image budget reached: {u['today']}/{u['daily_limit']} today, {u['month']}/{u['monthly_limit']} this month."))
        boundary = uuid.uuid4().hex
        fields = {"model": self.deployment, "prompt": prompt, "n": "1", "size": size, "quality": quality or self.quality}
        body = bytearray()
        for name, value in fields.items():
            body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode()
        mime = mimetypes.guess_type(str(image_path))[0] or "image/png"
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{image_path.name}\"\r\n"
                 f"Content-Type: {mime}\r\n\r\n").encode() + image_path.read_bytes() + b"\r\n"
        body += f"--{boundary}--\r\n".encode()
        request = urllib.request.Request(API_URL, data=bytes(body), method="POST", headers={
            "Authorization": f"Bearer {self.key}", "Content-Type": f"multipart/form-data; boundary={boundary}"})
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")[:600]
            status = ("no_credits" if "insufficient_quota" in detail or "credit_balance" in detail else
                      "quota_exceeded" if exc.code == 429 else
                      "blocked" if "moderation" in detail or "safety" in detail or "content_policy" in detail else "error")
            return ImageResult(status, error=f"HTTP {exc.code}: {detail}", prompt=prompt)
        except (urllib.error.URLError, TimeoutError) as exc:
            return ImageResult("error", error=str(exc), prompt=prompt)
        for item in data.get("data", []):
            if item.get("b64_json"):
                _count_image()
                return ImageResult("ok", base64.b64decode(item["b64_json"]), prompt=prompt)
        return ImageResult("error", error=f"no image in response: {str(data)[:300]}", prompt=prompt)
