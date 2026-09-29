"""AI content engine: fabulous, innovative real-estate imagery of the real Shrih Plaza.

Owner direction (2026-09-30): we are not building posters. We make AI real-estate
content, and the AI gets full creative freedom (sky, weather, light, season, mood,
people, props, atmosphere), while the building and its architecture stay exactly
as the real render shows. No headline, no footer, no layout: the image is the content.

Model: GPT Image 2.5 Flare on the OpenAI API (see openai_images.py). The source framing
is kept (size "auto"), so the building stays large and the automatic architecture
check can line the AI image up with the original render edge for edge.
"""

import io
import random
from datetime import datetime
from pathlib import Path
from typing import Any

from . import design_history
from .openai_images import OpenAIImageClient
from .paths import ASSETS_DIR, OUTPUTS_DIR

# Automatic building check: faithful relights score 0.92-0.95, a different view of the plaza 0.41-0.53.
ARCHITECTURE_PASS = 0.70

# Big ideas: each is a different world around the same real building.
CONCEPTS = [
    {"id": "blue-hour-light-trails", "scene": "Blue-hour long exposure: deep sapphire sky, the facade glowing warm like a jewel box, streaks of golden and red car light trails sweeping along the road in the foreground."},
    {"id": "monsoon-mirror", "scene": "Just after monsoon rain at night: wet paving turned into a mirror of the lit shops, puddle reflections, fine rain bokeh, moody teal and amber grade, a few people with umbrellas."},
    {"id": "god-rays", "scene": "Epic golden hour: dramatic sun rays breaking through clouds behind the building, long warm shadows, glowing dust in the air, cinematic scale."},
    {"id": "sky-lanterns", "scene": "Magical dusk: hundreds of glowing paper sky lanterns rising into a violet-orange sky above the plaza, families in the forecourt looking up, warm festive glow."},
    {"id": "punjab-mist-sunrise", "scene": "Misty winter sunrise in Punjab: soft fog on the ground, a pastel sky, the low sun beside the plaza, serene and premium, the shops just lighting up."},
    {"id": "milky-way-night", "scene": "Clear night with the Milky Way arching over the plaza, astrophotography style, every shop window glowing, cool sky against warm light."},
    {"id": "gold-dust-sky", "scene": "Surreal luxury: a giant ribbon of liquid gold and gold dust sweeping through a deep midnight-blue sky above the building, premium campaign look."},
    {"id": "day-to-night", "scene": "A seamless day-to-night transition across one continuous sky: bright morning blue on the left, deep dusk with glowing shops on the right."},
    {"id": "film-still-crowd", "scene": "Cinematic anamorphic film still: evening, warm and teal grade, soft lens flares, a lively crowd of well-dressed shoppers and families in the forecourt."},
    {"id": "noir-gold", "scene": "Luxury noir: near-black sky, crisp golden rim light tracing the facade edges, dramatic spotlights, high contrast, magazine-cover elegance."},
    {"id": "string-lights-market", "scene": "Evening festive market in the forecourt: warm string lights overhead, small stalls, children with balloons, families strolling, cosy golden atmosphere."},
    {"id": "aurora-sky", "scene": "Fantastical aurora-like ribbons of emerald, violet and gold in the night sky over the plaza, dreamy, reflected on the paving."},
    {"id": "storm-break", "scene": "Storm clouds clearing at sunset, a burst of gold light hitting the facade, a rainbow arcing behind the building, powerful and hopeful."},
    {"id": "fireworks", "scene": "Celebration night: colourful fireworks bursting high in the sky above the plaza, sparkle reflections on cars and paving, happy crowd below."},
]

SOURCES = sorted((ASSETS_DIR / "renders").glob("ai-*.jpg")) + sorted((ASSETS_DIR / "original").glob("elevation-*.jpg"))


def build_prompt(concept: dict[str, str], mood: str = "") -> str:
    return (
        "Transform this real-estate render of Shrih Plaza, a premium commercial destination in Dhuri, Punjab, "
        "into fabulous, innovative, scroll-stopping social media imagery, like a top agency's award-winning campaign.\n\n"
        f"Creative concept: {concept['scene']}\n"
        + (f"Extra direction: {mood}\n" if mood else "")
        + "\nYou have full creative freedom over the sky, weather, time of day, light, atmosphere, colour grade, "
        "people, vehicles, landscaping props and effects.\n\n"
        "The one rule you must never break: the building is real. Keep it exactly as it is, in the same place in "
        "the frame: the same outline, number of floors, window grid, columns, facade materials and colours, "
        "signboard positions, entrance and proportions. Do not redesign it, add floors, move it, change its shape "
        "or invent new wings. Keep the camera angle and framing. Only relight it and change the world around it.\n\n"
        "Do not add any text, headline, logo, watermark or phone number."
    )


def architecture_score(original: Path, candidate_bytes: bytes) -> float:
    """How closely the building's edges in the AI image match the original render (0 to 1).
    Only the building band (22% to 78% of the height) is compared, since the sky and
    foreground are free to change. Edge maps are blurred to forgive small shifts."""
    from PIL import Image, ImageFilter

    def edges(image):
        image = image.convert("L").resize((480, 270))
        band = image.crop((0, int(270 * 0.22), 480, int(270 * 0.78)))
        return band.filter(ImageFilter.FIND_EDGES).filter(ImageFilter.GaussianBlur(2))

    a = list(edges(Image.open(original)).getdata())
    b = list(edges(Image.open(io.BytesIO(candidate_bytes))).getdata())
    mean_a, mean_b = sum(a) / len(a), sum(b) / len(b)
    cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b))
    var_a = sum((x - mean_a) ** 2 for x in a) ** 0.5
    var_b = sum((y - mean_b) ** 2 for y in b) ** 0.5
    return round(cov / (var_a * var_b), 3) if var_a and var_b else 0.0


def choose(seed: int | None = None) -> dict[str, Any]:
    """A concept and render pair never used before, and a concept not used in the last 6 pieces."""
    rng = random.Random(seed)
    history = design_history.load_history()
    recent = {d.get("layout", "") for d in history[-6:]}
    used = {(d.get("layout", ""), d.get("photo", "")) for d in history}
    concepts = [c for c in CONCEPTS if f"ai:{c['id']}" not in recent] or list(CONCEPTS)
    rng.shuffle(concepts)
    sources = list(SOURCES)
    rng.shuffle(sources)
    for concept in concepts:
        for source in sources:
            if (f"ai:{concept['id']}", source.stem) not in used:
                return {"concept": concept, "source": source}
    return {"concept": concepts[0], "source": sources[0]}


def make_content(post_id: str, mood: str = "", seed: int | None = None, quality: str | None = None,
                 attempts: int = 2, on_step=None) -> dict[str, Any]:
    """Generate one AI image of the real building and check the building was kept.
    A failed building check retries once with a stricter instruction."""
    step = on_step or (lambda *_: None)
    pick = choose(seed)
    concept, source = pick["concept"], pick["source"]
    client = OpenAIImageClient()
    extra = mood
    base = {"concept": concept["id"], "scene": concept["scene"], "source_image": str(source), "model": client.deployment}
    for attempt in range(1, attempts + 1):
        prompt = build_prompt(concept, extra)
        step("generating", attempt, concept["id"], source.name)
        result = client.edit(source, prompt, size="auto", quality=quality, raw_prompt=True)
        if result.status != "ok":
            return {"status": result.status, "error": result.error, "prompt": prompt, **base}
        score = architecture_score(source, result.image_bytes)
        step("checked", attempt, score, ARCHITECTURE_PASS)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = OUTPUTS_DIR / "ai"
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"{stamp}_{concept['id']}.png"
        path.write_bytes(result.image_bytes)
        if score >= ARCHITECTURE_PASS:
            design_history.record(post_id, {"layout": f"ai:{concept['id']}", "photo": source.stem,
                                            "type_treatment": "ai-content", "concept": concept["id"]}, "produced")
            return {"status": "ok", "png": str(path), "architecture_score": score, "attempts": attempt, "prompt": prompt, **base}
        extra = (mood + " " if mood else "") + ("The previous try changed the building. This time keep every line of the "
                                               "building exactly where it is in the photo; change only light and surroundings.")
        if attempt == attempts:
            return {"status": "architecture_failed", "png": str(path), "architecture_score": score, "attempts": attempt,
                    "prompt": prompt, **base}
    return {"status": "error", "error": "no attempt ran", **base}
