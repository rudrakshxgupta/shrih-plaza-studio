import argparse
import json
from pathlib import Path

from . import decisions as owner_decisions
from .agents import ArchitectureGuardAgent, PreferenceLearningAgent
from .image_tools import enhance_image_safe
from .io import write_json
from .memory import load_memory, save_preferences
from .pipeline import ContentPipeline
from .paths import ASSETS_DIR, INPUTS_DIR, MEMORY_DIR, OUTPUTS_DIR
from .renderer import render_instagram_post


def cmd_run(args: argparse.Namespace) -> None:
    brief = Path(args.brief)
    if not brief.is_absolute():
        brief = (Path.cwd() / brief).resolve()
    result = ContentPipeline().run(
        brief_path=brief,
        platform=args.platform,
        content_format=args.format,
        max_attempts=args.max_attempts,
        render_image=args.render_image,
        image_path=Path(args.image).resolve() if args.image else None,
        generate_image=args.generate_image,
        max_image_attempts=args.max_image_attempts,
        design_layout=args.design,
        palette=args.palette,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_regenerate(args: argparse.Namespace) -> None:
    content_path = Path(args.content)
    if not content_path.is_absolute():
        content_path = (Path.cwd() / content_path).resolve()
    data = json.loads(content_path.read_text(encoding="utf-8"))
    previous_content = data.get("final_content", data)
    result = ContentPipeline().regenerate_from_feedback(
        previous_content=previous_content,
        feedback=args.feedback,
        decision=args.decision,
        reference_image_path=Path(args.image).resolve() if args.image else None,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_decide(args: argparse.Namespace) -> None:
    context = {}
    if args.post:
        report = Path(args.post)
        if report.exists():
            context = {k: v for k, v in json.loads(report.read_text(encoding="utf-8")).items()
                       if k in ("hook", "caption", "layout", "palette", "pillar", "date")}
    entry = owner_decisions.add_decision(args.id, args.decision, args.reason or "", args.category,
                                         args.ban or "", context)
    print(json.dumps({"saved": entry, "lessons_now": owner_decisions.lessons(),
                      "banned_phrases_now": owner_decisions.banned_phrases()}, indent=2, ensure_ascii=False))


def cmd_import_decisions(args: argparse.Namespace) -> None:
    data = json.loads(Path(args.file).read_text(encoding="utf-8"))
    items = data.get("decisions", data) if isinstance(data, dict) else data
    changed = owner_decisions.import_decisions(items)
    print(json.dumps({"imported": changed, "total": len(owner_decisions.load_decisions())}, indent=2))


def cmd_check_architecture(args: argparse.Namespace) -> None:
    result = ArchitectureGuardAgent().run(
        Path(args.original).resolve(), Path(args.candidate).resolve()
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_render_post(args: argparse.Namespace) -> None:
    memory = load_memory()
    content_path = Path(args.content)
    if not content_path.is_absolute():
        content_path = (Path.cwd() / content_path).resolve()
    data = json.loads(content_path.read_text(encoding="utf-8"))
    content = data.get("final_content", data)
    image_path = Path(args.image).resolve() if args.image else None
    result = render_instagram_post(content, memory.brand, memory.project, image_path=image_path)
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_feedback(args: argparse.Namespace) -> None:
    memory = load_memory()
    updated = PreferenceLearningAgent().learn(memory.preferences, args.decision, args.feedback)
    save_preferences(updated)
    print(json.dumps({
        "saved": True,
        "decision": args.decision,
        "feedback": args.feedback,
        "preference_file": str(MEMORY_DIR / "preference_memory.json"),
    }, indent=2, ensure_ascii=False))


def cmd_new_brief(args: argparse.Namespace) -> None:
    path = INPUTS_DIR / "trends" / args.name
    if path.suffix.lower() != ".md":
        path = path.with_suffix(".md")
    body = "\n".join([
        f"# {args.title}",
        "",
        f"Platform: {args.platform}",
        "",
        "Trend pattern:",
        "",
        "- ",
        "",
        "Content goal:",
        "",
        "- ",
        "",
        "Notes:",
        "",
        "- Do not copy competitor content exactly.",
        "- Use Shrih Plaza brand kit and verified facts only.",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    print(json.dumps({"created": str(path)}, indent=2))


def cmd_show_memory(args: argparse.Namespace) -> None:
    memory = load_memory()
    data = {
        "brand": memory.brand,
        "project": memory.project,
        "preferences": memory.preferences,
    }
    print(json.dumps(data, indent=2, ensure_ascii=False))


def cmd_enhance_image(args: argparse.Namespace) -> None:
    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = (Path.cwd() / input_path).resolve()
    output_path = Path(args.output) if args.output else ASSETS_DIR / "enhanced" / f"{input_path.stem}_enhanced{input_path.suffix}"
    if not output_path.is_absolute():
        output_path = (Path.cwd() / output_path).resolve()

    result = enhance_image_safe(input_path, output_path)
    review_path = OUTPUTS_DIR / "reviews" / f"{input_path.stem}_image_enhancement_review.json"
    write_json(review_path, result)
    print(json.dumps({
        "enhanced": True,
        "output": str(output_path),
        "review": str(review_path),
        "note": "Safe enhancement only. Manual architecture review is still required before posting.",
    }, indent=2, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shrih-agent", description="Shrih Plaza agentic content system")
    sub = parser.add_subparsers(required=True)

    run = sub.add_parser("run", help="Generate, review and auto-fix a content pack")
    run.add_argument("--brief", default="inputs/trends/sample_trend_brief.md")
    run.add_argument("--platform", default="Instagram")
    run.add_argument("--format", default="post")
    run.add_argument("--max-attempts", type=int, default=3)
    run.add_argument("--render-image", action="store_true", help="Also render a 1080x1350 Instagram PNG")
    run.add_argument("--image", help="Optional source elevation/render image")
    run.add_argument("--generate-image", action="store_true", help="Generate a real edited image with Gemini, architecture-verified")
    run.add_argument("--max-image-attempts", type=int, default=3)
    run.add_argument("--design", choices=["hero", "tenants"], help="Build a finished post with the design agent and visual reviewer")
    run.add_argument("--palette", default="navy", choices=["navy", "emerald", "maroon", "charcoal", "plum"], help="Colour palette for --design (navy and gold is the default)")
    run.set_defaults(func=cmd_run)

    regenerate = sub.add_parser("regenerate", help="Re-run generation using human feedback on a previous content pack")
    regenerate.add_argument("--content", required=True, help="Path to a saved content pack JSON")
    regenerate.add_argument("--decision", choices=["needs_changes", "rejected"], required=True)
    regenerate.add_argument("--feedback", required=True)
    regenerate.add_argument("--image", help="Reference photo, if the image should also be regenerated")
    regenerate.set_defaults(func=cmd_regenerate)

    decide = sub.add_parser("decide", help="Approve or deny a post; the reason is learned by the pipeline")
    decide.add_argument("--id", required=True, help="Post id, e.g. daily-2026-09-25")
    decide.add_argument("--decision", choices=["approve", "deny"], required=True)
    decide.add_argument("--reason", help="Required for deny")
    decide.add_argument("--category", default="other", choices=["copy", "design", "claim", "layout", "other"])
    decide.add_argument("--ban", help="A phrase that must never appear again")
    decide.add_argument("--post", help="Path to the post's report.json, to remember what was decided on")
    decide.set_defaults(func=cmd_decide)

    imp = sub.add_parser("import-decisions", help="Merge decisions exported from the web review page")
    imp.add_argument("--file", required=True)
    imp.set_defaults(func=cmd_import_decisions)

    check_architecture = sub.add_parser("check-architecture", help="Run the architecture guard on an existing image pair")
    check_architecture.add_argument("--original", required=True)
    check_architecture.add_argument("--candidate", required=True)
    check_architecture.set_defaults(func=cmd_check_architecture)

    render = sub.add_parser("render-post", help="Render an Instagram PNG from a generated content JSON")
    render.add_argument("--content", required=True)
    render.add_argument("--image")
    render.set_defaults(func=cmd_render_post)

    feedback = sub.add_parser("feedback", help="Record approval/rejection feedback")
    feedback.add_argument("--decision", choices=["approved", "rejected", "needs_changes"], required=True)
    feedback.add_argument("--feedback", required=True)
    feedback.set_defaults(func=cmd_feedback)

    brief = sub.add_parser("new-brief", help="Create a new trend/content brief file")
    brief.add_argument("--name", required=True)
    brief.add_argument("--title", default="New Shrih Plaza Content Brief")
    brief.add_argument("--platform", default="Instagram")
    brief.set_defaults(func=cmd_new_brief)

    memory = sub.add_parser("show-memory", help="Print loaded brand/project/preference memory")
    memory.set_defaults(func=cmd_show_memory)

    image = sub.add_parser("enhance-image", help="Safely enhance an image without generative architecture changes")
    image.add_argument("--input", required=True)
    image.add_argument("--output")
    image.set_defaults(func=cmd_enhance_image)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
