from dataclasses import dataclass
from typing import Any

from .io import read_json, write_json
from .paths import MEMORY_DIR


@dataclass
class BrandMemory:
    brand: dict[str, Any]
    project: dict[str, Any]
    preferences: dict[str, Any]


def load_memory() -> BrandMemory:
    return BrandMemory(
        brand=read_json(MEMORY_DIR / "brand_identity.json"),
        project=read_json(MEMORY_DIR / "project_facts.json"),
        preferences=read_json(MEMORY_DIR / "preference_memory.json"),
    )


def save_preferences(preferences: dict[str, Any]) -> None:
    write_json(MEMORY_DIR / "preference_memory.json", preferences)


def approved_facts(project: dict[str, Any]) -> list[str]:
    facts: list[str] = []
    for value in project.get("approved_claims", []):
        if isinstance(value, str) and value.strip():
            facts.append(value.strip())
    approval = project.get("approval_status", {})
    for value in approval.get("approved_public_wording", []):
        if isinstance(value, str) and value.strip():
            facts.append(value.strip())
    for brand in project.get("signed_brand_associations", []):
        facts.append(f"{brand} is an approved signed brand association.")
    return facts

