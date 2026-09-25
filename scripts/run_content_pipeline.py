import argparse
import json
import re
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MEMORY = ROOT / "memory"
OUTPUTS = ROOT / "outputs"


FORBIDDEN_PATTERNS = [
    r"\bguaranteed returns?\b",
    r"\bassured profits?\b",
    r"\b100% appreciation\b",
    r"\blowest price guaranteed\b",
    r"\bbest project\b",
    r"\bpossession soon\b",
    r"\blimited units only\b",
]


def load_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)


def read_text(path):
    return path.read_text(encoding="utf-8")


def verified_claim_phrases(project_facts):
    phrases = set()
    for key in ["project_name", "location", "project_type", "developer_name", "rera_number"]:
        value = project_facts.get(key)
        if isinstance(value, str) and value.strip():
            phrases.add(value.strip().lower())
    for item in project_facts.get("approved_claims", []):
        if isinstance(item, str) and item.strip():
            phrases.add(item.strip().lower())
    for collection_key in ["amenities", "nearby_landmarks", "offers"]:
        for item in project_facts.get(collection_key, []):
            if isinstance(item, str) and item.strip():
                phrases.add(item.strip().lower())
            elif isinstance(item, dict):
                for value in item.values():
                    if isinstance(value, str) and value.strip():
                        phrases.add(value.strip().lower())
    return phrases


def generate_content(brief, brand, project_facts, preferences):
    project_name = project_facts.get("project_name") or brand.get("brand_name") or "the project"
    cta = (brand.get("cta_preferences") or ["Book a site visit"])[0]
    style = ", ".join(preferences.get("style_preferences", [])[:3])

    hook = f"{project_name}: a premium address for modern growth"
    caption = (
        f"{project_name} brings a clean, premium real estate presence for buyers who value clarity, "
        f"visibility, and trust. {cta}."
    )

    return {
        "platform": "Instagram",
        "format": "post",
        "hook": hook,
        "visual_direction": (
            "Use one approved elevation image. Keep layout minimal with strong whitespace. "
            f"Design mood: {style}."
        ),
        "caption": caption,
        "cta": cta,
        "hashtags": ["#RealEstate", "#CommercialProperty", f"#{project_name.replace(' ', '')}"],
        "claims_used": [project_name],
        "source_brief_excerpt": brief[:500],
    }


def extract_claim_candidates(content):
    text = " ".join(
        str(content.get(key, ""))
        for key in ["hook", "caption", "cta", "visual_direction"]
    )
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def fact_check(content, project_facts):
    verified_phrases = verified_claim_phrases(project_facts)
    claims = []
    approved = True

    for sentence in extract_claim_candidates(content):
        lowered = sentence.lower()
        has_number = bool(re.search(r"\b\d+(\.\d+)?\b", lowered))
        contains_verified = any(phrase in lowered for phrase in verified_phrases)
        is_soft_marketing = not has_number and not any(word in lowered for word in [
            "rera", "possession", "price", "₹", "rs", "km", "minutes", "sq", "return", "profit"
        ])

        if contains_verified or is_soft_marketing:
            status = "verified" if contains_verified else "allowed_soft_marketing"
            action = "keep"
            source = "project_facts or safe non-factual marketing line"
        else:
            status = "missing_source"
            action = "rewrite"
            source = ""
            approved = False

        claims.append({
            "claim": sentence,
            "status": status,
            "source": source,
            "action": action,
        })

    return {
        "fact_accuracy_score": 10 if approved else 0,
        "claims": claims,
        "approved": approved,
    }


def legal_review(content, project_facts):
    text = json.dumps(content, ensure_ascii=False).lower()
    risky = []

    forbidden_claims = list(project_facts.get("forbidden_claims", []))
    for phrase in forbidden_claims:
        if phrase.lower() in text:
            risky.append(phrase)

    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, text):
            risky.append(pattern)

    risky = sorted(set(risky))
    return {
        "legal_score": 10 if not risky else 0,
        "approved": not risky,
        "risky_lines": risky,
        "recommended_rewrites": [
            "Remove risky or unsupported claims and replace with verified project facts."
        ] if risky else [],
    }


def critic_review(content, brand, preferences):
    issues = []
    score = 9

    if len(content.get("hook", "")) > 80:
        issues.append("Hook is too long for a clean premium creative.")
        score -= 1
    if len(content.get("caption", "")) > 300:
        issues.append("Caption may be too long for a first draft.")
        score -= 1
    if not content.get("cta"):
        issues.append("CTA is missing.")
        score -= 2

    avoid_terms = [item.lower() for item in brand.get("avoid", []) if isinstance(item, str)]
    text = json.dumps(content, ensure_ascii=False).lower()
    for term in avoid_terms:
        if term and term in text:
            issues.append(f"Brand avoid term appears: {term}")
            score -= 1

    return {
        "overall_score": max(score, 0),
        "approved": score >= 8 and not issues,
        "issues": issues,
        "fix_instructions": [
            "Shorten, simplify, and keep the creative premium."
        ] if issues else [],
        "what_is_working": [
            "Clean single-image direction",
            "Clear CTA",
            "No invented numeric claims"
        ],
    }


def auto_fix(content, reviews):
    updated = dict(content)
    all_issues = json.dumps(reviews, ensure_ascii=False).lower()

    if "hook is too long" in all_issues:
        updated["hook"] = updated["hook"][:72].rstrip()
    if "missing_source" in all_issues:
        updated["caption"] = re.sub(
            r"\b\d+(\.\d+)?\s*(km|minutes|min|sq\.?\s*ft\.?|%|percent)\b",
            "",
            updated.get("caption", ""),
            flags=re.IGNORECASE,
        )
    for pattern in FORBIDDEN_PATTERNS:
        updated["caption"] = re.sub(pattern, "premium real estate opportunity", updated.get("caption", ""), flags=re.IGNORECASE)

    return updated


def run_pipeline(brief_path):
    brand = load_json(MEMORY / "brand_identity.json")
    project_facts = load_json(MEMORY / "project_facts.json")
    preferences = load_json(MEMORY / "preference_memory.json")
    brief = read_text(brief_path)

    content = generate_content(brief, brand, project_facts, preferences)
    history = []

    for attempt in range(1, 4):
        reviews = {
            "attempt": attempt,
            "critic": critic_review(content, brand, preferences),
            "fact_checker": fact_check(content, project_facts),
            "legal_rera": legal_review(content, project_facts),
            "architecture_guard": {
                "architecture_safety_score": 10,
                "approved": True,
                "note": "No image transformation was performed by this local runner. Use the preservation checklist for enhanced images."
            },
        }
        history.append({"content": content, "reviews": reviews})

        passed = all([
            reviews["critic"]["approved"],
            reviews["fact_checker"]["approved"],
            reviews["legal_rera"]["approved"],
            reviews["architecture_guard"]["approved"],
        ])
        if passed:
            break

        content = auto_fix(content, reviews)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    package = {
        "status": "approved_internal_review" if passed else "needs_human_review",
        "final_content": content,
        "review_history": history,
        "next_step": "Human approval required before posting.",
    }

    write_json(OUTPUTS / "drafts" / f"content_pack_{timestamp}.json", package)
    write_json(OUTPUTS / "reviews" / f"review_{timestamp}.json", history[-1]["reviews"])

    print(json.dumps(package, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="Run the real estate content generation review pipeline.")
    parser.add_argument("--brief", required=True, help="Path to a trend/content brief markdown file.")
    args = parser.parse_args()
    run_pipeline((ROOT / args.brief).resolve() if not Path(args.brief).is_absolute() else Path(args.brief))


if __name__ == "__main__":
    main()

