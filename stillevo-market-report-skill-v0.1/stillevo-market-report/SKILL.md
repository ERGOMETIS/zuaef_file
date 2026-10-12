---
name: stillevo-market-report
description: Use when turning completed brand, competitor, OEM, product, or market research into a polished, evidence-linked client PDF and shareable HTML report. Convert structured research JSON and local product images into a consistent STILLEVO report; never invent product facts or substitute illustrative imagery for real product photos.
license: MIT
compatibility: Python 3.10+; WeasyPrint for PDF output. HTML output needs no extra runtime.
---

# STILLEVO Market Report

Turn **research results** into a readable, client-facing **report**, not into a new research or orchestration system.

## Use this skill when

- The research Agent has already collected brand/product facts, prices, specifications and their sources.
- A user needs an attractive, repeatable PDF or browser-readable HTML report.
- The user asks to re-layout a rough Word/Markdown/HTML/PDF research draft.

Do **not** use it to conduct market research, guess missing information, or claim that an illustration is an authentic product photo.

## Inputs and boundaries

1. Read `references/content-contract.md` for the JSON fields and source linkage. Read `references/design-guide.md` only when the report style must change.
2. Convert available research into one `report.json`. Keep the original units, market/currency context, observation date, source URL, and certainty. Use **“待核验”** for unknown facts; do not fill gaps from intuition.
3. Place permitted **real product photos** under a local `images/` folder; set each product's `image` to a relative path from the JSON file. If a photo is absent, leave the field empty: the report will display a missing-image placeholder, not a fake photo.
4. Build PDF and HTML with the script below. The script only renders; it does not fetch the web, call models, or modify research facts.
5. Open the PDF and visually inspect cover, long titles, spec rows, photos, and source index. Repair the **layout or source data** where necessary; avoid introducing a scoring or approval framework.
6. Deliver `report.pdf`, `report.html`, the input JSON, and source images as appropriate. Explain any open questions and whether the PDF is a draft.

## One-command example

From the skill root:

```bash
python -m pip install -r requirements.txt
python scripts/build_report.py --input examples/demo_report.json --out-dir /tmp/stillevo-report
```

Outputs:

- `/tmp/stillevo-report/report.pdf`
- `/tmp/stillevo-report/report.html` (self-contained, local assets embedded)
- `/tmp/stillevo-report/build_notes.txt` (missing images / source references only; not a quality score)

You may specify `--html-only` to generate HTML without WeasyPrint.

## Actual delivery workflow

- Research Agent / PydanticAI: produces research JSON and stores the evidence/images.
- This Skill: produces report assets; does not evaluate the business case or manage workers.
- WorkLPG: receives an Artifact path and a short Receipt, if that environment is connected.
- Human: reviews the report as a reader, especially authenticity and page layout, before delivery.

## Minimum operating rules

- **Evidence**: prices/specifications need a source ID. Missing source links are listed in `build_notes.txt`; never manufacture citations.
- **Images**: demo artwork in this package is only for layout testing. Replace with images of the actual product before delivering client work; check licensing and usage rights.
- **Currency**: preserve the site market, currency and date. Never infer conversion or compare currencies as if equivalent.
- **Status**: draft vs final status comes from the input. This renderer does not certify research quality.
- **Scope**: do not create dashboards, data pipelines, schemas, CI gates, autonomous correction loops, or agent management layers for a formatting task.

## Customize

- `assets/report.css`: visual design, A4 page layout, colors, typography.
- `scripts/build_report.py`: HTML section rendering, no framework required.
- `references/content-contract.md`: input contract and mapping advice.
- `references/design-guide.md`: art direction and manual visual inspection.

This is a small, portable example of the public Agent Skills structure, not a copy of internal ChatGPT skills or their runtime.
