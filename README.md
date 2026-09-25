# Real Estate Agentic Content System

This starter setup creates an agentic workflow for real estate social media content generation with hallucination control, brand memory, architecture preservation rules, internal critique, auto-fix loops, and user preference learning.

The system is designed for this workflow:

```text
Trend input
  -> Brand + project fact memory
  -> Content generation
  -> Critic review
  -> Fact verification
  -> Architecture preservation review
  -> Legal/RERA review
  -> Auto-fix loop
  -> Human approval
  -> Preference learning
  -> Final export
```

## What This Setup Gives You

- Agent prompts for each role in `agents/`
- Strict anti-hallucination policies in `policies/`
- Editable brand, project, and preference memory in `memory/`
- A sample trend brief in `inputs/trends/`
- Asset folders for original and enhanced images
- A local Python workflow runner in `scripts/run_content_pipeline.py`
- Output folders for drafts, reviews, and final approved content

## First-Time Setup

1. Add your real project facts in `memory/project_facts.json`.
2. Add your brand identity in `memory/brand_identity.json`.
3. Add your logo, elevation images, renders, and site images into `assets/original/`.
4. Add a trend/content inspiration brief into `inputs/trends/`.
5. Run:

```powershell
python scripts/run_content_pipeline.py --brief inputs/trends/sample_trend_brief.md
```

## Run The Actual Agent

Use the new local agent package:

```powershell
python run_agent.py run --brief inputs/trends/sample_trend_brief.md --platform Instagram --format post
```

It will:

- Load brand, project and preference memory
- Generate a content draft
- Critic-review it
- Fact-check claims
- Check legal/RERA risk
- Apply architecture-preservation policy
- Auto-fix weak output up to three times
- Export JSON and Markdown content packs

Optional OpenAI mode (text only):

```powershell
$env:OPENAI_API_KEY="your_api_key"
python run_agent.py run --brief inputs/trends/sample_trend_brief.md
```

Without `OPENAI_API_KEY`, the agent runs in safe local fallback mode.

## Real Image Generation, Trend Research, and Architecture Verification (Gemini)

Set `GEMINI_API_KEY` (from Google AI Studio) to unlock three things, all through the same key:

```powershell
$env:GEMINI_API_KEY="your_api_key"
python run_agent.py run --brief inputs/trends/sample_trend_brief.md --image assets/original/your-photo.jpg --generate-image --render-image
```

- **Trend research** is search-grounded instead of just reading your brief as-is.
- **Image generation** edits your real reference photo (lighting, sky, angle, approved seasonal decor) instead of drawing a new building from scratch.
- **Architecture verification** compares the original and generated photo against the checklist in `policies/architecture_preservation_policy.md` before anything is marked approved.

Image generation and search grounding are **billed** on Google's side even with a valid key -- plain text calls are free, but image edits and grounded search need billing enabled on the linked AI Studio/Cloud project (roughly 3-15 cents per image at current pricing). Without `GEMINI_API_KEY`, or if billing isn't enabled, the system keeps working exactly as it does today: trend research falls back to your written brief, and any image pair is routed to a manual on-screen checklist instead of being silently approved -- it never guesses.

Every time the architecture guard rejects an image (automatically via Gemini, or by you confirming the manual checklist), it's logged to `memory/mistake_memory.json`. Every future image prompt explicitly restates every past mistake as a "do not repeat this" instruction -- this is how the system avoids hallucinating the same structural change twice.

To regenerate a specific draft using your feedback (rather than just recording the feedback for next time):

```powershell
python run_agent.py regenerate --content outputs/drafts/agent_content_pack_....json --decision needs_changes --feedback "Too generic, lead with the SH-11 highway location" --image assets/original/your-photo.jpg
```

To test the architecture guard directly against any two images:

```powershell
python run_agent.py check-architecture --original assets/original/your-photo.jpg --candidate outputs/generated/candidate_....png
```

## Open The Web UI

Run:

```powershell
python ui/server.py
```

Then open:

```text
http://127.0.0.1:8787
```

The UI lets you generate content, see critic/fact/legal review results, upload real reference photos, generate a real Gemini-edited image with an architecture checklist, reject a draft and have it automatically regenerated with your feedback applied, save feedback for learning, view memory, and safely enhance images.

## Recording Your Feedback

When you approve or reject a content direction, record it so the system learns your taste:

```powershell
python scripts/record_feedback.py --decision rejected --feedback "Too flashy, make it more premium and clean"
```

```powershell
python scripts/record_feedback.py --decision approved --feedback "Good style, use this minimal layout again"
```

This updates `memory/preference_memory.json`, which is used by future content runs.

The agent command can also record feedback:

```powershell
python run_agent.py feedback --decision rejected --feedback "Too crowded, use more whitespace"
```

## Create A New Brief

```powershell
python run_agent.py new-brief --name festival-campaign --title "Festival retail campaign"
```

## Safe Image Enhancement

Put original images in `assets/original/`, then run:

```powershell
pip install -r requirements.txt
python run_agent.py enhance-image --input assets/original/your-image.jpg
```

This first image tool only applies non-generative quality edits: sharpness, contrast, color and brightness. It does not change elevation, facade, floors, windows, balconies, entrance or structure.

## Core Safety Rule

The AI may be creative with presentation, layout, and style, but every factual claim must come from `memory/project_facts.json`.

If a claim is not verified, it must be removed, softened, or sent to you for approval.

## Image Safety Rule

Enhancement is allowed only for:

- Lighting
- Sharpness
- Color balance
- Sky replacement
- Noise cleanup
- Ambience
- Minor foreground cleanup

Enhancement is not allowed to change:

- Elevation design
- Facade
- Floor count
- Windows
- Balconies
- Entrance shape
- Structural layout
- Building proportions

## Recommended Human Workflow

At first, keep posting manual:

```text
AI produces content pack -> You approve -> You post or schedule
```

After the system learns your taste and passes reviews consistently, you can add auto-scheduling.

## Design Agent, Visual Reviewer and Trend Scout

Build a finished, reviewed post from the brand kit and your real renders:

```powershell
python run_agent.py run --brief inputs/trends/sample_trend_brief.md --design hero
python run_agent.py run --brief inputs/trends/sample_trend_brief.md --design tenants
```

- The **design agent** (`shrih_agent/design_agent.py`) composes an HTML layout from the original logo, the approved brand logos and the aerial render, then renders a 1080x1350 PNG with headless Chrome or Edge. It never generates or edits the building, and it refuses the elevation renders because they show unapproved shop signs.
- The **visual reviewer** (`shrih_agent/visual_review.py`) checks the PNG: size, black bars, only the 12 approved brands, no unapproved brand names, forbidden claims, the phone number, the "Artist's impression" note, the logo and minimum text size. A failed review retries once, and every defect is logged to `memory/mistake_memory.json`.
- The **trend scout** (`agents/instagram_trend_scout_agent.md`) runs in a Claude session: it browses Explore and hashtag pages in your signed-in browser, looks only, and writes a snapshot to `inputs/trends/scout/`. The pipeline's trend agent reads snapshots from the last 30 days. It is not an unattended script, because scripted scraping of Instagram breaks its terms.
- Adobe Express export is done in a Claude session with the Adobe connector. The design HTML in `outputs/design/` is the source for it.
