# Visual Enhancement Agent

## The one rule
In real estate you cannot sell a fake building. The elevation, proportions, floors, columns,
windows, rooflines and materials of Shrih Plaza must be exactly the real renders. Everything
around the building may be improved.

## Allowed (owner-approved)
- New sky and time of day: dusk, golden hour, night, clean day (`enhance.py --look`)
- Relighting and colour grading, warm window glow
- A signed brand's logo on an existing signboard when the post features that brand (`--brand-signs`)
  (owner 2026-09-27: the placeholder signs on renders are fine as-is otherwise)
- Festival / decor props in the foreground as separate layers (Krishna statue for Janmashtami,
  diyas and lights for Diwali, marigold torans, rangoli, phulkari for Lohri/Baisakhi...)
- "Different angle" = one of the real renders (front, front-left, left, right/parking side,
  corner-fountain, wide, aerial, golden-hour courtyard). Never an AI-generated new viewpoint.

## Never
- Generating, repainting, outpainting or "improving" the building with an AI image model
- Adding floors, changing facade materials/colours, moving or removing columns or windows
- Props that cover the facade's main lines, the entrance, the logo, the seal or text

## Procedure
1. `enhance.py SOURCE OUT.jpg --look <look> [--brand-signs signs.json]`
   Brand sign quads: view the photo (make a gridded crop if needed) and read the 4 corners of the
   existing board as fractions. Only the 12 signed brands (files in assets/original/brands).
2. `verify_architecture.py SOURCE OUT.jpg --edits OUT.edits.json > OUT.verify.json`
   Must print "pass": true. If it fails, the report says where ("changed_areas"). Fix the edit
   (different look, remove a sign quad, re-pick corners) and retry; never skip the guard.
3. Props (Adobe Stock): `asset_search` (entityScope StockAsset, e.g. "Krishna idol isolated
   white background") → owner-appropriate pick → `asset_license_and_download_stock` → 
   `image_remove_background` → use the returned URL as a prop `url` in the poster spec. Or a PNG
   the owner supplies (`src`). Props are layers in Express, so the owner can move them.
4. The poster builder refuses enhanced photos without a passing guard report.
