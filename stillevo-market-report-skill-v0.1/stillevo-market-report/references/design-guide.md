# Design guide: STILLEVO Market Intelligence

## Direction

A restrained editorial research report: cool slate / midnight navy / gray-tinted white, ample white space, meaningful hierarchy, legible dense facts. Not a shopping catalog, not a startup pitch deck, not an AI infographic.

- Format: A4 portrait; fixed running header/footer on inner pages.
- Type: Inter / Noto Sans CJK (system fallback), not internet fonts.
- Content sequence: Cover -> Executive Brief -> Product Profiles -> Comparative View -> Source Index / Open Questions.
- Photo: real product photograph, consistent crop, no deceptive reuse. Missing photo is explicitly labeled.
- Price label must carry region/currency/date notes and reference IDs.
- Evidence links live in both product cards and Source Index, not a wall of raw URLs in the narrative.
- Keep the executive summary under one page. A Product Profile should be scannable without horizontal scrolling.

## Reader-oriented visual inspection (not automated gates)

After generating `report.pdf`, inspect the rendered pages:

1. Can the reader see a product photo, price, position and 5-8 important specs at a glance?
2. Are pages clipped or awkwardly broken? Are CJK glyphs intact?
3. Do source IDs resolve to a visible entry? Are source URLs click-through?
4. Are sample/demo labels and draft status accurate? Would a client confuse a placeholder with a real product?
5. Is each figure or price in the right currency, market and observation date?

Fix the actual problem and re-render. Do not add more validation frameworks.
