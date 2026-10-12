from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from open_product_research.cli import init_case
from open_product_research.media import find_product_images, public_https_url, save_product_image
from open_product_research.render import render_preview, render_report


def test_init_creates_one_fresh_case(tmp_path: Path):
    case = tmp_path / "case-a"
    init_case(case, "https://example.com", "EU", "OEM opportunities")
    assert (case / "input.md").is_file()
    assert "EU" in (case / "input.md").read_text()
    with pytest.raises(FileExistsError):
        init_case(case, "https://example.com", "EU", "try overwrite")


def test_url_rejects_local_hosts(monkeypatch):
    with pytest.raises(ValueError):
        public_https_url("http://example.com")
    with pytest.raises(ValueError):
        public_https_url("https://localhost/admin")
    with pytest.raises(ValueError):
        public_https_url("https://127.0.0.1/admin")
    with pytest.raises(ValueError):
        public_https_url("https://attacker:pass@example.com/")


def test_image_capture_provenance_without_identity_claim(tmp_path: Path, monkeypatch):
    import io

    from open_product_research import media
    output = io.BytesIO()
    Image.new("RGB", (800, 520), (230, 230, 230)).save(output, "PNG")
    monkeypatch.setattr(media, "public_https_url", lambda x: x)
    monkeypatch.setattr(media, "_fetch", lambda *a, **kw: (output.getvalue(), "image/png", a[0]))
    result = save_product_image(tmp_path, "https://img.example/a.png", "https://brand.example/p", "Demo C1")
    assert (tmp_path / result["path"]).is_file()
    record = json.loads((tmp_path / "assets/image_sources.jsonl").read_text())
    assert record["identity_verified"] is False
    assert record["rights_verified"] is False
    assert record["source_page"] == "https://brand.example/p"


def test_image_discovery_uses_real_page_attributes(monkeypatch):
    from open_product_research import media
    data = b'<html><meta property="og:image" content="https://img.example/a.jpg"><img src="/bike.jpg" alt="model"></html>'
    monkeypatch.setattr(media, "_fetch", lambda *a, **kw: (data, "text/html", "https://brand.example/p"))
    found = find_product_images("https://brand.example/p")
    assert len(found) == 2
    assert found[1]["url"] == "https://brand.example/bike.jpg"


def test_pdf_embeds_local_image_and_links(tmp_path: Path):
    from pypdf import PdfReader
    (tmp_path / "assets").mkdir()
    Image.new("RGB", (900, 500), "white").save(tmp_path / "assets/sample.jpg")
    (tmp_path / "report.md").write_text(
        "# Fictional test report\n\n![Synthetic fixture — not a real product](assets/sample.jpg)\n\n"
        "| SKU | Battery |\n|---|---|\n| Fictional C1 | UNKNOWN |\n\n"
        "See [source docs](https://example.com/research).\n", encoding="utf-8"
    )
    output = render_report(tmp_path)
    assert output["pages"] >= 1
    assert output["embedded_images"] >= 1
    assert output["links"] >= 1
    assert len(render_preview(tmp_path)) >= 1
    pdf = PdfReader(output["pdf"])
    assert "Fictional test" in pdf.pages[0].extract_text()


def test_missing_image_is_not_silently_dropped(tmp_path: Path):
    (tmp_path / "report.md").write_text("# Report\n\n![A](assets/missing.png)", encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        render_report(tmp_path)
