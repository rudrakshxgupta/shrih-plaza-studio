import argparse
import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PREFERENCE_FILE = ROOT / "memory" / "preference_memory.json"


def load_preferences():
    with PREFERENCE_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_preferences(data):
    with PREFERENCE_FILE.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)


def infer_lesson(decision, feedback):
    lowered = feedback.lower()
    lesson = {
        "decision": decision,
        "feedback": feedback,
        "lesson": "",
        "applies_to": ["real estate social content"],
        "confidence": 0.6,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }

    if any(word in lowered for word in ["flashy", "loud", "crowded", "too much"]):
        lesson["lesson"] = "Prefer cleaner, more premium layouts with less visual noise and less text."
        lesson["confidence"] = 0.8
    elif any(word in lowered for word in ["premium", "luxury", "clean", "minimal"]):
        lesson["lesson"] = "Use a premium, clean, minimal visual direction for future creatives."
        lesson["confidence"] = 0.75
    elif any(word in lowered for word in ["caption", "wording", "copy", "text"]):
        lesson["lesson"] = "Improve caption wording according to the user's feedback before final approval."
        lesson["confidence"] = 0.7
    elif any(word in lowered for word in ["image", "render", "elevation", "building"]):
        lesson["lesson"] = "Pay closer attention to image quality while preserving the original architecture."
        lesson["confidence"] = 0.75
    elif decision == "approved":
        lesson["lesson"] = "User approved this direction; reuse similar structure, tone, and design restraint."
        lesson["confidence"] = 0.7
    else:
        lesson["lesson"] = "Avoid repeating this rejected direction unless the user asks for it."
        lesson["confidence"] = 0.65

    return lesson


def main():
    parser = argparse.ArgumentParser(description="Record approval/rejection feedback into preference memory.")
    parser.add_argument("--decision", choices=["approved", "rejected", "needs_changes"], required=True)
    parser.add_argument("--feedback", required=True, help="User feedback, for example: 'Too flashy, make it cleaner.'")
    args = parser.parse_args()

    preferences = load_preferences()
    lesson = infer_lesson(args.decision, args.feedback)

    if args.decision == "approved":
        preferences.setdefault("approved_patterns", []).append(args.feedback)
    else:
        preferences.setdefault("rejected_patterns", []).append(args.feedback)

    preferences.setdefault("learned_lessons", []).append(lesson)
    save_preferences(preferences)

    print(json.dumps({
        "saved": True,
        "lesson": lesson,
        "preference_file": str(PREFERENCE_FILE),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

