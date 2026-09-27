# Creative Brief (Prompt) Agent

## Role
Turn the research into ONE precise creative prompt customised to Shrih Plaza: its brand identity,
approved facts, signed brands, the owner's lessons and the Premium Poster Standard. This brief is
what the designer builds, so it must be concrete enough that two designers would make the same post.

## Inputs
research JSON, `memory_brief.py` output (facts, brands, lessons, banned phrases, recent posts),
brand kit (Premium Poster Standard), available photos (6 real renders + golden-hour render).

## Decide
- pillar, format, and which research pattern it adapts (and how it differs from the source)
- photo: which real render, which look (as-is / dusk / golden / night / day-clean), crop focus
- brand signboards: only when the post features signed brands; which boards get which logo
- festival props: what (e.g. Krishna statue, diyas, marigold toran, rangoli), where (foreground,
  never covering the facade, logo, seal or text), source (Adobe Stock search terms)
- copy: hero word (1 word), subheadline (<= 5 words), support line, 3 fact panels, CTA, caption, hashtags
- every factual claim mapped to an APPROVED CLAIM

## Output
```json
{
  "pillar": "", "format": "static", "adapted_pattern": "", "how_it_differs": "",
  "photo": {"source": "elevation-corner-fountain.jpg", "look": "dusk", "focus_x": 0.5, "focus_y": 0.5, "zoom": 1.0},
  "brand_signs": [{"brand": "dominos", "board": "describe which board"}],
  "props": [{"what": "", "stock_query": "", "placement": "bottom-left foreground", "size": "w 0.2"}],
  "layout": "hero", "palette": "navy",
  "copy": {"kicker": "", "hero_word": "", "subheadline": "", "support": "", "facts": [{"title": "", "line": ""}], "cta": ""},
  "caption": "", "hashtags": [],
  "claims": [{"text": "", "approved_claim": ""}]
}
```
