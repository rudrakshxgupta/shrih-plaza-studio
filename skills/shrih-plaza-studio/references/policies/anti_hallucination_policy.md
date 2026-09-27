# Anti-Hallucination Policy

## Master Rule

If a claim is not present in `memory/project_facts.json`, the system must not present it as fact.

## Claim Categories That Require Verification

- Project name
- Location
- Developer name
- RERA number
- Price
- Area
- Possession date
- Distance from landmarks
- Amenities
- Number of units
- Floor count
- Rental income
- ROI or appreciation
- Approval status
- Offers and discounts

## Allowed Without Fact Source

- General emotional language, such as "designed for modern businesses"
- Platform-native hooks, as long as they do not imply unverified facts
- Generic CTAs, such as "Book a site visit"

## Must Reject

Reject or rewrite content containing:

- Guaranteed returns
- Assured profit
- 100% appreciation
- Lowest price guaranteed
- Best project in city
- Any unverified distance, date, price, unit size, or approval claim

## Verification Output Format

Each final content pack must include:

```json
{
  "claim": "Located near XYZ Road",
  "status": "verified | missing_source | rejected",
  "source": "project_facts.nearby_landmarks",
  "action": "keep | remove | rewrite | ask_user"
}
```

