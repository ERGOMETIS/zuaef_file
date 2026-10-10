# Product slice: source-backed competitor report

## Intent

A factory operator, product manager or market analyst gives one brand website, model name or short decision question and wants to know what products exist, where they compete, which claims are evidenced and what action to take.

## Reality

Models, prices, photos, speeds and regulatory configurations vary by market and year. Suppliers rarely disclose complete BOM/FOB/MOQ. Search summaries and third-party pictures can be stale or wrong. Source identity is not image identity; byte validation is not licensing.

## Product slice

One model-operated research run, official web tools, one narrow `ProductResearchCapability`, persistent working Markdown, direct linked sources, local genuine images, rendered customer PDF and human final review. No platform services or orchestration.

## Direct execution

1. `product-research init cases/new --lead ...` to capture target/market/decision.
2. `product-research run cases/new --model ...` to investigate live sources and save a working report.
3. `product-research render cases/new --preview` to create PDF and page images deterministically.
4. Operator inspects decisive sources, exact photo/SKU combinations and report pages; edits `report.md` if needed, then re-renders.

## Real verification

One unfamiliar real brand, no prewritten answer: client can use the PDF with no material factual errors; decisive claims point to actual opened sources; product photos match named variants; source conflicts are visible; business action is coherent. This has not yet been demonstrated end-to-end in the present environment.
