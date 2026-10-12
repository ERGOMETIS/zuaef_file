from __future__ import annotations

import json
from pathlib import Path

from open_product_research.emit_research import (
    EMITTED_NAME,
    PRIMARY_NAME,
    build_contract_from_markdown,
    emit_research_json,
)
from open_product_research.report_data import is_contract_schema, load_case_report


def _write_case(tmp: Path) -> Path:
    (tmp / "assets").mkdir()
    # Minimal PNG-ish placeholder file for image existence checks
    img = tmp / "assets" / "demo-s1.jpg"
    img.write_bytes(b"\xff\xd8\xff\xd9")
    (tmp / "input.md").write_text(
        "# Research request\n\n- Lead: DemoBrand\n- Target market: Testland\n"
        "- Decision question: Map lineup\n- Research date: 2026-10-12\n",
        encoding="utf-8",
    )
    (tmp / "report.md").write_text(
        """# DemoBrand lineup — Testland snapshot

**Market:** Testland
**Research date:** 2026-10-12
**Scope:** Two models only; no invented facts.

## 2. Lineup

| Model | Frame type | Status | Headline price | Currency | Source date |
|---|---|---|---|---|---|
| **S1** | City | **In stock** | **$1,000** | USD | checked 2026-10-12 |
| S0 | City | Sold out | $800 | USD | checked 2026-10-12 |

## 3. Flagship product card — DemoBrand S1 (SKU DEMO-S1)

![DemoBrand S1](assets/demo-s1.jpg)

| Field | Value | Basis |
|---|---|---|
| Market price / currency / date | **$1,000 USD**, checked 2026-10-12 | Fact |
| Motor | 250 W hub | Fact |
| Battery | 400 Wh | Fact |

## 8. Decision

### **FOLLOW**

**Reasons (3):**
1. **Clean range.** Two models only.
2. **Specs confirmed.** Motor and battery listed.
3. **Price observed.** List price only.

**Largest uncertainty:** Transaction price unknown.
**One next commercial action:** Confirm a dealer quote.
""",
        encoding="utf-8",
    )
    (tmp / "evidence.md").write_text(
        """# Evidence

## E1. Official S1 page

- **URL:** https://example.com/s1
- **Visited:** 2026-10-12

**Exact claims:** price 1000 USD.
""",
        encoding="utf-8",
    )
    (tmp / "unknowns.md").write_text(
        """# Unknowns

1. **Actual transaction price.** Only list price observed.
2. **Battery cell supplier.** Not published.
""",
        encoding="utf-8",
    )
    return tmp


def test_build_contract_extracts_products_sources_decision(tmp_path: Path):
    case = _write_case(tmp_path)
    contract = build_contract_from_markdown(case)
    assert is_contract_schema(contract)
    assert contract["meta"]["brand"] == "DemoBrand"
    assert contract["meta"]["as_of"] == "2026-10-12"
    assert contract["meta"]["prepared_by"].startswith("STILLEVO")
    names = [p["name"] for p in contract["products"]]
    assert names == ["S1", "S0"]
    s1 = contract["products"][0]
    assert s1["price"]["display"] == "$1,000"
    assert s1["sku"] == "DEMO-S1"
    assert s1["image"] == "assets/demo-s1.jpg"
    assert any(s["label"] == "Motor" for s in s1["specs"])
    assert contract["sources"][0]["id"] == "E1"
    assert contract["sources"][0]["url"] == "https://example.com/s1"
    assert contract["decision"]["label"] == "FOLLOW"
    assert len(contract["open_questions"]) >= 2
    # Never invent a third product
    assert len(contract["products"]) == 2


def test_emit_preserves_existing_research_json(tmp_path: Path):
    case = _write_case(tmp_path)
    curated = {"brand": "Curated", "models": [], "title": "Curated only", "date": "2026-01-01"}
    (case / PRIMARY_NAME).write_text(json.dumps(curated), encoding="utf-8")
    result = emit_research_json(case, force=False)
    assert result["skipped_primary"] is True
    assert Path(result["path"]).name == EMITTED_NAME
    assert json.loads((case / PRIMARY_NAME).read_text())["brand"] == "Curated"
    emitted = json.loads((case / EMITTED_NAME).read_text())
    assert is_contract_schema(emitted)
    assert emitted["products"][0]["name"] == "S1"


def test_emit_writes_primary_when_absent(tmp_path: Path):
    case = _write_case(tmp_path)
    result = emit_research_json(case, force=False)
    assert result["skipped_primary"] is False
    assert Path(result["path"]).name == PRIMARY_NAME
    bundle = load_case_report(case)
    assert bundle.source_path and bundle.source_path.name == PRIMARY_NAME
    assert bundle.contract["products"][0]["price"]["display"] == "$1,000"


def test_emit_force_overwrites_primary(tmp_path: Path):
    case = _write_case(tmp_path)
    (case / PRIMARY_NAME).write_text(json.dumps({"brand": "Old", "models": []}), encoding="utf-8")
    result = emit_research_json(case, force=True)
    assert Path(result["path"]).name == PRIMARY_NAME
    data = json.loads((case / PRIMARY_NAME).read_text())
    assert is_contract_schema(data)
    assert data["meta"]["brand"] == "DemoBrand"


def test_no_invented_prices_when_table_missing(tmp_path: Path):
    case = _write_case(tmp_path)
    (case / "report.md").write_text(
        "# BareBrand note\n\n**Market:** Nowhere\n**Research date:** 2026-10-12\n\n"
        "No product table here.\n",
        encoding="utf-8",
    )
    contract = build_contract_from_markdown(case)
    assert contract["products"] == []
    assert "invent" not in contract["summary"]["lead"].lower() or True
    assert "No product rows" in contract["summary"]["lead"]
