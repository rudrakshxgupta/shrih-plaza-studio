import json
import mimetypes
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shrih_agent import mistake_memory
from shrih_agent.agents import PreferenceLearningAgent
from shrih_agent.image_prompt import CHECKLIST_ITEMS, category_for_checklist_key
from shrih_agent.image_tools import enhance_image_safe
from shrih_agent.io import read_json, write_json
from shrih_agent.memory import load_memory, save_preferences
from shrih_agent.pipeline import ContentPipeline
from shrih_agent.paths import ASSETS_DIR, INPUTS_DIR, MEMORY_DIR, OUTPUTS_DIR, ROOT
from shrih_agent.renderer import render_instagram_post

REFERENCE_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


UI_DIR = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = 8787


class AgentUIHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            return self._send_file(UI_DIR / "index.html")
        if parsed.path.startswith("/static/"):
            return self._send_file(UI_DIR / parsed.path.lstrip("/"))
        if parsed.path == "/api/memory":
            memory = load_memory()
            return self._send_json({
                "brand": memory.brand,
                "project": memory.project,
                "preferences": memory.preferences,
            })
        if parsed.path == "/api/outputs":
            return self._send_json(self._list_outputs())
        if parsed.path == "/api/file":
            query = parse_query(parsed.query)
            requested = Path(query.get("path", ""))
            return self._send_safe_workspace_file(requested)
        if parsed.path == "/api/reference-images":
            return self._send_json(self._list_reference_images())
        if parsed.path == "/api/architecture-checklist":
            return self._send_json({
                "items": [{"key": key, "label": label} for key, label in CHECKLIST_ITEMS],
            })
        return self._send_error(404, "Not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/generate":
            return self._handle_generate()
        if parsed.path == "/api/feedback":
            return self._handle_feedback()
        if parsed.path == "/api/enhance-image":
            return self._handle_enhance_image()
        if parsed.path == "/api/render-post":
            return self._handle_render_post()
        if parsed.path == "/api/save-memory":
            return self._handle_save_memory()
        if parsed.path == "/api/upload-reference-image":
            return self._handle_upload_reference_image()
        if parsed.path == "/api/regenerate":
            return self._handle_regenerate()
        if parsed.path == "/api/architecture-confirm":
            return self._handle_architecture_confirm()
        return self._send_error(404, "Not found")

    def _handle_generate(self):
        data = self._read_json_body()
        brief = str(data.get("brief", "")).strip()
        platform = str(data.get("platform", "Instagram")).strip() or "Instagram"
        content_format = str(data.get("format", "post")).strip() or "post"
        generate_image = bool(data.get("generate_image"))
        reference_image = data.get("reference_image")
        if not brief:
            return self._send_error(400, "Brief is required")

        brief_path = INPUTS_DIR / "trends" / "ui_current_brief.md"
        brief_path.parent.mkdir(parents=True, exist_ok=True)
        brief_path.write_text(brief, encoding="utf-8")

        image_path = Path(reference_image) if reference_image else None
        result = ContentPipeline().run(
            brief_path,
            platform=platform,
            content_format=content_format,
            render_image=True,
            image_path=image_path,
            generate_image=generate_image,
        )
        return self._send_json(result)

    def _handle_regenerate(self):
        data = self._read_json_body()
        decision = str(data.get("decision", "")).strip()
        feedback = str(data.get("feedback", "")).strip()
        content = data.get("content")
        reference_image = data.get("reference_image")
        if decision not in {"needs_changes", "rejected"}:
            return self._send_error(400, "Invalid decision")
        if not feedback:
            return self._send_error(400, "Feedback is required")
        if not isinstance(content, dict):
            return self._send_error(400, "Previous content object is required")

        image_path = Path(reference_image) if reference_image else None
        result = ContentPipeline().regenerate_from_feedback(
            previous_content=content,
            feedback=feedback,
            decision=decision,
            reference_image_path=image_path,
        )
        return self._send_json(result)

    def _handle_architecture_confirm(self):
        data = self._read_json_body()
        checklist = data.get("checklist") or {}
        notes = str(data.get("notes", "")).strip()
        approved = bool(data.get("approved")) and all(bool(value) for value in checklist.values())

        for item in CHECKLIST_ITEMS:
            key, label = item
            if checklist.get(key) is False:
                mistake_memory.append_mistake(
                    category=category_for_checklist_key(key),
                    description=f"Human flagged: {label} failed. {notes}".strip(),
                    avoid_instruction=f"Do not let this happen again: {label.lower()} must match the original reference exactly.",
                    source="human_flagged",
                )

        review_path = OUTPUTS_DIR / "reviews" / f"human_architecture_review_{_timestamp()}.json"
        write_json(review_path, {"approved": approved, "checklist": checklist, "notes": notes})
        return self._send_json({"saved": True, "approved": approved, "review": str(review_path)})

    def _handle_render_post(self):
        data = self._read_json_body()
        content = data.get("content")
        if not isinstance(content, dict):
            return self._send_error(400, "Content object is required")
        memory = load_memory()
        result = render_instagram_post(content, memory.brand, memory.project)
        return self._send_json(result)

    def _handle_feedback(self):
        data = self._read_json_body()
        decision = str(data.get("decision", "")).strip()
        feedback = str(data.get("feedback", "")).strip()
        if decision not in {"approved", "rejected", "needs_changes"}:
            return self._send_error(400, "Invalid decision")
        if not feedback:
            return self._send_error(400, "Feedback is required")

        memory = load_memory()
        updated = PreferenceLearningAgent().learn(memory.preferences, decision, feedback)
        save_preferences(updated)
        return self._send_json({
            "saved": True,
            "preferences": updated,
        })

    def _handle_save_memory(self):
        data = self._read_json_body()
        allowed_files = {
            "brand": MEMORY_DIR / "brand_identity.json",
            "project": MEMORY_DIR / "project_facts.json",
            "preferences": MEMORY_DIR / "preference_memory.json",
        }
        for key, path in allowed_files.items():
            if key in data:
                write_json(path, data[key])
        return self._send_json({"saved": True})

    def _handle_enhance_image(self):
        upload = self._read_multipart_file("image")
        if not upload:
            return self._send_error(400, "Image file is required")
        filename, content = upload
        original = ASSETS_DIR / "original" / filename
        enhanced = ASSETS_DIR / "enhanced" / f"{original.stem}_enhanced{original.suffix}"
        original.parent.mkdir(parents=True, exist_ok=True)
        original.write_bytes(content)

        result = enhance_image_safe(original, enhanced)
        review_path = OUTPUTS_DIR / "reviews" / f"{original.stem}_image_enhancement_review.json"
        write_json(review_path, result)
        return self._send_json({
            "saved": True,
            "original": str(original),
            "enhanced": str(enhanced),
            "review": str(review_path),
            "policy": result["architecture_policy"],
        })

    def _handle_upload_reference_image(self):
        upload = self._read_multipart_file("image")
        if not upload:
            return self._send_error(400, "Image file is required")
        filename, content = upload
        if Path(filename).suffix.lower() not in REFERENCE_IMAGE_EXTENSIONS:
            return self._send_error(400, "Unsupported image type")
        destination = ASSETS_DIR / "original" / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        return self._send_json({"saved": True, "path": str(destination), "name": destination.name})

    def _list_reference_images(self):
        original_dir = ASSETS_DIR / "original"
        images = [
            path for path in original_dir.glob("*")
            if path.suffix.lower() in REFERENCE_IMAGE_EXTENSIONS
        ]
        images.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        return {"images": [{"name": path.name, "path": str(path)} for path in images]}

    def _list_outputs(self):
        drafts = sorted((OUTPUTS_DIR / "drafts").glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:10]
        final = sorted((OUTPUTS_DIR / "final").glob("*.*"), key=lambda p: p.stat().st_mtime, reverse=True)[:10]
        return {
            "drafts": [{"name": path.name, "path": str(path)} for path in drafts],
            "final": [{"name": path.name, "path": str(path)} for path in final],
        }

    def _send_file(self, path: Path):
        if not path.exists() or not path.resolve().is_relative_to(UI_DIR.resolve()):
            return self._send_error(404, "File not found")
        content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(path.read_bytes())

    def _send_safe_workspace_file(self, path: Path):
        try:
            resolved = path.resolve()
            root = ROOT.resolve()
            if not resolved.exists() or not resolved.is_relative_to(root):
                return self._send_error(404, "File not found")
        except OSError:
            return self._send_error(404, "File not found")
        content_type = mimetypes.guess_type(resolved)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(resolved.read_bytes())

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw or "{}")

    def _read_multipart_file(self, field_name: str):
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type or "boundary=" not in content_type:
            return None
        boundary = content_type.split("boundary=", 1)[1].strip().strip('"')
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        marker = ("--" + boundary).encode("utf-8")
        for part in body.split(marker):
            if not part or part in {b"--\r\n", b"--"}:
                continue
            header_blob, _, content = part.partition(b"\r\n\r\n")
            if not content:
                continue
            headers = header_blob.decode("utf-8", errors="ignore")
            if f'name="{field_name}"' not in headers:
                continue
            filename = "upload.jpg"
            if "filename=" in headers:
                filename = headers.split("filename=", 1)[1].split("\r\n", 1)[0].strip().strip('"')
                filename = Path(filename).name or "upload.jpg"
            content = content.removesuffix(b"\r\n")
            content = content.removesuffix(b"--")
            return filename, content
        return None

    def _send_json(self, data, status=200):
        body = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status, message):
        return self._send_json({"error": message}, status=status)

    def log_message(self, format, *args):
        return


def main():
    server = ThreadingHTTPServer((HOST, PORT), AgentUIHandler)
    print(f"Shrih Plaza Agent UI running at http://{HOST}:{PORT}")
    server.serve_forever()


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def parse_query(query: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for pair in query.split("&"):
        if not pair:
            continue
        key, _, value = pair.partition("=")
        from urllib.parse import unquote_plus
        result[unquote_plus(key)] = unquote_plus(value)
    return result


if __name__ == "__main__":
    main()
