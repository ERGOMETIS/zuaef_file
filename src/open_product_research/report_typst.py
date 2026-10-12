"""Preferred Typst PDF renderer for structured product-research cases."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .report_data import (
    ReportBundle,
    append_build_notes,
    resolve_image_file,
)

TEMPLATE = Path(__file__).resolve().parent / "templates" / "typst" / "report.typ"


def find_typst() -> Path | None:
    """Find the external Typst binary without requiring a Python dependency."""

    found = shutil.which("typst")
    if found:
        return Path(found)
    fallback = Path.home() / ".local" / "bin" / "typst"
    if fallback.is_file() and fallback.stat().st_mode & 0o111:
        return fallback
    return None


def _stage_images(
    data: dict[str, Any],
    base_dir: Path,
    mirror: Path,
    notes: list[str],
) -> int:
    """Copy referenced local images into the Typst work directory.

    The staged data uses simple basenames, so the template can receive one
    predictable ``assets/`` root.  A collision is given a deterministic suffix;
    source files are never rewritten.
    """

    mirror.mkdir(parents=True, exist_ok=True)
    staged: dict[Path, str] = {}
    used_names: set[str] = set()

    def stage(value: Any) -> str | None:
        if not value:
            return None
        relative = str(value)
        source = resolve_image_file(base_dir, relative)
        if source is None:
            if f"Image not found: {relative}" not in notes:
                notes.append(f"Image not found: {relative}")
            return None
        source = source.resolve()
        if source in staged:
            return staged[source]
        name = source.name
        if name in used_names:
            stem, suffix = source.stem, source.suffix
            index = 2
            while f"{stem}-{index}{suffix}" in used_names:
                index += 1
            name = f"{stem}-{index}{suffix}"
        used_names.add(name)
        shutil.copy2(source, mirror / name)
        staged[source] = name
        return name

    data["cover_image"] = stage(data.get("cover_image"))
    for model in data.get("models") or []:
        if not isinstance(model, dict):
            continue
        model["image"] = stage(model.get("image"))
        # The current template does not display model.cover_image separately,
        # but keeping it reachable makes the staged JSON safe for extensions.
        model["cover_image"] = stage(model.get("cover_image"))
    return len(staged)


def _pdf_stats(path: Path) -> tuple[int | None, int | None, int | None]:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        pages = len(reader.pages)
        images = sum(len(page.images) for page in reader.pages)
        links = sum(
            1
            for page in reader.pages
            for annotation in page.get("/Annots", [])
            if annotation.get_object().get("/Subtype") == "/Link"
        )
        return pages, images, links
    except Exception:  # noqa: BLE001 - stats are supplemental to a successful PDF
        return None, None, None


def render_typst(
    bundle: ReportBundle,
    case_dir: Path,
    *,
    lang: str = "en",
) -> dict[str, Any]:
    """Compile a staged Typst report and return legacy-style render metadata."""

    if lang not in {"en", "zh"}:
        raise ValueError("lang must be 'en' or 'zh'")
    typst = find_typst()
    if typst is None:
        raise RuntimeError("typst binary not found on PATH or ~/.local/bin/typst")
    if not TEMPLATE.is_file():
        raise FileNotFoundError(f"Packaged Typst template not found: {TEMPLATE}")

    case_dir = Path(case_dir).expanduser().resolve()
    deliverables = case_dir / "deliverables"
    deliverables.mkdir(parents=True, exist_ok=True)
    work = deliverables / ".typst_work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    mirror = work / "assets"

    notes = list(bundle.notes)
    data = json.loads(json.dumps(bundle.typst_data, ensure_ascii=False))
    copied = _stage_images(data, bundle.base_dir, mirror, notes)
    data_path = work / "research.typst.json"
    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    shutil.copy2(TEMPLATE, work / "report.typ")

    filename = "report.pdf" if lang == "en" else "report-zh.pdf"
    output = deliverables / filename
    # The template receives paths relative to its staged work directory.  The
    # trailing slash is intentional and also exercises the template's asset
    # input contract.
    command = [
        str(typst),
        "compile",
        "--input",
        f"data={data_path.name}",
        "--input",
        "assets=assets/",
        "--input",
        f"lang={lang}",
        "report.typ",
        str(output),
    ]
    process = subprocess.run(command, check=False, cwd=work, capture_output=True, text=True)
    notes.append(f"engine=typst lang={lang} images_staged={copied}")
    if process.returncode != 0:
        detail = (process.stderr or process.stdout or "Typst returned a non-zero exit code").strip()
        notes.append("typst compile failed: " + detail[-2000:])
        build_notes = append_build_notes(case_dir, notes, header=f"typst render lang={lang}")
        raise RuntimeError(f"typst compile failed: {detail}")

    pages, images, links = _pdf_stats(output)
    build_notes = append_build_notes(case_dir, notes, header=f"typst render lang={lang}")
    return {
        "pdf": str(output),
        "engine": "typst",
        "lang": lang,
        "pages": pages,
        "embedded_images": images,
        "links": links,
        "images_staged": copied,
        "build_notes": str(build_notes),
        "notes": notes,
    }


# A descriptive alias is useful to callers that do not want to import the
# generic renderer name.
render_report_typst = render_typst
