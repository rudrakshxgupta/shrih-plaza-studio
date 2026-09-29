"""Azure AI Foundry image client: gpt-image-2.5-flare edits of the real renders.

Owner decisions (2026-09-29): images are edited on Azure AI Foundry with the model that
is best for the credits spent. Side by side on the same relight, gpt-image-2.5-flare at
medium quality kept the building as exactly as gpt-image-2.5-sunburst, about twice as fast
and at a lower price, so Flare at medium is the default. Captions, reviews and checks are
done by Claude, not a Foundry text model.

The building must never change: every edit prompt carries the architecture lock,
and the result still has to pass the architecture checks before it is used.
Settings come from the environment or a git-ignored .env file:
FOUNDRY_ENDPOINT, FOUNDRY_API_KEY, FOUNDRY_IMAGE_DEPLOYMENT, FOUNDRY_IMAGE_QUALITY.
"""

import base64
import json
import mimetypes
import os
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path

from .paths import ROOT

ARCHITECTURE_LOCK = (
    "This is a real commercial building, Shrih Plaza. Keep the building exactly as it is: same outline, "
    "floor count, window grid, columns, facade materials, signboard positions, entrance, proportions, "
    "camera angle and framing. Do not redraw, move, add or remove any part of the building. "
    "Change only what is asked below."
)


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass
class FoundryImageResult:
    status: str  # ok | unavailable | quota_exceeded | blocked | error
    image_bytes: bytes | None = None
    error: str = ""
    prompt: str = ""


class FoundryImageClient:
    def __init__(self) -> None:
        _load_dotenv()
        self.endpoint = os.getenv("FOUNDRY_ENDPOINT", "").rstrip("/")
        self.key = os.getenv("FOUNDRY_API_KEY", "")
        self.deployment = os.getenv("FOUNDRY_IMAGE_DEPLOYMENT", "gpt-image-2.5-flare")
        self.api_version = os.getenv("FOUNDRY_IMAGE_API_VERSION", "2025-04-01-preview")
        self.quality = os.getenv("FOUNDRY_IMAGE_QUALITY", "medium")

    @property
    def available(self) -> bool:
        return bool(self.endpoint and self.key)

    def edit(self, image_path: Path, instruction: str, size: str = "auto", quality: str | None = None) -> FoundryImageResult:
        """Edit a real render. The architecture lock is always prepended to the instruction."""
        prompt = f"{ARCHITECTURE_LOCK}\n\nEdit: {instruction}"
        if not self.available:
            return FoundryImageResult("unavailable", error="FOUNDRY_ENDPOINT / FOUNDRY_API_KEY not set", prompt=prompt)
        boundary = uuid.uuid4().hex
        fields = {"prompt": prompt, "n": "1", "size": size, "quality": quality or self.quality}
        body = bytearray()
        for name, value in fields.items():
            body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode()
        mime = mimetypes.guess_type(str(image_path))[0] or "image/png"
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{image_path.name}\"\r\n"
                 f"Content-Type: {mime}\r\n\r\n").encode() + image_path.read_bytes() + b"\r\n"
        body += f"--{boundary}--\r\n".encode()
        url = f"{self.endpoint}/openai/deployments/{self.deployment}/images/edits?api-version={self.api_version}"
        request = urllib.request.Request(url, data=bytes(body), method="POST", headers={
            "api-key": self.key, "Content-Type": f"multipart/form-data; boundary={boundary}"})
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")[:600]
            status = "quota_exceeded" if exc.code == 429 else "blocked" if "content_policy" in detail or "safety" in detail else "error"
            return FoundryImageResult(status, error=f"HTTP {exc.code}: {detail}", prompt=prompt)
        except (urllib.error.URLError, TimeoutError) as exc:
            return FoundryImageResult("error", error=str(exc), prompt=prompt)
        for item in data.get("data", []):
            if item.get("b64_json"):
                return FoundryImageResult("ok", base64.b64decode(item["b64_json"]), prompt=prompt)
        return FoundryImageResult("error", error=f"no image in response: {str(data)[:300]}", prompt=prompt)
