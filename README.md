# Open Product Research Agent

**Source-backed competitor and product intelligence, from a brand URL to a client-readable report.**

A small, independently installable Python application built on **native PydanticAI + PydanticAI Harness**, not a replacement agent loop. It can investigate e-bikes, consumer products and OEM/ODM product portfolios; the domain-specific behavior lives in one native PydanticAI `AbstractCapability`.

**Status: v0.1 developer preview.** Local case initialization, document rendering, PNG page previews, URL and image mechanics are testable without model credentials. Full autonomous live-research quality is **not yet certified**. The presence of a PDF, passing unit tests or a successfully downloaded image is not evidence that commercial facts are correct.

## What it does

- Start with a brand URL, product name, model, or written purchasing/benchmarking question.
- Let the model investigate with official PydanticAI `WebSearch` and `WebFetch` (native provider or local fallbacks).
- Read/write a case folder with official Harness `FileSystem`, preserving drafts, direct URLs, unknowns and conflicts.
- Find genuine product-photo candidates on inspected pages, download real bytes and record provenance.
- Create a customer-facing Markdown report, then render a clickable, illustrated PDF and page-by-page previews.
- Separate official product specifications from proxy market indicators and business inference.

**Not included:** a crawler platform, automatic certification verification, a scraped supplier database, fake sales/FOB/MOQ estimates, multi-agent orchestration, SaaS UI, WorkLPG/ZUAEF dependencies, or a self-review engine that announces business truth.

## Installation

Python 3.11+ and internet access are required for installation and live model research. Native Harness versions track the PydanticAI release family; `pydantic-ai-harness 0.55.x` goes with `pydantic-ai-slim 2.55.x` through its dependencies. The public initial baseline is pinned to the 2026-10-09 matching release family; update both together after verification.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

To use a model, configure its provider according to PydanticAI's official documentation, e.g. `OPENAI_API_KEY` with `--model openai:...` or a configured compatible provider. **No API keys are bundled.** Use an API and model you have access to. A model that cannot call local web tools may not support this agent configuration.

## Run it

```bash
product-research init cases/brand-a \
  --lead 'https://brand.example/products' \
  --market 'Netherlands' \
  --goal 'E-bike model/SKU positioning and OEM/ODM product gaps'

# Set your provider key in the shell or a secrets manager; never commit it.
export OPENAI_API_KEY='...'
product-research run cases/brand-a --model openai:YOUR_MODEL --request-limit 45

# For a human-edited report:
product-research render cases/brand-a --preview
```

A finished case normally contains:

```text
cases/brand-a/
├── input.md
├── report.md                 # authoritative client narrative
├── evidence.md               # inspected URL and factual locator
├── catalog.md                # optional SKU/price matrix
├── unknowns.md               # unresolved material questions
├── assets/
│   ├── bike-model-<hash>.jpg # real downloaded photograph
│   └── image_sources.jsonl   # mechanical provenance, not identity certification
├── deliverables/report.pdf
└── preview/page-01.png
```

If the run stops prematurely, keep any useful partial `report.md`. Re-run `product-research render` after editing; a saved PDF does not imply accurate conclusions.

## How to use as a native Capability

```python
from pydantic_ai import Agent
from pydantic_ai.capabilities import LocalWorkspace, WebSearch, WebFetch
from pydantic_ai_harness import FileSystem
from open_product_research.capability import make_product_research_capability

case_dir = 'cases/brand-a'
agent = Agent(
    'openai:YOUR_MODEL',
    capabilities=[
        LocalWorkspace(case_dir),
        FileSystem(tools=['read_file', 'write_file', 'edit_file', 'list_directory']),
        WebSearch(local='duckduckgo'),
        WebFetch(local=True),
        make_product_research_capability(case_dir),
    ],
)
```

The application CLI uses precisely this path. You can compose the same Capability into any compatible PydanticAI agent. No ZUAEF or other host-specific types are imported.

## Research and visual rules

- Record **market, model year, SKU, currency, observation date** for comparable offers.
- Prefer **brand-specific and market-specific official pages** and original regulators/industry reports.
- Treat snippets as discovery, not proof that a page was read.
- A returned photograph is a **candidate** until its exact SKU/year/market has been inspected.
- Every report photo must be a real local `assets/...` file with original source metadata.
- Do not use generated images as product documentation; do not bundle third-party photos into this repository.
- Do not assert photo usage rights merely because an image is publicly accessible.
- Do not infer sales from reviews, actual OEM from visual similarity, or factory prices from retail tags.
- If no FactoryProfile exists, manufacturing feasibility and profit remain unknown.

PDF rendering supports headings, paragraphs, links, local Markdown images, lists, block quotes and readable tables. Each local product image should be on its own line, immediately followed by an appropriate specification table.

## Testing

```bash
python -m pytest -q
python -m compileall -q src
product-research render examples/sample-case --preview
```

The tests intentionally use synthetic local graphics for **renderer testing only**. They do not prove web research, real model execution, product/SKU identification, or report factual quality. To establish those, run a new real-brand case and have an operator verify decisive sources, images, commercial logic and every rendered PDF page.

## Architecture

```text
Native PydanticAI Agent
  + LocalWorkspace / FileSystem (official Harness)
  + WebSearch / WebFetch (official PydanticAI)
  + ProductResearchCapability (only custom business instructions + image tools)
             ↓
     report.md + evidence.md + assets/
             ↓
        deterministic PDF + preview
             ↓
        human business review
```

There is **no custom loop**, extra state machine, agent registry, receipt authority, scoring gate, model-driven PDF tool, or general research ontology. More mechanisms require a demonstrated operational or customer-result failure.

## Trust and safety

Remote page content is untrusted, can contain prompt injection and may change without notice. Run with a minimum-privilege provider key and a dedicated case workspace. `FileSystem` path restrictions are not a container sandbox. The image downloader rejects non-HTTPS and non-public host addresses, limits downloaded bytes, refuses unchecked redirects and saves only verified image bytes. This is a baseline mitigation, **not a complete network sandbox or defense against DNS rebinding**; production deployments should enforce outbound network restrictions outside Python.

## Licensing and attribution

Project source code: **MIT** (see `LICENSE`). PydanticAI/Harness are third-party dependencies with their own licenses. Report content, brand names, externally sourced imagery and screenshots are **not** re-licensed by this repository. The generated client reports must respect individual sources' applicable copyright and terms of use. See `THIRD_PARTY.md`.

Open issues and pull requests are welcome. No existing private project is required to install or run this repository.
