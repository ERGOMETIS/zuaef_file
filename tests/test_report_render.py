from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from open_product_research.report_data import (
    contract_to_typst,
    lab_to_contract,
    load_case_report,
)
from open_product_research.report_typst import find_typst


@pytest.fixture
def tiny_lab() -> dict:
    return {
        "title": "Fictional fixture lineup",
        "brand": "Fixture Brand",
        "market": "Test market",
        "date": "2026-01-01",
        "scope": "A deliberately fictional renderer fixture.",
        "range_summary": "Two fictional entries are represented.",
        "key_takeaways": [{"text": "One fixture observation.", "text_zh": "一条虚构测试观察。"}],
        "models": [
            {
                "name": "Fictional C1",
                "frame": "Test class",
                "status": "Fixture only",
                "featured": True,
                "price": {"display": "$1", "currency": "USD"},
                "image": None,
                "specs": {"motor": "fictional value"},
                "spec_source_ids": ["T1"],
            },
            {
                "name": "Fictional C2",
                "frame": "Test class",
                "status": "Not highlighted",
                "featured": False,
                "price": {"display": "待核验"},
                "image": None,
                "specs": {},
                "spec_source_ids": [],
            },
        ],
        "sources": [{"id": "T1", "title": "Fictional fixture source", "url": "https://example.com"}],
        "open_questions": ["What would a real source say?"],
    }


def test_lab_contract_typst_round_trip(tiny_lab: dict):
    contract = lab_to_contract(tiny_lab)
    assert [product["name"] for product in contract["products"]] == [
        "Fictional C1",
        "Fictional C2",
    ]
    assert contract["products"][0]["featured"] is True
    assert contract["products"][1]["featured"] is False
    assert contract["summary"]["findings"] == ["One fixture observation."]

    typst = contract_to_typst(contract)
    assert [model["name"] for model in typst["models"]] == ["Fictional C1", "Fictional C2"]
    assert typst["models"][0]["image"] is None
    assert typst["models"][0]["old_previous_price"] is None
    assert typst["decision"]["reasons"] == []
    assert typst["claims"] == []


def test_load_stillevo_contract_and_report_notes(tmp_path: Path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "research.json").write_text(
        json.dumps(
            {
                "meta": {
                    "title": "Fixture contract",
                    "brand": "Fixture Brand",
                    "subtitle": "Offline test",
                    "region": "Test",
                    "as_of": "2026-01-01",
                    "prepared_by": "STILLEVO | 坐驰未来",
                    "status": "DRAFT",
                    "disclaimer": "Fictional fixture.",
                },
                "summary": {"lead": "Fixture lead", "findings": [], "scope": "Fixture scope"},
                "products": [
                    {
                        "name": "Fictional C1",
                        "category": "Test",
                        "positioning": "Fixture",
                        "price": {"display": "待核验", "source_ids": ["MISSING"]},
                        "image": "assets/not-there.png",
                        "image_credit": "Fixture",
                        "specs": [],
                        "notes": [],
                        "source_ids": ["MISSING"],
                    }
                ],
                "sources": [],
                "open_questions": [],
            }
        ),
        encoding="utf-8",
    )
    bundle = load_case_report(tmp_path)
    assert bundle.contract["meta"]["brand"] == "Fixture Brand"
    assert bundle.typst_data["models"][0]["image"] is None
    assert any("Image not found" in note for note in bundle.notes)
    assert any("Unknown source ID MISSING" in note for note in bundle.notes)


def test_cli_render_help_contains_engine_and_lang():
    result = subprocess.run(
        [sys.executable, "-m", "open_product_research.cli", "render", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "--engine" in result.stdout
    assert "--lang" in result.stdout


def test_typst_compiles_tiny_fixture_offline(tmp_path: Path):
    if find_typst() is None:
        pytest.skip("Typst is not installed")
    contract = {
        "meta": {
            "title": "Fictional Typst fixture",
            "brand": "Fixture Brand",
            "subtitle": "Offline renderer test",
            "region": "Test market",
            "as_of": "2026-01-01",
            "prepared_by": "STILLEVO | 坐驰未来",
            "status": "DRAFT",
            "disclaimer": "Fictional fixture only.",
        },
        "summary": {
            "lead": "A tiny offline fixture.",
            "findings": ["No real product facts are represented."],
            "scope": "Renderer smoke test.",
        },
        "products": [
            {
                "name": "Fictional C1",
                "category": "Test class",
                "positioning": "Fixture only",
                "price": {"display": "待核验", "source_ids": []},
                "image": None,
                "image_credit": "",
                "specs": [],
                "notes": ["Fictional test data."],
                "source_ids": [],
            }
        ],
        "sources": [],
        "open_questions": [],
    }
    (tmp_path / "research.json").write_text(
        json.dumps(contract, ensure_ascii=False), encoding="utf-8"
    )
    from open_product_research.render import render_case

    result = render_case(tmp_path, engine="typst", lang="en")
    assert Path(result["pdf"]).is_file()
    assert result["pdf"].endswith("deliverables/report.pdf")
