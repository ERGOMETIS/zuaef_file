"""Deterministic Markdown -> PDF. Doesn't judge the truth of the report."""
from __future__ import annotations

from datetime import date
from html import escape
from pathlib import Path
from urllib.parse import urlsplit

import pypdfium2
from pypdf import PdfReader
import mistune
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from PIL import Image as PILImage

PAGE_W, PAGE_H = A4
P_WIDTH = PAGE_W - 37 * mm


def _font() -> str:
    """ReportLab's built-in CJK fallback. Projects can replace with their own licensed fonts."""
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    return "STSong-Light"


def _inline(nodes: list[dict] | None) -> str:
    rendered: list[str] = []
    for node in nodes or []:
        typ = node.get("type")
        if typ == "text":
            rendered.append(escape(node.get("raw", "")))
        elif typ == "strong":
            rendered.append(f"<b>{_inline(node.get('children'))}</b>")
        elif typ == "emphasis":
            rendered.append(f"<i>{_inline(node.get('children'))}</i>")
        elif typ == "codespan":
            rendered.append(escape(node.get("raw", "")))
        elif typ == "link":
            url = node.get("attrs", {}).get("url", "")
            if urlsplit(url).scheme in ("https", "http"):
                rendered.append(f'<link href="{escape(url, quote=True)}" color="#28667B">{_inline(node.get("children"))}</link>')
            else:
                rendered.append(_inline(node.get("children")))
        elif typ in ("softbreak", "linebreak"):
            rendered.append("<br/>")
        else:
            rendered.append(_inline(node.get("children")))
    return "".join(rendered)


def _local_image(src: str, case_dir: Path, width: float = P_WIDTH):
    """Embedded images must exist under assets, not arbitrary absolute paths."""
    rel = Path(src)
    if rel.is_absolute() or ".." in rel.parts or not rel.parts or rel.parts[0] != "assets":
        raise ValueError(f"Image must be a local assets/ path: {src}")
    img = (case_dir / rel).resolve()
    if not img.is_relative_to((case_dir / "assets").resolve()) or not img.is_file():
        raise FileNotFoundError(f"Missing local product photo: {src}")
    with PILImage.open(img) as check:
        w, h = check.size
    scale = min(width / w, 88 * mm / h)
    return Image(str(img), width=w * scale, height=h * scale)


def _footer(c, doc) -> None:
    c.saveState()
    c.setStrokeColor(colors.HexColor("#CFDAD9"))
    c.line(18 * mm, 16 * mm, PAGE_W - 18 * mm, 16 * mm)
    c.setFillColor(colors.HexColor("#536368"))
    c.setFont("Helvetica", 8)
    c.drawString(19 * mm, 11 * mm, "OPEN PRODUCT RESEARCH  /  PUBLIC-SOURCE REPORT")
    c.drawRightString(PAGE_W - 18 * mm, 11 * mm, f"{doc.page:02}")
    c.restoreState()


def render_report(case_dir: Path, *, source: str = "report.md", filename: str = "report.pdf") -> dict:
    case_dir = Path(case_dir).resolve()
    md = case_dir / source
    if not md.is_file():
        raise FileNotFoundError(f"No client report exists: {md}")
    content = md.read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError("The client report is empty")
    font = _font()
    styles = {
        "body": ParagraphStyle("body", fontName=font, fontSize=9, leading=15.5,
                                textColor=colors.HexColor("#23333A"), spaceAfter=7),
        "h1": ParagraphStyle("h1", fontName=font, fontSize=20, leading=30,
                              textColor=colors.HexColor("#14313C"), spaceAfter=15),
        "h2": ParagraphStyle("h2", fontName=font, fontSize=13.5, leading=22,
                              textColor=colors.HexColor("#24546A"), spaceBefore=14, spaceAfter=8),
        "h3": ParagraphStyle("h3", fontName=font, fontSize=10.8, leading=17,
                              textColor=colors.HexColor("#24546A"), spaceBefore=9, spaceAfter=6),
        "cell": ParagraphStyle("cell", fontName=font, fontSize=7.7, leading=12,
                                textColor=colors.HexColor("#23333A")),
        "head": ParagraphStyle("head", fontName=font, fontSize=8, leading=12,
                                textColor=colors.white),
        "caption": ParagraphStyle("caption", fontName=font, fontSize=8, leading=13,
                                   textColor=colors.HexColor("#69787D"), alignment=TA_CENTER),
    }
    destination = case_dir / "deliverables"
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / filename
    elements = []
    parser = mistune.create_markdown(renderer="ast", plugins=["table"])
    for block in parser(content):
        typ = block.get("type")
        if typ == "heading":
            level = min(3, block.get("attrs", {}).get("level", 2))
            elements.append(Paragraph(_inline(block.get("children")), styles[f"h{level}"]))
        elif typ == "paragraph":
            kids = block.get("children", [])
            if len(kids) == 1 and kids[0].get("type") == "image":
                src = kids[0].get("attrs", {}).get("url", "")
                pic = _local_image(src, case_dir)
                alt = _inline(kids[0].get("children"))
                elements.append(KeepTogether([pic, Spacer(1, 5), Paragraph(alt, styles["caption"]), Spacer(1, 10)]))
            else:
                # Inline images inside text paragraphs are not silently discarded.
                if any(n.get("type") == "image" for n in kids):
                    raise ValueError("Product photos must be on their own Markdown line")
                elements.append(Paragraph(_inline(kids), styles["body"]))
        elif typ == "table":
            rows = []
            for part in block.get("children", []):
                row_nodes = [part] if part.get("type") == "table_head" else part.get("children", [])
                for row in row_nodes:
                    cells = row.get("children", [])
                    rows.append([_inline(cell.get("children")) for cell in cells])
            if rows:
                col_n = len(rows[0])
                if any(len(row) != col_n for row in rows):
                    raise ValueError("Markdown table has inconsistent column count")
                if col_n > 7:
                    raise ValueError("Too many columns for portrait PDF; simplify table")
                layout = [[Paragraph(v, styles["head"] if i == 0 else styles["cell"]) for v in r] for i, r in enumerate(rows)]
                table = Table(layout, colWidths=[P_WIDTH / col_n] * col_n, repeatRows=1, hAlign="LEFT")
                table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#163740")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F8F7")]),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.35, colors.HexColor("#DEE6E5")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]))
                elements.extend([table, Spacer(1, 9)])
        elif typ == "list":
            for i, li in enumerate(block.get("children", [])):
                kids = li.get("children", [])
                body = _inline([child for b in kids for child in b.get("children", [])])
                prefix = f"{i + 1}. " if block.get("attrs", {}).get("ordered") else "• "
                elements.append(Paragraph(escape(prefix) + body, styles["body"]))
        elif typ == "block_quote":
            txt = " ".join(_inline(n.get("children")) for n in block.get("children", []))
            elements.append(Paragraph(txt, styles["body"]))
        elif typ == "block_code":
            elements.append(Paragraph(escape(block.get("raw", ""))[:2000], styles["body"]))
        elif typ in ("blank_line", "thematic_break"):
            elements.append(Spacer(1, 5))
    pdf = SimpleDocTemplate(str(target), pagesize=A4, leftMargin=18.5 * mm,
                            rightMargin=18.5 * mm, topMargin=19 * mm, bottomMargin=21 * mm,
                            title=content.splitlines()[0].lstrip("# ").strip()[:200])
    pdf.build(elements, onFirstPage=_footer, onLaterPages=_footer)
    checked = PdfReader(str(target))
    pages = len(checked.pages)
    images = sum(len(p.images) for p in checked.pages)
    links = sum(1 for p in checked.pages for a in p.get("/Annots", [])
                if a.get_object().get("/Subtype") == "/Link")
    return {"pdf": str(target), "pages": pages, "embedded_images": images, "links": links}


def render_preview(case_dir: Path, *, dpi: int = 115) -> list[str]:
    target = Path(case_dir).resolve() / "deliverables" / "report.pdf"
    preview = Path(case_dir).resolve() / "preview"
    preview.mkdir(parents=True, exist_ok=True)
    output = []
    doc = pypdfium2.PdfDocument(str(target))
    try:
        for i in range(len(doc)):
            fname = preview / f"page-{i + 1:02d}.png"
            page = doc[i]
            try:
                bitmap = page.render(scale=dpi / 72)
                bitmap.to_pil().save(fname)
                bitmap.close()
            finally:
                page.close()
            output.append(str(fname))
    finally:
        doc.close()
    return output
