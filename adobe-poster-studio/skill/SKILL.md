---
name: shrih-plaza-studio
description: Shrih Plaza's complete multi-agent social media studio, run inside Claude with AI-made posters. Use it whenever the user mentions Shrih Plaza, SHRIH PLAZA, SH-11 Dhuri, SCO spaces, their brands (Domino's, Barista, Sagar Ratna...), an Instagram post / reel cover / poster / creative / caption / festival greeting (Janmashtami, Diwali, Lohri...), trend research for their content, redesigning a denied post, or approving/denying/giving feedback on a post, even if they do not say skill or agents. Pipeline - social research → brand-customised creative brief → real-building enhancement with architecture guard → premium poster → review panel → auto-fix → owner → learning.
---

# Shrih Plaza Studio

A team of agents that Claude plays one after another. The GitHub repo is long-term memory,
real renders are the only source of the building, and AI-made images are where finished posts
live. The owner (Rudraksh) isn't a developer: plain language, show results, one question at a time.

Repo: https://github.com/rudrakshxgupta/shrih-plaza-studio (must stay public).

```
Research -> Creative brief -> Enhance real photo -> Architecture guard -> Design -> Review panel
                                   ^                     | fail                       | fail
                                   +---- auto-fix <------+---------- auto-fix <-------+  (max 3, then ask)
                                                                                      | pass
Owner "change X" <- Owner approves / denies <- AI poster + caption <-------------------+
      |                     |
      +-> back to step      +-> learning: decisions + mistakes saved for every future run
```

## Step 0 · Memory (always first)

```bash
bash <skill>/scripts/sync_repo.sh && python3 <skill>/scripts/memory_brief.py
```
Everything printed is binding. **Owner rules that override older memory (2026-09-27):**
placeholder shop signs on the renders are fine as-is; when a post features a signed brand, its
logo may be placed on an existing signboard. If the brief still shows the old "render signage not
approved" line, the owner rule wins (the staged `memory-update/project_facts.json` fixes it once uploaded).

## Step 1 · Social Research Agent
Follow `references/agents/social_research_agent.md`. Topic = what the owner asked, else the
brand's domain + any occasion within 14 days. Output the research JSON; keep it brief in chat.

## Step 2 · Creative Brief Agent
Follow `references/agents/creative_brief_agent.md`. Produce the brief JSON: adapted pattern,
photo + look + crop, brand signboards, festival props, copy, caption, hashtags, claim mapping.
Headline ≈ 6 words total (hero word + ≤ 5). Never repeat a recent hook or a rejected layout+palette.

## Step 3 · Visual Enhancement Agent + Architecture Guard
Follow `references/agents/visual_enhancement_agent.md`.
```bash
python3 <skill>/scripts/enhance.py $REPO/assets/original/<render>.jpg work/photo.jpg --look dusk [--brand-signs signs.json]
python3 <skill>/scripts/verify_architecture.py $REPO/assets/original/<render>.jpg work/photo.jpg \
        --edits work/photo.edits.json > work/photo.verify.json
```
The guard must pass. It rejects any stretched, shifted, redrawn, copied or AI-regenerated
building and names the area that changed. Look at the result yourself too. Photos used as-is
(an original render, or the bundled `golden-hour-courtyard.jpg` with `"graded": true`) need no guard.

## Step 4 · Design Agent (Premium Poster Standard)
Spec keys are documented at the top of `scripts/build_poster.py`
(layouts `hero` / `brands`; palettes navy / maroon / emerald; `focus_x/y`, `zoom`, `props`, `verified`).
```bash
python3 <skill>/scripts/build_poster.py spec.json work/post.html
python3 <skill>/scripts/preview.py work/post.html work/post.png
```
`preview.py` lists issues: text overflow/overlap, text over the frame, props covering text/logo/seal,
photo upscaled too far (soft). Zero issues required. Then view the PNG as a creative director
against the Premium Poster Standard in `references/brand/shrih-plaza-brand-kit.md`.

## Step 5 · Review Panel (separate strict passes, write a verdict for each)
1. **Fact checker** (`fact_checker_agent.md`): every claim maps to an APPROVED CLAIM; brands only the 12.
2. **Legal / RERA** (`legal_rera_agent.md`): no forbidden wording, banned phrases, prices, returns,
   possession dates, unit counts, urgency, RERA number. "Artist's impression." present.
3. **Architecture**: guard passed for every enhanced photo; props don't hide the facade.
4. **Critic** (`critic_agent.md`): stops the scroll? premium? too much text? CTA clear? follows lessons?
5. **Scores** (`review_scoring_policy.md`): fact 10, architecture 10, legal 10, brand ≥ 8, visual ≥ 8,
   trend ≥ 7, sales ≥ 7.

## Step 6 · Auto-fix loop + automatic learning
Any failure → fix only what failed (`auto_fix_agent.md`) and rerun from the step that failed.
For EACH failure fixed, log it so the system learns without being told:
```bash
python3 <skill>/scripts/log_mistake.py --category design_defect --what "..." --avoid "..."
```
Max 3 loops. Still failing, or a new fact/photo is needed → ask the owner one question.

## Step 7 · AI poster
The poster is an AI image made on Azure AI Foundry (GPT Image 2.5 Flare) from a real render:
`python scripts/ai_poster.py`. The AI has full creative freedom around the building; the building
itself must match the source render. Adobe Express is no longer used.

## Step 8 · Owner
Show the preview PNG (copy to `/mnt/user-data/outputs/` and present it), caption +
hashtags, and a 4-line review summary (facts ✓, legal ✓, architecture ✓ with score, critic score).
Ask: approve, or what should change?
- "Change X" → apply X, rerun from the affected step (copy → Step 2, photo/look → Step 3,
  layout → Step 4), then back through the review panel.
- Decision → record it (a denial needs a reason):
```bash
python3 <skill>/scripts/record_decision.py --post-id claude-YYYY-MM-DD-NN --decision approved|denied \
  --reason "..." --category design|layout|copy|claim|other \
  --context '{"hook":"...","caption":"...","layout":"hero","palette":"navy","pillar":"...","date":"YYYY-MM-DD"}'
```

## Step 9 · Save the learning
Present every file in `/mnt/user-data/outputs/memory-update/` and say once:
> GitHub → repo → `memory` folder → **Add file → Upload files** → drop these → **Commit changes**.
Until uploaded, this chat remembers but the next chat and the daily 9 AM post don't.

## Hard rules
- The building is always a real render. Only sky, light, colour, declared brand signboards and
  foreground props may change, and the guard must pass.
- Only APPROVED CLAIMS, only the 12 signed brands, phone from contact.
- No prices, returns, possession dates, unit counts, urgency, "best in city", RERA number.
- "Artist's impression." on every render-based post.
- Newest owner feedback beats older preferences.
