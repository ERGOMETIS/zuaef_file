# Report rendering

## Content versus layout

Research content is the source of truth. A structured case can contain
`research.json` at the case root or `deliverables/report.json` using the
stillevo-aligned contract documented in
`src/open_product_research/report_contract.md`. The loader translates the
working `templates-lab` shape (`brand` + `models`) into that contract, but it
never fills in an unobserved price, specification, SKU, image identity, or
commercial conclusion. If no JSON exists, the Markdown fallback extracts only
a title, input bullets, unknown-question lines, and evidence URLs; products
remain empty or `待核验`.

Layout engines consume the normalized data:

- **Typst** is the preferred PDF engine. The external `typst` executable is
  searched on `PATH` and then at `~/.local/bin/typst`. The packaged template
  receives JSON through `--input data=...`, a staged local image root through
  `--input assets=...`, and `--input lang=en|zh`.
- **HTML** writes a self-contained `report.html` or `report-zh.html` with
  embedded local images and the packaged CSS. If `weasyprint` is installed it
  also writes `report-html.pdf` (or `report-html-zh.pdf`) without replacing a
  Typst PDF; otherwise the HTML is still useful and the gap is recorded in
  `build_notes.txt`.
- **Legacy** retains the original Markdown → ReportLab path for old cases and
  environments without Typst.

Every engine writes or appends `deliverables/build_notes.txt`. It records the
engine and language, missing local images, unknown source IDs, staging or
optional-dependency limitations, and compile diagnostics. It is a build log,
not a quality score. `--preview` rasterizes the PDF just produced, including
`report-zh.pdf` for a Chinese Typst/legacy run.

## What was absorbed from stillevo

The integration keeps the evidence-first contract (`meta`, `summary`,
`products`, `sources`, and `open_questions`), source-ID chips, explicit
missing-image placeholders, a build-notes file, the visual inspection habit,
and the default `STILLEVO | 坐驰未来` prepared-by branding. The HTML path and
its visual checklist remain available as a review/fallback engine.

Typst replaced WeasyPrint as the preferred PDF engine because the
`templates-lab/typst/report.typ` design already provides the desired bilingual
brief layout and robust page composition. The stillevo HTML renderer remains
an independent, self-contained option rather than a second project copied into
this package.

The skill's demo SVGs are deliberately dropped as client art. Real local image
assets retain their provenance; transparent PNGs are kept and placed on a
light-gray panel rather than flood-filled, which could destroy dark wheels or
other product details.

The reference skill package remains on disk at
`stillevo-market-report-skill-v0.1/` for comparison and provenance. It is not
nested into the Python package as a second application.

## Visual inspection checklist

Before sharing a rendered brief, inspect the page PNGs rather than treating a
successful compile as approval:

- confirm the cover image is the exact local product asset, with no invented or
  demo artwork and no dark-wheel flood fill;
- check that product photos, placeholders, prices, source chips/citations, and
  the prepared-by/status line are visible and not clipped;
- scan page breaks for orphaned headings, empty panels, table overflow, and
  unreadable Chinese or long URLs;
- open representative source links and confirm their IDs correspond to the
  claims shown; unresolved IDs and missing files should remain in
  `build_notes.txt`; and
- verify the requested language, PDF filename, page count, and preview set
  match the run being reviewed.

## CLI examples

```bash
# Auto-select Typst when available, otherwise use the legacy renderer.
product-research render cases/brand-a --preview

product-research render cases/brand-a --engine typst --lang en --preview
product-research render cases/brand-a --engine typst --lang zh --preview
product-research render cases/brand-a --engine html --lang en
product-research render cases/brand-a --engine legacy --lang en
```

The command prints one JSON result. A normal Typst run leaves
`deliverables/report.pdf` (English) or `deliverables/report-zh.pdf` (Chinese),
plus the page PNGs under `preview/` when requested.
