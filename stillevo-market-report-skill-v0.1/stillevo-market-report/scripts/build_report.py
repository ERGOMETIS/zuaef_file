#!/usr/bin/env python3
"""Render an evidence-linked research report from local JSON; no network calls."""
import argparse
import base64
from html import escape
import json
import mimetypes
from pathlib import Path
from urllib.parse import urlparse
import sys

HERE = Path(__file__).resolve().parent.parent
CSS_FILE = HERE / 'assets' / 'report.css'


def e(x):
    return escape(str(x if x is not None else ''), quote=True)


def text_or(x, fallback='待核验'):
    s = str(x or '').strip()
    return s if s else fallback


def data_image(path_str, base_dir, notes):
    if not path_str:
        return None
    image_path = (base_dir / path_str).resolve()
    if not image_path.is_file():
        notes.append(f'Image not found: {path_str}')
        return None
    mime = mimetypes.guess_type(image_path.name)[0] or 'application/octet-stream'
    if mime not in ('image/png', 'image/jpeg', 'image/webp', 'image/svg+xml', 'image/gif'):
        notes.append(f'Unsupported image MIME {mime}: {path_str}')
        return None
    return f'data:{mime};base64,{base64.b64encode(image_path.read_bytes()).decode("ascii")}'


def source_labels(ids, known, notes, context):
    ids = ids or []
    if not ids:
        notes.append(f'Missing source ID: {context}')
        return '<span class="chip">NO SOURCE</span>'
    out=[]
    for source_id in ids:
        if source_id not in known:
            notes.append(f'Unknown source ID {source_id}: {context}')
        out.append(f'<span class="chip">{e(source_id)}</span>')
    return ''.join(out)


def safe_link(url):
    parsed=urlparse(str(url or ''))
    if parsed.scheme in ('http','https') and parsed.netloc:
        return f'<a href="{e(url)}">{e(url)}</a>'
    return e(url or 'No URL recorded')


def section_head(kicker, heading, right=''):
    return f'''<div class="section-head"><div><div class="section-kicker">{e(kicker)}</div><h2>{e(heading)}</h2></div><div class="section-aside">{e(right)}</div></div>'''


def html_report(data, base_dir, notes):
    meta=data.get('meta') or {}
    summary=data.get('summary') or {}
    products=data.get('products') or []
    sources=data.get('sources') or []
    questions=data.get('open_questions') or []
    known={s.get('id') for s in sources if s.get('id')}
    brand=text_or(meta.get('brand'),'Unnamed brand')
    title=text_or(meta.get('title'),'Product Intelligence')
    as_of=text_or(meta.get('as_of'),'Date not recorded')
    status=text_or(meta.get('status'),'DRAFT')
    logo_name = text_or(meta.get('prepared_by'),'STILLEVO')

    cover_image = None
    for p in products:
        if p.get('image'):
            cover_image = data_image(p['image'], base_dir, notes)
            if cover_image: break
    cover_fig = (f'<img src="{cover_image}" alt="Sample hero image">' if cover_image else '<span>NO PRODUCT PHOTOGRAPH</span>')
    demo_banner = '<div class="watermark">Fictional sample data · Not client ready</div>' if meta.get('demo') else ''
    cover = f'''<section class="cover">
      <div class="topline"><div class="wordmark">STILLEVO<small>坐驰未来 / RESEARCH SERVICES</small></div><div class="serial">MARKET INTELLIGENCE<br>{e(as_of)}<br><span class="status">{e(status)}</span></div></div>
      <div class="eyebrow">BRAND PRODUCT RESEARCH / {e(meta.get('region','Market unspecified'))}</div>
      <h1>{e(title)}</h1><div class="sub">{e(meta.get('subtitle','Product line · pricing · specifications · evidence'))}</div>
      <div class="photo">{cover_fig}<span class="tile-label">{e(brand)} / PRODUCT LANDSCAPE</span></div>
      <div class="bottomline"><span>{e(logo_name)}</span><span>{e(meta.get('disclaimer','Source-linked research brief'))}</span></div>
    </section>'''

    findings=summary.get('findings') or []
    find_html=''.join(f'<div class="finding"><strong>{i:02d}</strong>{e(item)}</div>' for i,item in enumerate(findings,1)) or '<p>No findings supplied.</p>'
    summary_page=f'''<section class="page-section summary-page">
      {section_head('01 / Executive Brief','研究摘要', f'{brand} / {as_of}')}
      <p class="lead">{e(summary.get('lead','No executive summary provided.'))}</p>
      <div class="metrics"><div class="metric"><b>{len(products):02d}</b><span>PRODUCT ENTRIES</span></div><div class="metric"><b>{len(sources):02d}</b><span>LISTED SOURCES</span></div><div class="metric"><b>{len(questions):02d}</b><span>OPEN QUESTIONS</span></div></div>
      <div class="content-grid"><div><div class="mini-heading">Key observations</div>{find_html}</div><div><div class="scope"><b>SCOPE &amp; LIMITATIONS</b>{e(summary.get('scope','Scope not described.'))}</div>{demo_banner}</div></div>
    </section>'''

    profiles=[]
    for idx,p in enumerate(products,1):
        name=text_or(p.get('name'),'Unnamed model')
        price=p.get('price') or {}
        price_str=text_or(price.get('display'))
        img = data_image(p.get('image',''), base_dir, notes)
        photo=f'<img src="{img}" alt="{e(name)}">' if img else '<div class="nothing">真实车型图片尚未提供 / No verified product photograph</div>'
        raw_specs=p.get('specs') or []
        spec_rows=[]
        for spec in raw_specs:
            label = spec.get('label', '—')
            chips = source_labels(spec.get('source_ids'), known, notes, f'{name} / {label}')
            spec_rows.append(f'<tr><td>{e(label)}</td><td>{e(text_or(spec.get("value")))}</td><td>{chips}</td></tr>')
        specs = ''.join(spec_rows)
        if not specs: specs='<tr><td>Specifications</td><td>待核验</td><td>—</td></tr>'
        notes_list=''.join(f'<p class="note">• {e(n)}</p>' for n in (p.get('notes') or [])) or '<p>No notes entered.</p>'
        profile=f'''<section class="page-section product-page">
        {section_head(f'02 / Product Profile {idx:02d}',name,f'{brand} / {e(p.get("category",""))}')}
        <div class="product-intro">{e(text_or(p.get('positioning'),'Positioning not recorded'))}</div>
        <div class="product-hero"><div class="product-photo">{photo}<small>{e(p.get('image_credit','Image source not recorded'))}</small></div><div class="product-price"><div class="price-label">Observed price</div><strong>{e(price_str)}</strong><p>{e(price.get('note','Region, date and currency not specified'))}</p><div class="source-chips">{source_labels(price.get('source_ids'),known,notes,f'{name} / price')}</div></div></div>
        <div class="mini-heading">Selected specifications</div><table class="specs">{specs}</table>
        <div class="product-footer"><div><div class="mini-heading">Research notes</div><div class="notes">{notes_list}</div></div><div><div class="mini-heading">Evidence</div><div class="caption">Source IDs for product: {source_labels(p.get('source_ids'),known,notes,f'{name} / product')}<br>Full source URLs appear in the Source Index.</div></div></div>
        </section>'''
        profiles.append(profile)

    comparows=''.join(f'<tr><td class="model">{e(p.get("name","—"))}</td><td>{e(p.get("category","—"))}</td><td>{e((p.get("price") or {}).get("display","待核验"))}<br><span class="source-chips">{source_labels((p.get("price") or {}).get("source_ids"),known,notes,f"{p.get('name','?')} / comparison price")}</span></td></tr>' for p in products)
    comparison=f'''<section class="page-section comparison-page">
       {section_head('03 / Competitive View','产品组合速览',f'{len(products)} listed products')}
       <p class="lead">本页只并排呈现已记录的产品与价格，不自动推断各市场价格可比，也不据此计算市场份额。</p>
       <div class="table-wrap"><table class="compare"><thead><tr><th>PRODUCT / MODEL</th><th>CATEGORY</th><th>OBSERVED PRICE</th></tr></thead><tbody>{comparows}</tbody></table></div>
       <div class="disclaimer">{e(meta.get('disclaimer','Information may change.'))} · Prices, currency, regions and observation dates must be read alongside the underlying source pages.</div>
    </section>'''

    source_html=''.join(f'''<div class="source-entry"><span class="id">{e(s.get('id','—'))}</span><span class="title">{e(s.get('title','Untitled source'))}</span><div class="url">{safe_link(s.get('url'))}</div><div class="accessed">Accessed: {e(s.get('accessed','not recorded'))} · {e(s.get('note',''))}</div></div>''' for s in sources) or '<div class="nothing">No sources recorded.</div>'
    questions_html='<ol class="questions">'+''.join(f'<li>{e(q)}</li>' for q in questions)+'</ol>' if questions else '<p class="nothing">No open questions recorded (not a guarantee of completeness).</p>'
    evidence=f'''<section class="page-section evidence-page">
       {section_head('04 / Traceability','来源与待确认事项',f'{len(sources)} links / {len(questions)} questions')}
       <div class="mini-heading">Source index</div>{source_html}
       <div class="mini-heading" style="margin-top:20px">Open questions / Pending verification</div>{questions_html}
       <p class="disclaimer">Report status: {e(status)}. A formatted report is not independent verification of its underlying content.</p>
    </section>'''

    css = CSS_FILE.read_text(encoding='utf-8')
    # Use a neutral static brand in page margin: CSS running header can be changed per document manually.
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{e(title)}</title><style>{css}</style></head><body data-brand="{e(brand)}">{cover}{summary_page}{''.join(profiles)}{comparison}{evidence}</body></html>'''


def main():
    ap=argparse.ArgumentParser(description='Render client report from local research JSON.')
    ap.add_argument('--input', required=True, type=Path, help='Path to report.json')
    ap.add_argument('--out-dir', required=True, type=Path, help='Output directory')
    ap.add_argument('--html-only', action='store_true', help='Create HTML without PDF')
    args=ap.parse_args()
    if not args.input.is_file():
        ap.error(f'Input not found: {args.input}')
    data=json.loads(args.input.read_text(encoding='utf-8'))
    if not isinstance(data,dict):
        ap.error('Input JSON root must be an object')
    for key in ('meta','summary','products','sources'):
        if key not in data:
            ap.error(f'Missing required top-level field: {key}')
    output=args.out_dir.resolve()
    output.mkdir(parents=True,exist_ok=True)
    notes=[]
    html=html_report(data,args.input.resolve().parent,notes)
    html_path=output/'report.html'
    html_path.write_text(html,encoding='utf-8')
    (output/'build_notes.txt').write_text(('\n'.join(dict.fromkeys(notes)) or 'No missing image/source-ID references detected.')+'\n',encoding='utf-8')
    print(f'HTML: {html_path}')
    if not args.html_only:
        try:
            from weasyprint import HTML
        except ImportError:
            print('WeasyPrint is not installed. Install via: python -m pip install -r requirements.txt',file=sys.stderr)
            return 2
        pdf_path=output/'report.pdf'
        HTML(string=html,base_url=str(output)).write_pdf(str(pdf_path))
        print(f'PDF:  {pdf_path}')
    print(f'Notes: {output / "build_notes.txt"} ({len(dict.fromkeys(notes))} items)')
    return 0

if __name__=='__main__':
    sys.exit(main())
