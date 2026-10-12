# Report content contract (v0.1)

`report.json` is the output of research, not a prompt for a layout engine to
invent findings. Paths in `products[].image` and `cover_image` are local paths
relative to the JSON file (or to the case image base selected by the loader).
Remote image fetching is never performed during rendering.

## Required top-level fields

The root must contain:

- `meta`
- `summary`
- `products`
- `sources`
- `open_questions`

### `meta`

Required fields are `title`, `brand`, `subtitle`, `region`, `as_of`,
`prepared_by`, `status`, and `disclaimer`. `prepared_by` defaults to
`STILLEVO | 坐驰未来`; `demo` is optional. A bilingual document may also use
`title_zh`, `brand_zh`, `subtitle_zh`, and `region_zh`.

### `summary`

Required fields are `lead`, `findings` (a list), and `scope`. Each text may
have an optional `*_zh` twin: `lead_zh`, `findings_zh`, and `scope_zh`.

### `products[]`

Each product contains:

- `name`, `category`, `positioning`
- `price`: `{display, source_ids, note}`
- `image` (a relative local path) and `image_credit`
- `specs`: a list of `{label, value, source_ids}`
- `notes` (a list)
- `source_ids`

Optional product fields are `name_zh`, `category_zh`, `positioning_zh`,
`featured`, `sku`, `status`, `image_provenance`, plus renderer-preserved
`frame`, `old_previous_price`, `price_date`, `image_caption`, `spec_note`, and
bilingual value helpers. A product without a verified local image must render
an explicit missing-image placeholder; do not create a look-alike illustration.
Use `待核验` instead of synthetic prices, range estimates, fake model counts,
or invented specifications.

### `sources[]`

Each source contains `id`, `title`, `url`, `accessed`, and `note`. Optional
fields are `title_zh` and `urls` (additional URLs). Source IDs are references,
not proof that a claim was independently checked. Unknown referenced IDs are
reported in `deliverables/build_notes.txt`, not treated as a quality score and
not used as a reason to reject the report.

### `open_questions`

A list of unresolved questions. `open_questions_zh` is an optional bilingual
twin list.

## Optional Typst-rich extensions

These fields are preserved for the preferred Typst layout and may be ignored by
HTML when unused:

- `decision`
- `key_takeaways`
- `unresolved_conflicts`
- `evidence_gaps` and `evidence_gaps_zh`
- `range_summary` and `range_summary_zh`
- `range_callouts`
- `claims`
- `price_band`
- `cover_image` and `cover_caption` / `cover_caption_zh`
- `cover_source_ids`

The Typst adapter also accepts `flagship_specs` / `flagship_specs_zh` from the
working templates-lab JSON. Missing decision, risk, claim, source, image, SKU,
and previous-price keys are normalized to empty lists, safe strings, or `null`
values before compilation so a sparse contract still renders.

## Mapping existing case material

Loader precedence: `research.json` (curated or post-run emit) >
`research.emitted.json` > `deliverables/report.json` > Markdown heuristics.

After `product-research run`, `emit_research` builds a stillevo contract from
`report.md` / `evidence.md` / `unknowns.md` / `assets` (lineup tables, field
cards, local images, evidence E-ids). It never invents products, prices, or
sources. If a richer curated `research.json` already exists, the emitter writes
`research.emitted.json` instead of clobbering it (`emit-json --force` to
overwrite).

The thin Markdown heuristic (no JSON) only reads the H1 from `report.md`,
brand/market from `input.md`, unknowns lines, and HTTPS URLs from `evidence.md`.
Products stay empty; use `待核验` rather than inventing prices or specs.

Transparent PNG exports are preferred when a JPG has a sibling/provenance PNG
with alpha. Keep the alpha image and composite it on a light-gray template
panel. Never flood-fill black wheels or other dark product details.
