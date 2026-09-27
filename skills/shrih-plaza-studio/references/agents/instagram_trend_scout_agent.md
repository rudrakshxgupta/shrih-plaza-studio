# Instagram Trend Scout Agent

## Role

Look at what is currently working on Instagram for commercial real estate, retail and festival content, and record reusable patterns for the trend research agent.

## How it runs

This agent runs inside a Claude session, not as an unattended script. Scripted scraping of Instagram breaks its terms and would need the owner's login, so it is not built.

1. Open Instagram in the signed-in browser. The owner signs in; the agent never types a password.
2. Visit the Explore page, the Reels tab, and hashtag pages such as #commercialrealestate, #retailspace and the festival of the week.
3. Look only. No likes, follows, comments, saves, shares or messages.
4. For 8 to 15 posts note: format (reel, carousel, static), hook style, visual pacing, layout, caption structure, hashtag habits, CTA style.
5. Write one snapshot file to `inputs/trends/scout/YYYY-MM-DD-topic.md` using the format below.

## Rules

- Record patterns, never copy exact text, layouts or brand artwork.
- Never record another company's claims as Shrih Plaza facts.
- Explore is personalised to the signed-in account, so treat it as inspiration, not as a ranking of what is trending nationally.
- Note the date. Snapshots older than 30 days are ignored by the pipeline.

## Snapshot format

```markdown
# Scout snapshot YYYY-MM-DD

Source: Instagram Explore / Reels / #hashtag (signed in, read-only)

## Usable patterns
- one reusable pattern per line

## Content angles
- one angle per line

## Formats
- reel / carousel / static

## Avoid copying
- specific things seen that must not be reproduced

## Observations
Free notes, not read by the pipeline.
```
