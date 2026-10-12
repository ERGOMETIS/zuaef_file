"""Load, validate, and translate the supported report content contracts.

The renderer treats research content as evidence, not as an invitation to fill in
missing commercial facts.  Structured JSON is preferred.  The Markdown fallback
is intentionally narrow: it extracts a title, a few input bullets, questions,
and URLs, while products, prices, and specifications remain empty or ``待核验``.

Image handling deliberately preserves transparent product art.  A transparent
PNG may be composited on the light-gray panel by a template; this module never
flood-fills a black JPEG (which can also fill wheel spokes or other product
parts).
"""
from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

PREPARED_BY = "STILLEVO | 坐驰未来"
UNKNOWN = "待核验"

# These are the optional fields used by the Typst design.  They are copied from
# lab-shaped input instead of being re-created by the layout renderer.
TYPOGRAPHY_EXTENSIONS = (
    "decision",
    "key_takeaways",
    "unresolved_conflicts",
    "evidence_gaps",
    "evidence_gaps_zh",
    "range_summary",
    "range_summary_zh",
    "range_callouts",
    "claims",
    "price_band",
    "cover_image",
    "cover_caption",
    "cover_caption_zh",
    "cover_source_ids",
    "flagship_specs",
    "flagship_specs_zh",
)


@dataclass
class ReportBundle:
    """The three pieces a renderer needs for one case."""

    contract: dict[str, Any]
    typst_data: dict[str, Any]
    base_dir: Path
    notes: list[str] = field(default_factory=list)
    source_path: Path | None = None


def is_contract_schema(data: dict[str, Any]) -> bool:
    """Return whether *data* looks like the stillevo content contract."""

    return isinstance(data, dict) and "meta" in data and "products" in data


def is_lab_schema(data: dict[str, Any]) -> bool:
    """Return whether *data* looks like templates-lab ``research.json``."""

    return isinstance(data, dict) and "brand" in data and "models" in data and "meta" not in data


def detect_schema(data: dict[str, Any]) -> str | None:
    """Return ``contract``, ``lab``, or ``None`` for an unsupported root."""

    if is_contract_schema(data):
        return "contract"
    if is_lab_schema(data):
        return "lab"
    return None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _string(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def _source_ids(value: Any) -> list[str]:
    return [str(item) for item in _as_list(value) if item is not None and str(item).strip()]


def _note(notes: list[str], message: str) -> None:
    """Append a build note once per rendering operation."""

    if message not in notes:
        notes.append(message)


def _safe_relative_path(base_dir: Path, value: Any, notes: list[str] | None = None) -> Path | None:
    if not value:
        return None
    raw = Path(str(value))
    base = Path(base_dir).resolve()
    if raw.is_absolute():
        if notes is not None:
            _note(notes, f"Image path must be relative: {value}")
        return None
    resolved = (base / raw).resolve()
    try:
        resolved.relative_to(base)
    except ValueError:
        if notes is not None:
            _note(notes, f"Image path escapes base dir: {value}")
        return None
    return resolved


def _has_alpha(path: Path) -> bool:
    """Check PNG alpha without changing or re-encoding its pixels."""

    try:
        from PIL import Image

        with Image.open(path) as image:
            return "A" in image.getbands() or "transparency" in image.info
    except Exception:  # noqa: BLE001 - a bad image is handled as a missing asset
        return False


def _provenance_name(provenance: Any) -> str | None:
    if not provenance:
        return None
    parsed = urlparse(str(provenance))
    name = Path(parsed.path).name
    return name or None


def _png_candidates(base_dir: Path, original: Path, provenance: Any) -> list[Path]:
    """Find likely transparent siblings, ordered from most specific to broad."""

    candidates: list[Path] = []
    seen: set[Path] = set()
    roots = [original.parent, base_dir, base_dir / "assets"]
    provenance_name = _provenance_name(provenance)
    names: list[str] = []
    if provenance_name and provenance_name.lower().endswith(".png"):
        names.append(provenance_name)
    if original.suffix.lower() in {".jpg", ".jpeg"}:
        names.append(original.with_suffix(".png").name)
    for name in names:
        for root in roots:
            candidate = (root / name).resolve()
            if candidate not in seen:
                seen.add(candidate)
                candidates.append(candidate)
    # An alpha export often has a descriptive suffix rather than the exact JPG
    # name (for example ``*_alpha_on_f3f4f6.png``).
    for root in roots:
        if not root.is_dir():
            continue
        for pattern in (f"{original.stem}*alpha*.png", f"{original.stem}*.png"):
            for candidate in sorted(root.glob(pattern)):
                candidate = candidate.resolve()
                if candidate not in seen:
                    seen.add(candidate)
                    candidates.append(candidate)
    return candidates


def _relative_posix(path: Path, base_dir: Path) -> str:
    return path.resolve().relative_to(Path(base_dir).resolve()).as_posix()


def _pick_image(
    base_dir: Path,
    rel: str | None,
    notes: list[str],
    provenance: Any = None,
) -> str | None:
    """Resolve a local image and prefer an available transparent PNG.

    Paths remain relative to ``base_dir``.  A missing path is recorded and
    returned as ``None`` so templates can render an explicit placeholder.
    """

    if not rel:
        return None
    original = _safe_relative_path(base_dir, rel, notes)
    if original is None:
        return None

    if original.is_file():
        if original.suffix.lower() in {".jpg", ".jpeg"}:
            for candidate in _png_candidates(Path(base_dir).resolve(), original, provenance):
                if candidate.is_file() and _has_alpha(candidate):
                    _note(notes, f"Preferring alpha PNG over JPEG: {_relative_posix(candidate, Path(base_dir))}")
                    return _relative_posix(candidate, Path(base_dir))
        return _relative_posix(original, Path(base_dir))

    # If the referenced JPG was not copied but its transparent export was, use
    # the export.  This is also useful for cases assembled from imagefetch logs.
    for candidate in _png_candidates(Path(base_dir).resolve(), original, provenance):
        if candidate.is_file() and (_has_alpha(candidate) or original.suffix.lower() not in {".jpg", ".jpeg"}):
            _note(notes, f"Image missing; using PNG: {_relative_posix(candidate, Path(base_dir))}")
            return _relative_posix(candidate, Path(base_dir))
    _note(notes, f"Image not found: {rel}")
    return None


def resolve_image_file(base_dir: Path, rel: str | None) -> Path | None:
    """Return a safe existing image path for HTML/base64 embedding."""

    if not rel:
        return None
    path = _safe_relative_path(Path(base_dir), rel)
    return path if path is not None and path.is_file() else None


def _spec_key(label: Any) -> str:
    text = _string(label, "other").lower()
    key = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return key or "other"


def _spec_values(model: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = model.get("specs")
    raw_zh = model.get("specs_zh") if isinstance(model.get("specs_zh"), dict) else {}
    values: dict[str, Any] = {}
    values_zh: dict[str, Any] = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            values[str(key)] = value
            if str(key) in raw_zh:
                values_zh[str(key)] = raw_zh[str(key)]
    elif isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            key = _spec_key(item.get("label"))
            values[key] = item.get("value")
            if "value_zh" in item:
                values_zh[key] = item.get("value_zh")
    for key, value in raw_zh.items():
        values_zh.setdefault(str(key), value)
    return values, values_zh


def _spec_rows(model: dict[str, Any]) -> list[dict[str, Any]]:
    values, values_zh = _spec_values(model)
    source_default = _source_ids(model.get("spec_source_ids") or model.get("source_ids"))
    rows: list[dict[str, Any]] = []
    raw = model.get("specs")
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            key = _spec_key(item.get("label"))
            row = {
                "label": item.get("label") or key.replace("_", " ").title(),
                "value": item.get("value"),
                "source_ids": _source_ids(item.get("source_ids") or source_default),
            }
            if key in values_zh:
                row["value_zh"] = values_zh[key]
            rows.append(row)
        return rows
    for key, value in values.items():
        row = {
            "label": str(key).replace("_", " ").title(),
            "value": UNKNOWN if value is None else value,
            "source_ids": list(source_default),
        }
        if key in values_zh:
            row["value_zh"] = values_zh[key]
        rows.append(row)
    return rows


def lab_to_contract(lab: dict[str, Any], *, base_dir: Path | None = None) -> dict[str, Any]:
    """Map every templates-lab model into the stillevo-aligned contract.

    ``base_dir`` is optional for direct conversion tests.  When supplied, local
    image paths are checked and transparent PNG siblings are preferred.
    """

    if not isinstance(lab, dict):
        raise TypeError("lab must be a dictionary")
    notes: list[str] = []
    base = Path(base_dir).resolve() if base_dir is not None else None
    brand = _string(lab.get("brand"), "Unnamed brand")
    as_of = _string(lab.get("date"), UNKNOWN)
    products: list[dict[str, Any]] = []

    for raw_model in _as_list(lab.get("models")):
        model = raw_model if isinstance(raw_model, dict) else {}
        spec_values, spec_values_zh = _spec_values(model)
        spec_source_ids = _source_ids(model.get("spec_source_ids") or model.get("source_ids"))
        specs = _spec_rows(model)
        price = model.get("price") if isinstance(model.get("price"), dict) else {}
        price_source_ids = _source_ids(
            price.get("source_ids") or model.get("price_source_ids") or spec_source_ids
        )
        raw_image = model.get("image")
        image = (
            _pick_image(base, raw_image, notes, model.get("image_provenance"))
            if base is not None and raw_image
            else raw_image
        )
        product_notes = [item for item in _as_list(model.get("notes")) if item]
        if model.get("spec_note") and model.get("spec_note") not in product_notes:
            product_notes.append(model["spec_note"])
        product: dict[str, Any] = {
            "name": model.get("name") or UNKNOWN,
            "name_zh": model.get("name_zh"),
            "category": model.get("category") or model.get("frame") or "",
            "category_zh": model.get("category_zh") or model.get("frame_zh"),
            "positioning": model.get("positioning") or model.get("status") or "",
            "positioning_zh": model.get("positioning_zh") or model.get("status_zh"),
            "price": {
                "display": price.get("display") or UNKNOWN,
                "display_zh": price.get("display_zh"),
                "source_ids": price_source_ids,
                "note": price.get("note") or model.get("price_date") or "",
                "note_zh": price.get("note_zh") or model.get("price_date_zh"),
                "currency": price.get("currency"),
                "currency_zh": price.get("currency_zh"),
            },
            "image": image,
            "image_credit": model.get("image_credit") or model.get("image_caption") or "",
            "image_credit_zh": model.get("image_credit_zh") or model.get("image_caption_zh"),
            "specs": specs,
            "notes": product_notes,
            "source_ids": _source_ids(model.get("source_ids") or spec_source_ids),
            "featured": bool(model.get("featured")),
            "sku": model.get("sku"),
            "status": model.get("status"),
            "status_zh": model.get("status_zh"),
            "image_provenance": model.get("image_provenance"),
            # Typst-compatible extensions carried through the conversion.
            "frame": model.get("frame"),
            "frame_zh": model.get("frame_zh"),
            "old_previous_price": copy.deepcopy(model.get("old_previous_price")),
            "price_date": model.get("price_date"),
            "price_date_zh": model.get("price_date_zh"),
            "image_caption": model.get("image_caption"),
            "image_caption_zh": model.get("image_caption_zh"),
            "spec_note": model.get("spec_note"),
            "spec_note_zh": model.get("spec_note_zh"),
            "spec_source_ids": spec_source_ids,
            "specs_map": copy.deepcopy(spec_values),
            "specs_map_zh": copy.deepcopy(spec_values_zh),
        }
        products.append(product)

    findings: list[str] = []
    findings_zh: list[str] = []
    for raw_item in _as_list(lab.get("key_takeaways")):
        item = raw_item if isinstance(raw_item, dict) else {"text": raw_item}
        if item.get("text"):
            findings.append(str(item["text"]))
        if item.get("text_zh"):
            findings_zh.append(str(item["text_zh"]))

    sources: list[dict[str, Any]] = []
    for raw_source in _as_list(lab.get("sources")):
        source = raw_source if isinstance(raw_source, dict) else {}
        entry: dict[str, Any] = {
            "id": source.get("id") or UNKNOWN,
            "title": source.get("title") or "Untitled source",
            "title_zh": source.get("title_zh"),
            "url": source.get("url"),
            "urls": list(source.get("urls") or []),
            "accessed": source.get("accessed") or as_of,
            "note": source.get("note") or "",
        }
        if "image_urls" in source:
            entry["image_urls"] = list(source.get("image_urls") or [])
        sources.append(entry)

    cover_image = lab.get("cover_image")
    if base is not None and cover_image:
        cover_image = _pick_image(base, cover_image, notes)

    meta = {
        "title": lab.get("title") or f"{brand} Product Intelligence",
        "title_zh": lab.get("title_zh"),
        "brand": brand,
        "brand_zh": lab.get("brand_zh"),
        "subtitle": lab.get("subtitle") or lab.get("scope") or "Product line · pricing · specifications · evidence",
        "subtitle_zh": lab.get("subtitle_zh") or lab.get("scope_zh"),
        "region": lab.get("market") or "",
        "region_zh": lab.get("market_zh"),
        "as_of": as_of,
        "prepared_by": lab.get("prepared_by") or PREPARED_BY,
        "status": lab.get("status") or "DRAFT",
        "disclaimer": lab.get("disclaimer")
        or "Publicly observable information only; list prices are not transactions; information may change.",
    }
    if "demo" in lab:
        meta["demo"] = bool(lab.get("demo"))

    summary = {
        "lead": lab.get("range_summary") or "",
        "lead_zh": lab.get("range_summary_zh"),
        "findings": findings,
        "findings_zh": findings_zh,
        "scope": lab.get("scope") or "",
        "scope_zh": lab.get("scope_zh"),
    }
    contract: dict[str, Any] = {
        "meta": meta,
        "summary": summary,
        "products": products,
        "sources": sources,
        "open_questions": list(lab.get("open_questions") or []),
        "open_questions_zh": list(lab.get("open_questions_zh") or []),
    }

    # Preserve the Typst-rich fields verbatim where present.  Conversion only
    # changes the fields whose shape differs between lab and the content contract.
    for key in TYPOGRAPHY_EXTENSIONS:
        if key in lab and key not in {"cover_image"}:
            contract[key] = copy.deepcopy(lab[key])
    contract["cover_image"] = cover_image
    if notes:
        contract["_conversion_notes"] = notes
    return contract


def _price_for_typst(value: Any, *, display_fallback: str = UNKNOWN) -> dict[str, Any]:
    if isinstance(value, dict):
        price = copy.deepcopy(value)
    elif value is None:
        price = {}
    else:
        price = {"display": str(value)}
    price.setdefault("display", display_fallback)
    price.setdefault("display_zh", price.get("display") or display_fallback)
    price.setdefault("currency", "")
    price.setdefault("currency_zh", price.get("currency") or "")
    price.setdefault("label", None)
    price.setdefault("label_zh", price.get("label"))
    return price


def _spec_maps(product: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    raw_map = product.get("specs_map")
    raw_map_zh = product.get("specs_map_zh")
    if isinstance(raw_map, dict):
        values = copy.deepcopy(raw_map)
    else:
        values = {}
        for raw_spec in _as_list(product.get("specs")):
            if not isinstance(raw_spec, dict):
                continue
            values[_spec_key(raw_spec.get("label"))] = raw_spec.get("value")
    if isinstance(raw_map_zh, dict):
        values_zh = copy.deepcopy(raw_map_zh)
    else:
        values_zh = {}
        for raw_spec in _as_list(product.get("specs")):
            if not isinstance(raw_spec, dict):
                continue
            key = _spec_key(raw_spec.get("label"))
            if "value_zh" in raw_spec:
                values_zh[key] = raw_spec.get("value_zh")
    for key, value in values.items():
        values_zh.setdefault(key, copy.deepcopy(value))
    return values, values_zh


def _normalise_decision(value: Any) -> dict[str, Any]:
    decision = value if isinstance(value, dict) else {}
    reasons = [str(item) for item in _as_list(decision.get("reasons")) if item is not None]
    reasons_zh = [str(item) for item in _as_list(decision.get("reasons_zh")) if item is not None]
    if len(reasons_zh) < len(reasons):
        reasons_zh.extend(reasons[len(reasons_zh) :])
    return {
        "label": decision.get("label") or "REVIEW",
        "label_zh": decision.get("label_zh") or decision.get("label") or "复核",
        "reasons": reasons,
        "reasons_zh": reasons_zh,
        "largest_uncertainty": decision.get("largest_uncertainty") or "",
        "largest_uncertainty_zh": decision.get("largest_uncertainty_zh")
        or decision.get("largest_uncertainty")
        or "",
        "next_commercial_action": decision.get("next_commercial_action") or "",
        "next_commercial_action_zh": decision.get("next_commercial_action_zh")
        or decision.get("next_commercial_action")
        or "",
    }


def _normalise_takeaways(value: Any, summary: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = _as_list(value)
    if not raw_items:
        raw_items = [
            {"text": text, "text_zh": None, "inference": False, "source_ids": []}
            for text in _as_list(summary.get("findings"))
            if text
        ]
    findings_zh = _as_list(summary.get("findings_zh"))
    output: list[dict[str, Any]] = []
    for index, raw_item in enumerate(raw_items):
        item = raw_item if isinstance(raw_item, dict) else {"text": raw_item}
        text = item.get("text") or ""
        text_zh = item.get("text_zh")
        if text_zh is None and index < len(findings_zh):
            text_zh = findings_zh[index]
        output.append(
            {
                "text": str(text),
                "text_zh": str(text_zh) if text_zh is not None else str(text),
                "inference": bool(item.get("inference")),
                "source_ids": _source_ids(item.get("source_ids")),
            }
        )
    return output


def _normalise_conflicts(value: Any) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for raw_item in _as_list(value):
        item = raw_item if isinstance(raw_item, dict) else {"detail": raw_item}
        output.append(
            {
                "title": item.get("title") or "Unresolved issue",
                "title_zh": item.get("title_zh") or item.get("title") or "未解决事项",
                "detail": item.get("detail") or "",
                "detail_zh": item.get("detail_zh") or item.get("detail") or "",
                "status": item.get("status") or "UNRESOLVED",
                "status_zh": item.get("status_zh") or item.get("status") or "未解决",
                "source_ids": _source_ids(item.get("source_ids")),
            }
        )
    return output


def _normalise_callouts(value: Any) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for raw_item in _as_list(value):
        item = raw_item if isinstance(raw_item, dict) else {"text": raw_item}
        output.append(
            {
                "title": item.get("title") or "NOTE",
                "title_zh": item.get("title_zh") or item.get("title") or "注",
                "text": item.get("text") or "",
                "text_zh": item.get("text_zh") or item.get("text") or "",
                "source_ids": _source_ids(item.get("source_ids")),
            }
        )
    return output


def _normalise_claims(value: Any) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for index, raw_item in enumerate(_as_list(value), 1):
        item = raw_item if isinstance(raw_item, dict) else {"text": raw_item}
        output.append(
            {
                "id": item.get("id") or f"C{index}",
                "text": item.get("text") or "",
                "text_zh": item.get("text_zh") or item.get("text") or "",
                "inference": bool(item.get("inference")),
                "source_ids": _source_ids(item.get("source_ids")),
            }
        )
    return output


def contract_to_typst(contract: dict[str, Any]) -> dict[str, Any]:
    """Produce the templates-lab-shaped JSON consumed by ``report.typ``.

    Every key accessed by the Typst template is materialised here.  Missing
    decision/risk/claim sections become empty lists or neutral empty strings;
    nullable product fields such as ``image``, ``sku`` and
    ``old_previous_price`` remain ``null`` so the template can show its own
    placeholders.
    """

    if not isinstance(contract, dict):
        raise TypeError("contract must be a dictionary")
    meta = contract.get("meta") if isinstance(contract.get("meta"), dict) else {}
    summary = contract.get("summary") if isinstance(contract.get("summary"), dict) else {}
    raw_products = contract.get("products") if isinstance(contract.get("products"), list) else []
    models: list[dict[str, Any]] = []

    for raw_product in raw_products:
        product = raw_product if isinstance(raw_product, dict) else {}
        values, values_zh = _spec_maps(product)
        price = _price_for_typst(product.get("price"))
        specs_source_ids = _source_ids(
            product.get("spec_source_ids")
            or product.get("source_ids")
            or [sid for spec in _as_list(product.get("specs")) if isinstance(spec, dict) for sid in _as_list(spec.get("source_ids"))]
        )
        featured = bool(product["featured"]) if "featured" in product else True
        old_price = product.get("old_previous_price")
        if old_price is not None:
            old_price = _price_for_typst(old_price)
        model = {
            "name": product.get("name") or UNKNOWN,
            "name_zh": product.get("name_zh") or product.get("name") or UNKNOWN,
            "frame": product.get("frame") or product.get("category") or "",
            "frame_zh": product.get("frame_zh")
            or product.get("category_zh")
            or product.get("category")
            or "",
            "status": product.get("status") or product.get("positioning") or "",
            "status_zh": product.get("status_zh")
            or product.get("positioning_zh")
            or product.get("positioning")
            or "",
            "price": price,
            "old_previous_price": old_price,
            "price_date": product.get("price_date") or price.get("note") or "",
            "price_date_zh": product.get("price_date_zh")
            or price.get("note_zh")
            or price.get("note")
            or "",
            "featured": featured,
            "sku": product.get("sku"),
            "image": product.get("image"),
            "cover_image": product.get("image"),
            "image_caption": product.get("image_caption") or product.get("image_credit"),
            "image_caption_zh": product.get("image_caption_zh")
            or product.get("image_credit_zh")
            or product.get("image_credit"),
            "image_provenance": product.get("image_provenance"),
            "specs": values,
            "specs_zh": values_zh,
            "spec_note": product.get("spec_note"),
            "spec_note_zh": product.get("spec_note_zh") or product.get("spec_note"),
            "spec_source_ids": specs_source_ids,
        }
        models.append(model)

    raw_sources = contract.get("sources") if isinstance(contract.get("sources"), list) else []
    sources: list[dict[str, Any]] = []
    for raw_source in raw_sources:
        source = raw_source if isinstance(raw_source, dict) else {}
        sources.append(
            {
                "id": source.get("id") or UNKNOWN,
                "title": source.get("title") or "Untitled source",
                "title_zh": source.get("title_zh") or source.get("title") or "未命名来源",
                "url": source.get("url"),
                "urls": list(source.get("urls") or []),
                "image_urls": list(source.get("image_urls") or []),
                "accessed": source.get("accessed") or "",
                "note": source.get("note") or "",
            }
        )

    price_band = contract.get("price_band") if isinstance(contract.get("price_band"), dict) else {}
    if not price_band:
        displays = [
            (product.get("price") or {}).get("display")
            for product in raw_products
            if isinstance(product, dict) and isinstance(product.get("price"), dict) and product["price"].get("display")
        ]
        display = " / ".join(str(item) for item in displays) if displays else UNKNOWN
        price_band = {
            "display": display,
            "display_zh": display,
            "basis": "Observed prices from the research contract.",
            "basis_zh": "来自研究合同的观察价格。",
            "currency": "",
            "currency_zh": "",
        }
    else:
        price_band = copy.deepcopy(price_band)
        price_band.setdefault("display", UNKNOWN)
        price_band.setdefault("display_zh", price_band.get("display") or UNKNOWN)
        price_band.setdefault("basis", "")
        price_band.setdefault("basis_zh", price_band.get("basis") or "")

    open_questions = [str(item) for item in _as_list(contract.get("open_questions")) if item is not None]
    open_questions_zh = [str(item) for item in _as_list(contract.get("open_questions_zh")) if item is not None]
    if len(open_questions_zh) < len(open_questions):
        open_questions_zh.extend(open_questions[len(open_questions_zh) :])
    evidence_gaps = [str(item) for item in _as_list(contract.get("evidence_gaps")) if item is not None]
    evidence_gaps_zh = [str(item) for item in _as_list(contract.get("evidence_gaps_zh")) if item is not None]
    if len(evidence_gaps_zh) < len(evidence_gaps):
        evidence_gaps_zh.extend(evidence_gaps[len(evidence_gaps_zh) :])

    cover_image = contract.get("cover_image")
    if cover_image is None:
        cover_image = next((model.get("image") for model in models if model.get("image")), None)
    typst = {
        "title": meta.get("title") or "Product Intelligence",
        "title_zh": meta.get("title_zh") or meta.get("title") or "产品情报",
        "brand": meta.get("brand") or "Brand",
        "brand_zh": meta.get("brand_zh") or meta.get("brand") or "品牌",
        "market": meta.get("region") or "",
        "market_zh": meta.get("region_zh") or meta.get("region") or "",
        "scope": summary.get("scope") or meta.get("subtitle") or "",
        "scope_zh": summary.get("scope_zh") or meta.get("subtitle_zh") or summary.get("scope") or "",
        "date": meta.get("as_of") or UNKNOWN,
        "date_zh": meta.get("as_of_zh") or meta.get("as_of") or UNKNOWN,
        "cover_image": cover_image,
        "cover_caption": contract.get("cover_caption") or "",
        "cover_caption_zh": contract.get("cover_caption_zh") or contract.get("cover_caption") or "",
        "cover_source_ids": _source_ids(contract.get("cover_source_ids")),
        "price_band": price_band,
        "models": models,
        "flagship_specs": copy.deepcopy(contract.get("flagship_specs") or (models[0]["specs"] if models else {})),
        "flagship_specs_zh": copy.deepcopy(
            contract.get("flagship_specs_zh") or (models[0].get("specs_zh") if models else {})
        ),
        "decision": _normalise_decision(contract.get("decision")),
        "range_summary": contract.get("range_summary") or summary.get("lead") or "",
        "range_summary_zh": contract.get("range_summary_zh")
        or summary.get("lead_zh")
        or summary.get("lead")
        or "",
        "range_callouts": _normalise_callouts(contract.get("range_callouts")),
        "key_takeaways": _normalise_takeaways(contract.get("key_takeaways"), summary),
        "unresolved_conflicts": _normalise_conflicts(contract.get("unresolved_conflicts")),
        "evidence_gaps": evidence_gaps,
        "evidence_gaps_zh": evidence_gaps_zh,
        "open_questions": open_questions,
        "open_questions_zh": open_questions_zh,
        "claims": _normalise_claims(contract.get("claims")),
        "sources": sources,
    }
    return typst


def _source_id_references(value: Any, path: str = "") -> list[tuple[str, str]]:
    """Find every ``source_ids``-style list in a nested JSON value."""

    found: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if key.endswith("source_ids"):
                for source_id in _as_list(child):
                    if source_id is not None and str(source_id).strip():
                        found.append((str(source_id), child_path))
            else:
                found.extend(_source_id_references(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_source_id_references(child, f"{path}[{index}]"))
    return found


def validate_source_ids(contract: dict[str, Any], notes: list[str]) -> None:
    """Record unknown source references without rejecting a report."""

    known = {str(source.get("id")) for source in _as_list(contract.get("sources")) if isinstance(source, dict) and source.get("id")}
    for source_id, path in _source_id_references(contract):
        if source_id not in known:
            _note(notes, f"Unknown source ID {source_id}: {path}")


def _heuristic_from_markdown(case_dir: Path, notes: list[str]) -> dict[str, Any]:
    """Extract only safe Markdown hints; never invent products, prices, or specs.

    The fallback reads the first H1 from ``report.md``; ``lead``, ``brand``,
    ``brand/url`` and ``market`` bullets from ``input.md``; non-heading lines
    from ``unknowns.md`` as open questions; and unique HTTPS URLs from
    ``evidence.md`` as source records.  Product rows stay empty because
    Markdown headings are not reliable SKU evidence.
    """

    _note(
        notes,
        "Heuristic Markdown extraction only: products/prices/specs remain empty or 待核验; prefer research.json.",
    )
    report = case_dir / "report.md"
    evidence = case_dir / "evidence.md"
    unknowns = case_dir / "unknowns.md"
    input_md = case_dir / "input.md"

    title = "Product Intelligence"
    if report.is_file():
        for line in report.read_text(encoding="utf-8").splitlines():
            if line.lstrip().startswith("# "):
                title = line.lstrip()[2:].strip() or title
                break

    brand, market = "Unnamed brand", ""
    if input_md.is_file():
        for line in input_md.read_text(encoding="utf-8").splitlines():
            match = re.match(r"^\s*[-*]\s*([^:]+):\s*(.*?)\s*$", line)
            if not match:
                continue
            key, value = match.group(1).strip().lower(), match.group(2).strip()
            if key in {"brand", "lead", "brand/url", "url", "company"} and value:
                brand = value
            elif key in {"target market", "market", "region"}:
                market = value

    questions: list[str] = []
    if unknowns.is_file():
        for line in unknowns.read_text(encoding="utf-8").splitlines():
            item = line.strip().lstrip("-* ").strip()
            if item and not item.startswith("#"):
                questions.append(item)

    sources: list[dict[str, Any]] = []
    if evidence.is_file():
        text = evidence.read_text(encoding="utf-8")
        seen: set[str] = set()
        for url in re.findall(r"https?://[^\s\)\]\>\"']+", text):
            url = url.rstrip(".,;:")
            if url in seen:
                continue
            seen.add(url)
            host = urlparse(url).netloc or "source"
            sources.append(
                {
                    "id": f"E{len(sources) + 1}",
                    "title": host,
                    "url": url,
                    "accessed": UNKNOWN,
                    "note": "Extracted from evidence.md URL mention",
                }
            )

    return {
        "meta": {
            "title": title,
            "brand": brand,
            "subtitle": "Heuristic draft from Markdown case files",
            "region": market,
            "as_of": UNKNOWN,
            "prepared_by": PREPARED_BY,
            "status": "DRAFT",
            "disclaimer": "Heuristic extraction; verify against primary sources before delivery.",
        },
        "summary": {
            "lead": "Structured product rows were not available; only Markdown heuristics were applied.",
            "findings": [],
            "scope": "No invented product facts. Supply research.json for a full Typst/HTML brief.",
        },
        "products": [],
        "sources": sources,
        "open_questions": questions,
    }


def load_json_file(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"Report JSON root must be an object: {path}")
    return data


def _resolve_contract_images(contract: dict[str, Any], base_dir: Path, notes: list[str]) -> dict[str, Any]:
    resolved = copy.deepcopy(contract)
    for product in _as_list(resolved.get("products")):
        if not isinstance(product, dict):
            continue
        raw_image = product.get("image")
        product["image"] = _pick_image(
            base_dir,
            raw_image,
            notes,
            product.get("image_provenance"),
        ) if raw_image else None
    if resolved.get("cover_image"):
        resolved["cover_image"] = _pick_image(base_dir, resolved.get("cover_image"), notes)
    return resolved


def load_case_report(case_dir: Path) -> ReportBundle:
    """Load a case as ``contract``, Typst JSON, base image directory, and notes.

    Priority: ``research.json`` (curated or post-run emit) >
    ``research.emitted.json`` (emitter audit copy when primary already existed) >
    ``deliverables/report.json``. If none exist, Markdown heuristics only extract
    title/brand/market/questions/URLs — never products, prices, or specs.
    """

    case_dir = Path(case_dir).expanduser().resolve()
    notes: list[str] = []
    candidates = [
        case_dir / "research.json",
        case_dir / "research.emitted.json",
        case_dir / "deliverables" / "report.json",
    ]
    source_path = next((candidate for candidate in candidates if candidate.is_file()), None)
    if source_path is None:
        contract = _heuristic_from_markdown(case_dir, notes)
        typst_data = contract_to_typst(contract)
        validate_source_ids(contract, notes)
        return ReportBundle(contract, typst_data, case_dir, notes, None)

    data = load_json_file(source_path)
    # A deliverables/report.json is commonly emitted by a case-level renderer;
    # keep case/assets as its image root when that folder exists.  Otherwise
    # paths are relative to the JSON's own directory, as required by the
    # contract and by templates-lab research.json.
    base_dir = source_path.parent
    if source_path.parent.name == "deliverables" and (case_dir / "assets").is_dir():
        base_dir = case_dir
        _note(notes, "Using case root as image base for deliverables/report.json")

    schema = detect_schema(data)
    if schema == "lab":
        contract = lab_to_contract(data, base_dir=base_dir)
        notes.extend(contract.pop("_conversion_notes", []))
        contract = _resolve_contract_images(contract, base_dir, notes)
        notes.append(f"Loaded templates-lab schema from {source_path.name}")
    elif schema == "contract":
        contract = _resolve_contract_images(data, base_dir, notes)
        notes.append(f"Loaded stillevo contract from {source_path.name}")
    else:
        raise ValueError(
            f"Unrecognized report JSON schema in {source_path}: "
            "expected stillevo contract (meta+products) or lab research (brand+models)"
        )

    validate_source_ids(contract, notes)
    typst_data = contract_to_typst(contract)
    return ReportBundle(contract, typst_data, base_dir.resolve(), notes, source_path.resolve())


def write_contract(case_dir: Path, contract: dict[str, Any]) -> Path:
    """Write a contract to the conventional deliverables location."""

    output = Path(case_dir).resolve() / "deliverables"
    output.mkdir(parents=True, exist_ok=True)
    path = output / "report.json"
    path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def write_build_notes(case_dir: Path, notes: list[str], *, header: str = "") -> Path:
    """Overwrite build notes for callers that want a fresh report log."""

    output = Path(case_dir).resolve() / "deliverables"
    output.mkdir(parents=True, exist_ok=True)
    path = output / "build_notes.txt"
    unique = list(dict.fromkeys(str(item) for item in notes if item))
    body = []
    if header:
        body.append(header.rstrip())
    body.append("\n".join(unique) if unique else "No missing image/source-ID references detected.")
    path.write_text("\n".join(body).rstrip() + "\n", encoding="utf-8")
    return path


def append_build_notes(case_dir: Path, notes: list[str], *, header: str = "") -> Path:
    """Append a de-duplicated build entry, preserving earlier language runs."""

    output = Path(case_dir).resolve() / "deliverables"
    output.mkdir(parents=True, exist_ok=True)
    path = output / "build_notes.txt"
    unique = list(dict.fromkeys(str(item) for item in notes if item))
    entry = []
    if header:
        entry.append(header.rstrip())
    entry.append("\n".join(unique) if unique else "No missing image/source-ID references detected.")
    prior = path.read_text(encoding="utf-8").rstrip() if path.is_file() else ""
    combined = f"{prior}\n\n" if prior else ""
    path.write_text(combined + "\n".join(entry).rstrip() + "\n", encoding="utf-8")
    return path
