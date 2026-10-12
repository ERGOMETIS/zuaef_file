"""Self-contained HTML renderer adapted from the stillevo report path.

HTML is useful for review and for optional WeasyPrint output.  It shares the
contract, source chips, missing-image placeholders, and build-note discipline
with the Typst renderer, but does not use the skill package as a second
project and does not ship its demo SVG artwork.
"""
from __future__ import annotations

import base64
import mimetypes
from html import escape
from pathlib import Path
from urllib.parse import urlparse

from .report_data import UNKNOWN, ReportBundle, append_build_notes, resolve_image_file

TEMPLATE_CSS = Path(__file__).resolve().parent / "templates" / "html" / "report.css"

_UI = {
    "en": {
        "summary": "Executive summary",
        "observations": "Key observations",
        "scope": "Scope & limitations",
        "product_profile": "Product profile",
        "price": "Observed price",
        "specifications": "Selected specifications",
        "notes": "Research notes",
        "evidence": "Evidence",
        "comparison": "Lineup at a glance",
        "source_index": "Source index",
        "questions": "Open questions / Pending verification",
        "no_photo": "No verified product photograph",
        "no_findings": "No findings supplied.",
        "no_notes": "No notes entered.",
        "no_sources": "No sources recorded.",
        "no_questions": "No open questions recorded (not a guarantee of completeness).",
        "no_source": "NO SOURCE",
        "product_entries": "PRODUCT ENTRIES",
        "listed_sources": "LISTED SOURCES",
        "open_questions": "OPEN QUESTIONS",
        "category": "CATEGORY",
        "model": "PRODUCT / MODEL",
        "observed_price": "OBSERVED PRICE",
        "traceability": "Traceability",
        "research_brief": "Product / competitor research brief",
        "source_urls": "Source URLs are kept here so claims remain readable.",
        "internal_rights": "Internal-analysis images; reuse rights require clearance from the rights-holder.",
    },
    "zh": {
        "summary": "执行摘要",
        "observations": "关键观察",
        "scope": "范围与限制",
        "product_profile": "产品档案",
        "price": "观察到的价格",
        "specifications": "已记录规格",
        "notes": "研究备注",
        "evidence": "证据",
        "comparison": "产品线概览",
        "source_index": "来源索引",
        "questions": "开放问题 / 待核验事项",
        "no_photo": "尚未提供已核验的产品照片",
        "no_findings": "未提供发现。",
        "no_notes": "未填写备注。",
        "no_sources": "未记录来源。",
        "no_questions": "未记录开放问题（不代表已完整核验）。",
        "no_source": "无来源",
        "product_entries": "产品条目",
        "listed_sources": "列出来源",
        "open_questions": "开放问题",
        "category": "类别",
        "model": "产品 / 型号",
        "observed_price": "观察价格",
        "traceability": "可追溯性",
        "research_brief": "产品 / 竞品研究简报",
        "source_urls": "来源 URL 集中列于此处，以保持主文可读。",
        "internal_rights": "图片仅用于内部分析；再次使用前必须向权利持有人确认权利。",
    },
}


def _e(value: object, *, quote: bool = False) -> str:
    return escape(str(value if value is not None else ""), quote=quote)


def _text(value: object, fallback: str = "") -> str:
    text = str(value).strip() if value is not None else ""
    return text or fallback


def _localized(obj: dict, key: str, lang: str, fallback: str = "") -> str:
    if lang == "zh":
        zh_value = obj.get(f"{key}_zh")
        if zh_value is not None and str(zh_value).strip():
            return str(zh_value)
    value = obj.get(key)
    return _text(value, fallback)


def _localized_item(values: object, values_zh: object, index: int, lang: str, fallback: str = "") -> str:
    if lang == "zh" and isinstance(values_zh, list) and index < len(values_zh):
        return _text(values_zh[index], fallback)
    if isinstance(values, list) and index < len(values):
        return _text(values[index], fallback)
    return fallback


def _data_image(path_value: object, base_dir: Path, notes: list[str]) -> str | None:
    if not path_value:
        return None
    relative = str(path_value)
    image_path = resolve_image_file(base_dir, relative)
    if image_path is None:
        message = f"Image not found: {relative}"
        if message not in notes:
            notes.append(message)
        return None
    mime = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    if mime not in {"image/png", "image/jpeg", "image/webp", "image/svg+xml", "image/gif"}:
        message = f"Unsupported image MIME {mime}: {relative}"
        if message not in notes:
            notes.append(message)
        return None
    payload = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{payload}"


def _source_chips(ids: object, known: set[str], notes: list[str], context: str, lang: str) -> str:
    source_ids = [str(item) for item in (ids if isinstance(ids, list) else [ids] if ids else [])]
    if not source_ids:
        message = f"Missing source ID: {context}"
        if message not in notes:
            notes.append(message)
        return f'<span class="chip">{_e(_UI[lang]["no_source"])}</span>'
    chips: list[str] = []
    for source_id in source_ids:
        if source_id not in known:
            message = f"Unknown source ID {source_id}: {context}"
            if message not in notes:
                notes.append(message)
        chips.append(f'<span class="chip">{_e(source_id)}</span>')
    return "".join(chips)


def _safe_link(url: object) -> str:
    value = str(url or "")
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return f'<a href="{_e(value, quote=True)}">{_e(value)}</a>'
    return _e(value or "No URL recorded")


def _section_head(kicker: str, heading: str, aside: str = "") -> str:
    return (
        '<div class="section-head"><div><div class="section-kicker">'
        f"{_e(kicker)}</div><h2>{_e(heading)}</h2></div>"
        f'<div class="section-aside">{_e(aside)}</div></div>'
    )


def html_report(
    data: dict,
    base_dir: Path,
    notes: list[str],
    *,
    lang: str = "en",
) -> str:
    """Render a contract dictionary as self-contained HTML."""

    if lang not in {"en", "zh"}:
        raise ValueError("lang must be 'en' or 'zh'")
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    products = data.get("products") if isinstance(data.get("products"), list) else []
    sources = data.get("sources") if isinstance(data.get("sources"), list) else []
    questions = data.get("open_questions") if isinstance(data.get("open_questions"), list) else []
    known = {str(source.get("id")) for source in sources if isinstance(source, dict) and source.get("id")}
    ui = _UI[lang]
    brand = _localized(meta, "brand", lang, "Unnamed brand")
    title = _localized(meta, "title", lang, "Product Intelligence")
    as_of = _localized(meta, "as_of", lang, "Date not recorded")
    status = _localized(meta, "status", lang, "DRAFT")
    prepared_by = _localized(meta, "prepared_by", lang, "STILLEVO | 坐驰未来")
    region = _localized(meta, "region", lang, "Market unspecified")
    disclaimer = _localized(meta, "disclaimer", lang, "Source-linked research brief")

    cover_image: str | None = None
    for product in products:
        if isinstance(product, dict) and product.get("image"):
            cover_image = _data_image(product.get("image"), base_dir, notes)
            if cover_image:
                break
    if cover_image:
        cover_figure = f'<img src="{cover_image}" alt="{_e(brand)} product image">'
    else:
        cover_figure = f'<span>{_e(ui["no_photo"])}</span>'
    demo_banner = (
        '<div class="watermark">Fictional sample data · Not client ready</div>'
        if meta.get("demo")
        else ""
    )
    cover = f"""<section class="cover">
      <div class="topline"><div class="wordmark">STILLEVO<small>坐驰未来 / RESEARCH SERVICES</small></div><div class="serial">MARKET INTELLIGENCE<br>{_e(as_of)}<br><span class="status">{_e(status)}</span></div></div>
      <div class="eyebrow">BRAND PRODUCT RESEARCH / {_e(region)}</div>
      <h1>{_e(title)}</h1><div class="sub">{_e(_localized(meta, 'subtitle', lang, ui['research_brief']))}</div>
      <div class="photo">{cover_figure}<span class="tile-label">{_e(brand)} / PRODUCT LANDSCAPE</span></div>
      <div class="bottomline"><span>{_e(prepared_by)}</span><span>{_e(disclaimer)}</span></div>
    </section>"""

    findings = summary.get("findings") if isinstance(summary.get("findings"), list) else []
    findings_zh = summary.get("findings_zh")
    finding_html = "".join(
        f'<div class="finding"><strong>{index:02d}</strong>{_e(_localized_item(findings, findings_zh, index - 1, lang))}</div>'
        for index in range(1, len(findings) + 1)
    ) or f'<p>{_e(ui["no_findings"])}</p>'
    summary_page = f"""<section class="page-section summary-page">
      {_section_head('01 / Executive Brief', ui['summary'], f'{brand} / {as_of}')}
      <p class="lead">{_e(_localized(summary, 'lead', lang, 'No executive summary provided.'))}</p>
      <div class="metrics"><div class="metric"><b>{len(products):02d}</b><span>{_e(ui['product_entries'])}</span></div><div class="metric"><b>{len(sources):02d}</b><span>{_e(ui['listed_sources'])}</span></div><div class="metric"><b>{len(questions):02d}</b><span>{_e(ui['open_questions'])}</span></div></div>
      <div class="content-grid"><div><div class="mini-heading">{_e(ui['observations'])}</div>{finding_html}</div><div><div class="scope"><b>{_e(ui['scope'])}</b>{_e(_localized(summary, 'scope', lang, 'Scope not described.'))}</div>{demo_banner}</div></div>
    </section>"""

    profiles: list[str] = []
    for index, raw_product in enumerate(products, 1):
        product = raw_product if isinstance(raw_product, dict) else {}
        name = _localized(product, "name", lang, "Unnamed model")
        category = _localized(product, "category", lang, "")
        positioning = _localized(product, "positioning", lang, "Positioning not recorded")
        price = product.get("price") if isinstance(product.get("price"), dict) else {}
        image_data = _data_image(product.get("image"), base_dir, notes)
        if image_data:
            photo = f'<img src="{image_data}" alt="{_e(name, quote=True)}">'
        else:
            photo = f'<div class="nothing">{_e(ui["no_photo"])}</div>'
        raw_specs = product.get("specs") if isinstance(product.get("specs"), list) else []
        spec_rows: list[str] = []
        for raw_spec in raw_specs:
            spec = raw_spec if isinstance(raw_spec, dict) else {}
            label = _localized(spec, "label", lang, "—")
            value = _localized(spec, "value", lang, UNKNOWN)
            chips = _source_chips(spec.get("source_ids"), known, notes, f"{name} / {label}", lang)
            spec_rows.append(f"<tr><td>{_e(label)}</td><td>{_e(value)}</td><td>{chips}</td></tr>")
        spec_table = "".join(spec_rows) or (
            f'<tr><td>{_e(ui["specifications"])}</td><td>{_e(UNKNOWN)}</td><td>—</td></tr>'
        )
        raw_notes = product.get("notes") if isinstance(product.get("notes"), list) else []
        raw_notes_zh = product.get("notes_zh")
        note_items = []
        for note_index, item in enumerate(raw_notes):
            note_items.append(
                f'<p class="note">• {_e(_localized_item(raw_notes, raw_notes_zh, note_index, lang))}</p>'
            )
        notes_html = "".join(note_items) or f'<p>{_e(ui["no_notes"])}</p>'
        price_display = _localized(price, "display", lang, UNKNOWN)
        price_note = _localized(price, "note", lang, "Region, date and currency not specified")
        product_source_chips = _source_chips(
            product.get("source_ids"), known, notes, f"{name} / product", lang
        )
        price_chips = _source_chips(price.get("source_ids"), known, notes, f"{name} / price", lang)
        image_credit = _localized(product, "image_credit", lang, "Image source not recorded")
        profiles.append(
            f"""<section class="page-section product-page">
        {_section_head(f'02 / Product Profile {index:02d}', name, f'{brand} / {category}')}
        <div class="product-intro">{_e(positioning)}</div>
        <div class="product-hero"><div class="product-photo">{photo}<small>{_e(image_credit)}</small></div><div class="product-price"><div class="price-label">{_e(ui['price'])}</div><strong>{_e(price_display)}</strong><p>{_e(price_note)}</p><div class="source-chips">{price_chips}</div></div></div>
        <div class="mini-heading">{_e(ui['specifications'])}</div><table class="specs"><tbody>{spec_table}</tbody></table>
        <div class="product-footer"><div><div class="mini-heading">{_e(ui['notes'])}</div><div class="notes">{notes_html}</div></div><div><div class="mini-heading">{_e(ui['evidence'])}</div><div class="caption">Source IDs for product: {product_source_chips}<br>{_e(ui['source_urls'])}</div></div></div>
        </section>"""
        )

    comparison_rows = []
    for raw_product in products:
        product = raw_product if isinstance(raw_product, dict) else {}
        name = _localized(product, "name", lang, "—")
        category = _localized(product, "category", lang, "—")
        price = product.get("price") if isinstance(product.get("price"), dict) else {}
        price_text = _localized(price, "display", lang, UNKNOWN)
        chips = _source_chips(price.get("source_ids"), known, notes, f"{name} / comparison price", lang)
        comparison_rows.append(
            f'<tr><td class="model">{_e(name)}</td><td>{_e(category)}</td><td>{_e(price_text)}<br><span class="source-chips">{chips}</span></td></tr>'
        )
    comparison = f"""<section class="page-section comparison-page">
       {_section_head('03 / Competitive View', ui['comparison'], f'{len(products)} listed products')}
       <p class="lead">{_e('本页只并排呈现已记录的产品与价格，不自动推断各市场价格可比，也不据此计算市场份额。' if lang == 'zh' else 'This page places recorded products and prices side by side; it does not infer cross-market comparability or market share.')}</p>
       <div class="table-wrap"><table class="compare"><thead><tr><th>{_e(ui['model'])}</th><th>{_e(ui['category'])}</th><th>{_e(ui['observed_price'])}</th></tr></thead><tbody>{''.join(comparison_rows)}</tbody></table></div>
       <div class="disclaimer">{_e(disclaimer)} · Prices, currency, regions and observation dates must be read alongside the underlying source pages.</div>
    </section>"""

    source_entries: list[str] = []
    for source in sources:
        source = source if isinstance(source, dict) else {}
        source_id = source.get("id", "—")
        source_title = _localized(source, "title", lang, "Untitled source")
        urls = []
        if source.get("url"):
            urls.append(source.get("url"))
        urls.extend(source.get("urls") if isinstance(source.get("urls"), list) else [])
        url_html = "<br>".join(_safe_link(url) for url in urls) or _e("No URL recorded")
        source_entries.append(
            f'<div class="source-entry"><span class="id">{_e(source_id)}</span><span class="title">{_e(source_title)}</span><div class="url">{url_html}</div><div class="accessed">Accessed: {_e(source.get("accessed", "not recorded"))} · {_e(_localized(source, "note", lang, ""))}</div></div>'
        )
    source_html = "".join(source_entries) or f'<div class="nothing">{_e(ui["no_sources"])}</div>'
    question_items = []
    questions_zh = data.get("open_questions_zh")
    for index, question in enumerate(questions):
        question_items.append(
            f'<li>{_e(_localized_item(questions, questions_zh, index, lang))}</li>'
        )
    questions_html = (
        f'<ol class="questions">{"".join(question_items)}</ol>'
        if question_items
        else f'<p class="nothing">{_e(ui["no_questions"])}</p>'
    )
    evidence = f"""<section class="page-section evidence-page">
       {_section_head('04 / ' + ui['traceability'], '来源与待确认事项' if lang == 'zh' else 'Sources and pending questions', f'{len(sources)} links / {len(questions)} questions')}
       <div class="mini-heading">{_e(ui['source_index'])}</div>{source_html}
       <div class="mini-heading" style="margin-top:20px">{_e(ui['questions'])}</div>{questions_html}
       <p class="disclaimer">Report status: {_e(status)}. A formatted report is not independent verification of its underlying content.</p>
    </section>"""

    css = TEMPLATE_CSS.read_text(encoding="utf-8")
    html_lang = "zh-CN" if lang == "zh" else "en"
    return (
        f'<!doctype html><html lang="{html_lang}"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_e(title)}</title><style>{css}</style></head>"
        f'<body data-brand="{_e(brand, quote=True)}">{cover}{summary_page}{"".join(profiles)}{comparison}{evidence}</body></html>'
    )


def render_html(
    bundle: ReportBundle,
    case_dir: Path,
    *,
    lang: str = "en",
) -> dict[str, object]:
    """Write HTML and, when available, a separate WeasyPrint PDF."""

    if lang not in {"en", "zh"}:
        raise ValueError("lang must be 'en' or 'zh'")
    case_dir = Path(case_dir).expanduser().resolve()
    deliverables = case_dir / "deliverables"
    deliverables.mkdir(parents=True, exist_ok=True)
    notes = list(bundle.notes)
    html = html_report(bundle.contract, bundle.base_dir, notes, lang=lang)
    html_name = "report.html" if lang == "en" else "report-zh.html"
    html_path = deliverables / html_name
    html_path.write_text(html, encoding="utf-8")

    pdf_path: Path | None = None
    pdf_name = "report-html.pdf" if lang == "en" else "report-html-zh.pdf"
    try:
        from weasyprint import HTML

        pdf_path = deliverables / pdf_name
        HTML(string=html, base_url=str(deliverables)).write_pdf(str(pdf_path))
    except (ImportError, OSError, RuntimeError) as exc:
        notes.append(f"WeasyPrint unavailable; HTML only: {type(exc).__name__}")

    notes.append(f"engine=html lang={lang}")
    build_notes = append_build_notes(case_dir, notes, header=f"html render lang={lang}")
    result: dict[str, object] = {
        "html": str(html_path),
        "engine": "html",
        "lang": lang,
        "pdf": str(pdf_path) if pdf_path else None,
        "build_notes": str(build_notes),
        "notes": notes,
    }
    if pdf_path:
        result["pdf"] = str(pdf_path)
    return result


render_report_html = render_html
