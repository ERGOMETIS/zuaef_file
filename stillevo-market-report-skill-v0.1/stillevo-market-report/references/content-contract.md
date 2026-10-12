# Content contract (v0.1)

`report.json` is the **output of research**, not a prompt for the layout agent to invent findings.

## Required content

```json
{
  "meta": {
    "title": "Brand Product Intelligence",
    "brand": "Brand",
    "subtitle": "First-pass product scan",
    "region": "United States / brand website",
    "as_of": "2026-10-12",
    "prepared_by": "STILLEVO | 坐驰未来",
    "status": "DRAFT",
    "disclaimer": "Publicly observable information only; prices may change."
  },
  "summary": {
    "lead": "One neutral paragraph anchored in the research.",
    "findings": ["Observation 1", "Observation 2"],
    "scope": "Scope and limitations"
  },
  "products": [{
    "name": "Model name",
    "category": "Commuter",
    "positioning": "Short positioning summary",
    "price": {"display": "$1,899", "source_ids": ["S01"], "note": "US MSRP, observed YYYY-MM-DD"},
    "image": "images/model.jpg",
    "image_credit": "Official brand website; use subject to rights",
    "specs": [{"label": "Motor", "value": "250 W nominal", "source_ids": ["S01"]}],
    "notes": ["What this product suggests", "Missing attributes if any"],
    "source_ids": ["S01"]
  }],
  "sources": [{
    "id": "S01", "title": "Official product page", "url": "https://...",
    "accessed": "2026-10-12", "note": "Product specifications and MSRP"
  }],
  "open_questions": ["Something not confirmed by an official source"]
}
```

## Principles

- Only `meta`, `summary`, `products`, `sources`, `open_questions` are top-level fields. Unneeded fields can be omitted; renderer uses safe fallbacks.
- For products, `name`, `category`, `positioning`, `image`, `price.display`, `specs`, `notes`, `source_ids` are renderable. Source IDs are **references**, not proof that evidence has actually been checked.
- Use `"待核验"` rather than synthetic prices, range estimates, fake model counts, or invented specifications.
- For missing local images, render a clearly marked placeholder. Do not generate a similar-looking product image and present it as actual.
- Avoid product-comparison claims where prices differ by currency/market/date without a qualification.
- Cite every price and specification where source is available. Do not place source IDs beside interpretive commentary unless that source actually supports the claim.
- Preserve accessible web URLs in the evidence index. If a source has been deleted, mark it instead of silently replacing it.
- All paths are relative to the JSON file, no remote image fetching. The example references are deliberately reserved `example.com` placeholders.

## Mapping existing research material

Existing Word/HTML/Markdown -> manually or through Agent extraction -> factual JSON -> run Skill. Maintain source records during conversion. Extracted text is **not independently verified** just because it was formatted into a PDF.
