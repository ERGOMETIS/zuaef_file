"""Emit stillevo-aligned research.json from case Markdown deliverables.

Extracts only what report.md / evidence.md / unknowns.md / assets already state.
Never invents products, prices, or sources. Missing values use 待核验 or are omitted.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import mistune

from .report_data import PREPARED_BY, UNKNOWN

EMITTED_NAME = "research.emitted.json"
PRIMARY_NAME = "research.json"


def _strip_md(text: str) -> str:
    s = text or ""
    s = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"__(.+?)__", r"\1", s)
    s = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"\1", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _inline_text(nodes: list[dict] | None) -> str:
    parts: list[str] = []
    for node in nodes or []:
        typ = node.get("type")
        if typ == "text":
            parts.append(node.get("raw", ""))
        elif typ in ("softbreak", "linebreak"):
            parts.append(" ")
        elif typ == "codespan":
            parts.append(node.get("raw", ""))
        else:
            parts.append(_inline_text(node.get("children")))
    return _strip_md("".join(parts))


def _table_cells(node: dict) -> list[str]:
    """Flatten mistune3 table_head (cells) or table_row (cells) into text cells."""
    cells: list[str] = []
    for child in node.get("children") or []:
        if child.get("type") == "table_row":
            cells = [_inline_text(c.get("children")) for c in child.get("children") or []]
            break
        if child.get("type") == "table_cell":
            cells.append(_inline_text(child.get("children")))
    return cells


def _ast_tables(md: str) -> list[tuple[list[str], list[list[str]]]]:
    """Return (header, rows) for every Markdown table."""
    parser = mistune.create_markdown(renderer="ast", plugins=["table"])
    out: list[tuple[list[str], list[list[str]]]] = []
    for block in parser(md):
        if block.get("type") != "table":
            continue
        header: list[str] = []
        rows: list[list[str]] = []
        for part in block.get("children") or []:
            if part.get("type") == "table_head":
                header = _table_cells(part)
            elif part.get("type") == "table_body":
                for row in part.get("children") or []:
                    if row.get("type") == "table_row":
                        rows.append([_inline_text(c.get("children")) for c in row.get("children") or []])
                    elif row.get("type") == "table_cell":
                        # Defensive: some renderers flatten oddly
                        pass
        if header:
            out.append((header, rows))
    return out


def _markdown_images(md: str) -> list[tuple[str, str]]:
    """Return (alt, relative path) for local assets/ images."""
    found: list[tuple[str, str]] = []
    for m in re.finditer(r"!\[([^\]]*)\]\((assets/[^)\s]+)\)", md):
        found.append((_strip_md(m.group(1)), m.group(2).replace("\\", "/")))
    return found


def _parse_input_meta(case_dir: Path) -> dict[str, str]:
    brand, market, goal, as_of = "Unnamed brand", "", "", UNKNOWN
    input_md = case_dir / "input.md"
    if input_md.is_file():
        for line in input_md.read_text(encoding="utf-8").splitlines():
            low = line.lower()
            if "lead:" in low:
                brand = line.split(":", 1)[-1].strip() or brand
            elif "target market:" in low or (low.strip().startswith("- market:")):
                market = line.split(":", 1)[-1].strip()
            elif "decision question:" in low or "goal:" in low:
                goal = line.split(":", 1)[-1].strip()
            elif "research date:" in low:
                as_of = line.split(":", 1)[-1].strip() or as_of
    # Lead may be a URL — refine brand from host if needed
    if brand.startswith("http"):
        host = urlparse(brand).netloc.lower()
        host = host.removeprefix("www.")
        brand = host.split(".")[0].title() if host else brand
    return {"brand": brand, "market": market, "goal": goal, "as_of": as_of}


def _header_meta(report: str) -> dict[str, str]:
    title = "Product Intelligence"
    market = ""
    as_of = ""
    scope = ""
    for line in report.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break

    def _after_label(line: str, label: str) -> str | None:
        m = re.search(rf"\*?\*?{re.escape(label)}\*?\*?\s*:\s*(.+)$", line, re.IGNORECASE)
        if not m:
            return None
        return _strip_md(m.group(1).strip().strip("*").strip())

    for line in report.splitlines()[:50]:
        for label, bucket in (("Market", "market"), ("Research date", "as_of"), ("Scope", "scope")):
            val = _after_label(line, label)
            if val:
                if bucket == "market":
                    # Stop at middle-dot / extra bold fields on combined lines
                    val = re.split(r"\s*[·|]\s*", val)[0].strip()
                    val = re.sub(r"\s*Research date:.*$", "", val, flags=re.IGNORECASE).strip()
                    market = val or market
                elif bucket == "as_of":
                    dm = re.search(r"20\d{2}-\d{2}-\d{2}", val)
                    as_of = dm.group(0) if dm else val
                else:
                    scope = val
    return {"title": title, "market": market, "as_of": as_of, "scope": scope}

def _looks_like_lineup(header: list[str]) -> bool:
    joined = " | ".join(h.lower() for h in header)
    # Competitor / positioning tables are not the brand lineup.
    if re.search(r"positioning|brand\s*/\s*model|gearing|compet", joined, re.IGNORECASE):
        return False
    if any(re.search(r"^field$", h, re.IGNORECASE) for h in header):
        return False
    has_model = any(re.search(r"\bmodel\b|\bproduct\b|\bsku\b", h, re.IGNORECASE) for h in header)
    has_price = any(re.search(r"price|list|us list|headline", h, re.IGNORECASE) for h in header)
    return bool(has_model and has_price) or (
        has_model and "status" in joined and "currency" in joined
    )


def _col(header: list[str], *names: str) -> int | None:
    lowered = [h.lower().strip() for h in header]
    for name in names:
        for i, h in enumerate(lowered):
            if name in h:
                return i
    return None


def _products_from_lineup(header: list[str], rows: list[list[str]]) -> list[dict[str, Any]]:
    mi = _col(header, "model", "product")
    if mi is None:
        return []
    pi = _col(header, "headline price", "us list", "list price", "price")
    fi = _col(header, "frame")
    si = _col(header, "status")
    ci = _col(header, "currency")
    di = _col(header, "source date", "date")
    # optional spec columns
    spec_cols = {
        header[i]: i
        for i in range(len(header))
        if i not in {mi, pi, fi, si, ci, di}
        and header[i].strip()
    }
    products: list[dict[str, Any]] = []
    for row in rows:
        if len(row) < len(header):
            row = row + [""] * (len(header) - len(row))
        name = row[mi].strip()
        if not name or name.lower() in {"model", "product"}:
            continue
        price_display = row[pi].strip() if pi is not None else ""
        currency = row[ci].strip() if ci is not None else ""
        if not currency and price_display:
            if price_display.startswith("€") or "EUR" in price_display.upper():
                currency = "EUR"
            elif price_display.startswith("$") or "USD" in price_display.upper():
                currency = "USD"
            elif price_display.startswith("£") or "GBP" in price_display.upper():
                currency = "GBP"
        if not price_display:
            price_display = UNKNOWN
        status = row[si].strip() if si is not None else ""
        frame = row[fi].strip() if fi is not None else ""
        price_date = row[di].strip() if di is not None else ""
        specs = []
        specs_map: dict[str, str] = {}
        for label, idx in spec_cols.items():
            val = row[idx].strip() if idx < len(row) else ""
            if not val:
                continue
            key = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
            specs_map[key] = val
            specs.append({"label": label, "value": val, "source_ids": []})
        products.append(
            {
                "name": name,
                "category": frame,
                "frame": frame or None,
                "positioning": status,
                "status": status or None,
                "featured": False,
                "price": {
                    "display": price_display,
                    "source_ids": [],
                    "note": price_date,
                    "currency": currency or None,
                },
                "price_date": price_date or None,
                "image": None,
                "image_credit": "",
                "specs": specs,
                "specs_map": specs_map,
                "notes": [],
                "source_ids": [],
            }
        )
    return products


def _products_from_field_tables(
    report: str,
    tables: list[tuple[list[str], list[list[str]]]],
) -> list[dict[str, Any]]:
    """Parse Field/Value product cards; attach nearest preceding heading as name."""
    # Map table index → preceding heading by scanning AST order
    parser = mistune.create_markdown(renderer="ast", plugins=["table"])
    heading_stack: list[str] = []
    results: list[dict[str, Any]] = []
    table_i = 0
    for block in parser(report):
        typ = block.get("type")
        if typ == "heading":
            heading_stack.append(_inline_text(block.get("children")))
        elif typ == "table":
            if table_i >= len(tables):
                continue
            header, rows = tables[table_i]
            table_i += 1
            if not header:
                continue
            h0 = header[0].lower()
            # Field | Value [| Basis] OR Field | ProductName
            if not re.search(r"^field$", h0, re.IGNORECASE):
                continue
            if _looks_like_lineup(header):
                continue
            value_col = 1 if len(header) > 1 else None
            if value_col is None:
                continue
            heading = next((h for h in reversed(heading_stack) if h), "")
            # Prefer explicit product name from heading
            name = heading
            for prefix in (
                "Flagship product card —",
                "Second flagship —",
                "Flagship product card -",
                "Second flagship -",
                "Flagship —",
                "Product card —",
            ):
                if heading.lower().startswith(prefix.lower()) or prefix.lower() in heading.lower():
                    # Split on em-dash / en-dash only (ASCII hyphen breaks "flagship")
                    parts = re.split(r"\s*[—–]\s*", heading, maxsplit=1)
                    name = parts[-1].strip() if len(parts) > 1 else heading
                    break
            # Strip SKU parenthetical noise for matching later
            name_clean = re.sub(r"\([^)]*\)", "", name).strip()
            # If header col1 is a product name (Aventon style), use it
            if len(header) >= 2 and not re.search(r"^value$", header[1], re.IGNORECASE):
                name_clean = header[1].split("(")[0].strip() or name_clean

            specs: list[dict[str, Any]] = []
            specs_map: dict[str, str] = {}
            price_display = UNKNOWN
            currency = None
            price_date = ""
            sku = None
            for row in rows:
                if len(row) < 2:
                    continue
                label = row[0].strip()
                value = row[1].strip()
                if not label or not value:
                    continue
                low = label.lower()
                if "price" in low or "market price" in low:
                    price_display = value
                    # try extract currency token
                    if "EUR" in value.upper() or "€" in value:
                        currency = "EUR"
                    elif "USD" in value.upper() or "$" in value:
                        currency = "USD"
                    elif "GBP" in value.upper() or "£" in value:
                        currency = "GBP"
                    dm = re.search(r"20\d{2}-\d{2}-\d{2}", value)
                    if dm:
                        price_date = dm.group(0)
                key = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
                specs_map[key] = value
                specs.append({"label": label, "value": value, "source_ids": []})
            # SKU from heading
            sm = re.search(r"SKU\s+([A-Za-z0-9-]+)", heading, re.IGNORECASE)
            if sm:
                sku = sm.group(1)
            if not name_clean:
                continue
            results.append(
                {
                    "name": name_clean,
                    "category": "",
                    "positioning": "",
                    "featured": True,
                    "sku": sku,
                    "price": {
                        "display": price_display,
                        "source_ids": [],
                        "note": price_date,
                        "currency": currency,
                    },
                    "price_date": price_date or None,
                    "image": None,
                    "image_credit": "",
                    "specs": specs,
                    "specs_map": specs_map,
                    "notes": [],
                    "source_ids": [],
                }
            )
    return results


def _merge_products(
    lineup: list[dict[str, Any]],
    cards: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Prefer lineup rows for catalogue; enrich with flagship card specs/prices when names match."""

    def key(n: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", n.lower())

    by_key: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for p in lineup:
        k = key(p["name"])
        by_key[k] = dict(p)
        order.append(k)
    for c in cards:
        k = key(c["name"])
        # fuzzy: card name may be "VanMoof S6 Open Drift Black" while lineup is "S6 Open".
        # Prefer the longest lineup key contained in the card key (so S6 Open beats S6).
        match = k if k in by_key else None
        if match is None:
            candidates = [lk for lk in order if lk and (lk in k or k in lk)]
            if candidates:
                match = max(candidates, key=len)
        if match is None:
            by_key[k] = dict(c)
            order.append(k)
            continue
        base = by_key[match]
        # Enrich: card specs win when present; keep lineup price if already concrete
        if c.get("specs"):
            base["specs"] = c["specs"]
            base["specs_map"] = c.get("specs_map") or base.get("specs_map") or {}
        card_price = (c.get("price") or {}).get("display")
        base_price = (base.get("price") or {}).get("display")
        if card_price and card_price != UNKNOWN:
            if not base_price or base_price == UNKNOWN:
                base["price"] = c["price"]
            else:
                # keep lineup display; copy currency/note if missing
                bp = base.setdefault("price", {})
                cp = c.get("price") or {}
                bp.setdefault("currency", cp.get("currency"))
                if not bp.get("note") and cp.get("note"):
                    bp["note"] = cp["note"]
        if c.get("sku") and not base.get("sku"):
            base["sku"] = c["sku"]
        base["featured"] = True
        # Prefer shorter lineup name
    return [by_key[k] for k in order]


def _attach_images(
    products: list[dict[str, Any]],
    images: list[tuple[str, str]],
    case_dir: Path,
) -> None:
    used: set[str] = set()

    def key(n: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", n.lower())

    for p in products:
        pk = key(p["name"])
        tokens = [t for t in re.findall(r"[a-z0-9]+", p["name"].lower()) if len(t) > 1]
        best = None
        for alt, rel in images:
            if rel in used:
                continue
            blob = key(alt) + key(Path(rel).stem)
            score = 0
            if pk and pk in blob:
                score += 10
            for t in tokens:
                if t in blob:
                    score += 2
            # common patterns: s6-open vs s6
            if score > 0 and (best is None or score > best[0]):
                best = (score, rel, alt)
        if best and best[0] >= 2:
            rel = best[1]
            path = case_dir / rel
            if path.is_file():
                p["image"] = rel
                p["image_credit"] = best[2] or ""
                used.add(rel)
    # cover = first featured with image else first with image


def _sources_from_evidence(evidence: str, as_of: str) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    # Pattern A: ## E1. Title  then URL bullet
    for m in re.finditer(
        r"^##\s+(E\d+)\.\s+(.+?)\n(.*?)(?=^##\s+E\d+\.|\Z)",
        evidence,
        re.MULTILINE | re.DOTALL,
    ):
        sid, title, body = m.group(1), _strip_md(m.group(2)), m.group(3)
        url = None
        um = re.search(r"\*\*URL:\*\*\s*(https?://\S+)", body)
        if not um:
            um = re.search(r"(https?://[^\s\)\]\>\"']+)", body)
        if um:
            url = um.group(1).rstrip(".,;")
        accessed = as_of
        am = re.search(r"\*\*Visited:\*\*\s*([0-9-]+)", body)
        if am:
            accessed = am.group(1)
        if url:
            seen_urls.add(url)
        sources.append(
            {
                "id": sid,
                "title": title,
                "url": url,
                "accessed": accessed or UNKNOWN,
                "note": "",
            }
        )

    # Pattern B: ### 2.1 Name — https://... (Aventon-style) when no E-ids found
    if not sources:
        n = 0
        for m in re.finditer(
            r"^###\s+[\d.]+\s+(.+?)\s+[—-]\s*(https?://\S+)",
            evidence,
            re.MULTILINE,
        ):
            n += 1
            title, url = _strip_md(m.group(1)), m.group(2).rstrip(".,;")
            if url in seen_urls:
                continue
            seen_urls.add(url)
            sources.append(
                {
                    "id": f"E{n}",
                    "title": title,
                    "url": url,
                    "accessed": as_of or UNKNOWN,
                    "note": "Extracted from evidence.md heading URL",
                }
            )

    # Fallback: unique https URLs
    if not sources:
        urls = re.findall(r"https?://[^\s\)\]\>\"']+", evidence)
        for i, url in enumerate(dict.fromkeys(urls), 1):
            host = urlparse(url).netloc or "source"
            sources.append(
                {
                    "id": f"E{i}",
                    "title": host,
                    "url": url,
                    "accessed": as_of or UNKNOWN,
                    "note": "Extracted from evidence.md URL mention",
                }
            )
    return sources


def _open_questions(unknowns: str) -> list[str]:
    questions: list[str] = []
    if not unknowns.strip():
        return questions
    # Numbered items: 1. **Title.** rest
    for m in re.finditer(r"^\s*\d+\.\s+\*\*(.+?)\*\*\s*(.*)$", unknowns, re.MULTILINE):
        title = _strip_md(m.group(1))
        rest = _strip_md(m.group(2))
        q = f"{title} {rest}".strip() if rest else title
        if q:
            questions.append(q)
    if questions:
        return questions
    # Bullet lines under ## sections (skip headers / table sep)
    for line in unknowns.splitlines():
        s = line.strip()
        if not s or s.startswith(("#", "|")) or set(s) <= {"-", "|", ":", " "}:
            continue
        if s.startswith(("-", "*")):
            s = s.lstrip("-*").strip()
            if s:
                questions.append(_strip_md(s))
    # Table first column "Unknown"
    for header, rows in _ast_tables(unknowns):
        if not header:
            continue
        if not re.search(r"unknown", header[0], re.IGNORECASE):
            continue
        for row in rows:
            if row and row[0].strip():
                questions.append(row[0].strip())
    # de-dupe preserve order
    return list(dict.fromkeys(questions))


def _decision_from_report(report: str) -> dict[str, Any] | None:
    # Find Decision section
    # Prefer a heading that is the Decision section itself (e.g. "## 8. Decision"),
    # not an earlier heading that merely mentions the word (e.g. "decision question").
    m = re.search(
        r"^##\s+(?:\d+\.\s*)?Decision\s*$\n(.*?)(?=^##\s+|\Z)",
        report,
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    if not m:
        m = re.search(
            r"^##\s+(?:\d+\.\s*)?Decision\b[^\n]*\n(.*?)(?=^##\s+|\Z)",
            report,
            re.MULTILINE | re.DOTALL | re.IGNORECASE,
        )
    if not m:
        return None
    body = m.group(1)
    label_m = re.search(
        r"(?:^|\n)\s*(?:#{1,6}\s*)?\*?\*?(FOLLOW|HOLD|PASS|REVIEW|BUY|WATCH)\*?\*?\b",
        body,
        re.IGNORECASE,
    )
    if not label_m:
        return None
    label = label_m.group(1).upper()
    reasons: list[str] = []
    for rm in re.finditer(r"^\s*\d+\.\s+\*\*(.+?)\*\*\s*(.*)$", body, re.MULTILINE):
        reasons.append(_strip_md(f"{rm.group(1)} {rm.group(2)}"))
    if not reasons:
        for rm in re.finditer(r"^\s*\d+\.\s+(.+)$", body, re.MULTILINE):
            text = _strip_md(rm.group(1))
            if text and not text.lower().startswith("reasons"):
                reasons.append(text)
    unc = ""
    um = re.search(r"\*\*Largest uncertainty:\*\*\s*(.+)", body, re.IGNORECASE)
    if um:
        unc = _strip_md(um.group(1))
    action = ""
    am = re.search(r"\*\*(?:One )?next commercial action:\*\*\s*(.+)", body, re.IGNORECASE)
    if am:
        action = _strip_md(am.group(1))
    return {
        "label": label,
        "reasons": reasons[:5],
        "largest_uncertainty": unc or UNKNOWN,
        "next_commercial_action": action or UNKNOWN,
    }


def _findings_from_report(report: str) -> list[str]:
    findings: list[str] = []
    for m in re.finditer(r"\*\*Fact:\*\*\s*(.+)", report):
        findings.append(_strip_md(m.group(1)))
        if len(findings) >= 5:
            break
    return findings


def build_contract_from_markdown(case_dir: Path) -> dict[str, Any]:
    """Build a stillevo content-contract dict from case Markdown. No invented facts."""
    case_dir = Path(case_dir).resolve()
    report_path = case_dir / "report.md"
    if not report_path.is_file():
        raise FileNotFoundError(f"Cannot emit research.json without report.md: {report_path}")

    report = report_path.read_text(encoding="utf-8")
    evidence = (case_dir / "evidence.md").read_text(encoding="utf-8") if (case_dir / "evidence.md").is_file() else ""
    unknowns = (case_dir / "unknowns.md").read_text(encoding="utf-8") if (case_dir / "unknowns.md").is_file() else ""

    input_meta = _parse_input_meta(case_dir)
    header = _header_meta(report)
    as_of = header.get("as_of") or input_meta.get("as_of") or UNKNOWN
    market = header.get("market") or input_meta.get("market") or ""
    title = header["title"]
    brand = input_meta.get("brand") or "Unnamed brand"
    # Prefer the title's leading brand token for stable casing (VanMoof vs Vanmoof).
    tm = re.match(r"([A-Za-z0-9][A-Za-z0-9+._-]*)", title)
    if tm:
        title_brand = tm.group(1)
        if brand in {"Unnamed brand", ""} or brand.lower() in {"http", "https"} or brand.lower() == title_brand.lower():
            brand = title_brand

    tables = _ast_tables(report)
    lineup_products: list[dict[str, Any]] = []
    for header_row, rows in tables:
        if _looks_like_lineup(header_row):
            lineup_products.extend(_products_from_lineup(header_row, rows))
    cards = _products_from_field_tables(report, tables)
    products = _merge_products(lineup_products, cards)
    images = _markdown_images(report)
    _attach_images(products, images, case_dir)

    # Featured: flagship cards / in-stock / first three with images
    for p in products:
        status = (p.get("status") or p.get("positioning") or "").lower()
        if p.get("featured"):
            continue
        if p.get("specs") and len(p.get("specs") or []) >= 5 or "in stock" in status or "available" in status:
            p["featured"] = True
    if not any(p.get("featured") for p in products):
        for p in products[:3]:
            p["featured"] = True

    sources = _sources_from_evidence(evidence, as_of) if evidence else []
    questions = _open_questions(unknowns) if unknowns else []
    decision = _decision_from_report(report)
    findings = _findings_from_report(report)

    cover = next((p.get("image") for p in products if p.get("image")), None)
    scope = header.get("scope") or input_meta.get("goal") or ""

    lead = ""
    if products:
        names = ", ".join(p["name"] for p in products[:4])
        lead = f"Observed lineup sketch from report.md: {names}."
    else:
        lead = (
            "No product rows could be extracted from Markdown tables; "
            "open questions and sources only. Supply a curated research.json for a full brief."
        )

    contract: dict[str, Any] = {
        "meta": {
            "title": title,
            "brand": brand,
            "subtitle": scope or "Product line · pricing · specifications · evidence",
            "region": market,
            "as_of": as_of,
            "prepared_by": PREPARED_BY,
            "status": "DRAFT",
            "disclaimer": (
                "Publicly observable information extracted from case Markdown only; "
                "list prices are not transactions; missing fields are 待核验 — nothing was invented."
            ),
            "demo": False,
        },
        "summary": {
            "lead": lead,
            "findings": findings,
            "scope": scope or "Extracted from report.md / evidence.md / unknowns.md",
        },
        "products": products,
        "sources": sources,
        "open_questions": questions,
    }
    if decision:
        contract["decision"] = decision
    if cover:
        contract["cover_image"] = cover
    contract["_emitter"] = {
        "version": "0.1",
        "from": ["report.md", "evidence.md", "unknowns.md", "assets"],
        "note": (
            "Structured extraction only. Prefer a hand-curated research.json when richer "
            "(bilingual fields, Typst extensions). Precedence: research.json > "
            f"{EMITTED_NAME} > Markdown heuristics at render time."
        ),
    }
    return contract


def emit_research_json(
    case_dir: Path,
    *,
    force: bool = False,
    dest: Path | None = None,
) -> dict[str, Any]:
    """Write stillevo contract JSON for a case.

    Precedence policy:
    - If ``research.json`` already exists and ``force`` is False, write
      ``research.emitted.json`` instead (do not clobber curated lab/contract JSON).
    - If ``research.json`` is absent, write it so ``product-research render`` can use Typst.
    - ``force=True`` overwrites ``research.json`` (or ``dest`` if given).

    Returns a small result dict: path, skipped_primary, product_count, source_count.
    """
    case_dir = Path(case_dir).resolve()
    contract = build_contract_from_markdown(case_dir)
    # Strip internal emitter bookkeeping from on-disk optional? Keep _emitter for audit.
    primary = case_dir / PRIMARY_NAME
    emitted = case_dir / EMITTED_NAME

    target: Path
    skipped_primary = False
    if dest is not None:
        target = Path(dest)
    elif force:
        target = primary
    elif primary.is_file():
        # Preserve curated / richer explicit JSON
        target = emitted
        skipped_primary = True
    else:
        target = primary

    # Drop private key from published contract copy used by loader? Keep it — harmless.
    payload = {k: v for k, v in contract.items()}
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "path": str(target),
        "skipped_primary": skipped_primary,
        "primary_exists": primary.is_file(),
        "product_count": len(contract.get("products") or []),
        "source_count": len(contract.get("sources") or []),
        "open_question_count": len(contract.get("open_questions") or []),
        "schema": "contract",
    }
