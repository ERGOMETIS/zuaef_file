// Required: --input data=<path-to-typst.json>
// Optional: --input assets=<asset-root/> and --input lang=en|zh.
// Product images should keep their alpha channel and sit on the light-gray
// panel below. Never flood-fill black backgrounds: that can fill wheel spokes.
#let data-path = sys.inputs.at("data")
#let requested-lang = if "lang" in sys.inputs { sys.inputs.at("lang") } else { "en" }
#let lang = if requested-lang == "zh" { "zh" } else { "en" }
#let asset-input = if "assets" in sys.inputs { sys.inputs.at("assets") } else { "" }
#let asset-root = if asset-input == "" or asset-input.ends-with("/") { asset-input } else { asset-input + "/" }
#let r = json(data-path)

#let ink = rgb("#2b2f36")
#let navy = rgb("#1f3a5f")
#let muted = rgb("#66717d")
#let pale = rgb("#edf1f5")
#let panel = rgb("#F3F4F6")
#let rule = rgb("#d7dee6")
#let warm = rgb("#a66a2c")
#let warning-fill = rgb("#fbf4eb")
#let light-fill = rgb("#f6f8fa")

#let ui = (
  en: (
    decision_brief: "DECISION BRIEF",
    executive_summary: "Executive summary",
    price_band: "PRICE BAND",
    list_prices: "advertised list prices, not transactions",
    highlighted_models: "HIGHLIGHTED MODELS",
    flagship_count: "flagship / highlighted models",
    decision: "DECISION",
    follow_benchmark: "follow the benchmark",
    what_matters: "What matters",
    fact: "FACT",
    inference: "INFERENCE",
    why_decision: "WHY FOLLOW",
    next_action: "NEXT COMMERCIAL ACTION",
    range_map: "RANGE MAP",
    range_title: "Lineup at a glance",
    model: "Model",
    frame: "Frame / class",
    status: "Status",
    price: "Price",
    previous: "Old / previous",
    evidence_posture: "Evidence posture",
    featured: "Featured",
    not_highlighted: "Not highlighted",
    no_price: "—",
    product_profile: "PRODUCT PROFILE",
    specification: "Specification",
    value: "Value",
    not_recorded: "Not recorded",
    source_values: "Technical values are preserved from the evidence record.",
    sku: "SKU",
    image_source: "Image source",
    image_not_available: "No product image recorded",
    note: "NOTE",
    risk_register: "RISK REGISTER",
    risks_title: "Risks and unknowns",
    largest_uncertainty: "LARGEST UNCERTAINTY",
    unresolved_conflicts: "Unresolved conflicts",
    evidence_gaps: "Evidence gaps",
    open_questions: "Open questions before acting",
    sources: "EVIDENCE",
    sources_title: "Sources appendix",
    source_refs: "Source refs in the brief are bracket numbers. URLs are kept here so claims remain readable.",
    open_source: "Open source",
    url_not_stated: "URL not stated in the evidence record",
    image_rights: "IMAGE RIGHTS",
    image_rights_body: "Internal-analysis images; reuse rights require clearance from the rights-holder.",
    claims: "CLAIMS",
    claims_title: "Claim register",
    current_lineup: "Current e-bike lineup",
    market: "MARKET",
    research_date: "RESEARCH DATE",
    brief_label: "Product / competitor research brief",
    status_label: "STATUS",
    not_available: "Not available",
    motor: "Motor",
    torque: "Torque",
    battery: "Battery",
    transmission: "Transmission",
    brakes: "Brakes",
    speed_class: "Speed class",
    range: "Range",
    wheel_size_weight: "Wheel size / weight",
    weight: "Weight",
    rider_height: "Rider height",
    product_version: "Product version",
    colours: "Colours",
    delivery: "Delivery",
    variant_note: "Variant note",
    other: "Other / anchor",
  ),
  zh: (
    decision_brief: "决策简报",
    executive_summary: "执行摘要",
    price_band: "价格区间",
    list_prices: "广告标价，不是交易价格",
    highlighted_models: "重点型号",
    flagship_count: "旗舰 / 重点型号",
    decision: "决策",
    follow_benchmark: "跟踪该基准",
    what_matters: "关键事项",
    fact: "事实",
    inference: "推断",
    why_decision: "为何跟进",
    next_action: "下一步商业行动",
    range_map: "产品线地图",
    range_title: "产品线概览",
    model: "型号",
    frame: "车架 / 类别",
    status: "状态",
    price: "价格",
    previous: "旧 / 上一价格",
    evidence_posture: "证据定位",
    featured: "重点型号",
    not_highlighted: "未重点介绍",
    no_price: "—",
    product_profile: "产品档案",
    specification: "规格",
    value: "数值",
    not_recorded: "未记录",
    source_values: "技术数值保留自证据记录。",
    sku: "SKU",
    image_source: "图片来源",
    image_not_available: "未记录产品图片",
    note: "注",
    risk_register: "风险登记",
    risks_title: "风险与未知项",
    largest_uncertainty: "最大不确定性",
    unresolved_conflicts: "未解决的冲突",
    evidence_gaps: "证据缺口",
    open_questions: "行动前的开放问题",
    sources: "证据",
    sources_title: "来源附录",
    source_refs: "简报中的来源引用使用方括号编号。URL 集中列于此处，以保持主文可读。",
    open_source: "打开来源",
    url_not_stated: "证据记录未提供 URL",
    image_rights: "图片权利",
    image_rights_body: "图片仅用于内部分析；再次使用前必须向权利持有人确认权利。",
    claims: "主张",
    claims_title: "主张登记",
    current_lineup: "当前电动自行车产品线",
    market: "市场",
    research_date: "研究日期",
    brief_label: "产品 / 竞品研究简报",
    status_label: "状态",
    not_available: "不可用",
    motor: "电机",
    torque: "扭矩",
    battery: "电池",
    transmission: "传动系统",
    brakes: "刹车",
    speed_class: "速度等级",
    range: "续航",
    wheel_size_weight: "轮径 / 重量",
    weight: "重量",
    rider_height: "骑手身高",
    product_version: "产品版本",
    colours: "颜色",
    delivery: "交付",
    variant_note: "版本说明",
    other: "其他 / 锚点",
  ),
)

#let t(key) = ui.at(lang).at(key)
#let choose(en, zh: none) = if lang == "zh" and zh != none { zh } else { en }
#let jtext(obj, key) = {
  let en = obj.at(key)
  let zh-key = key + "_zh"
  let zh = if zh-key in obj { obj.at(zh-key) } else { none }
  choose(en, zh: zh)
}
#let specs-for(model) = if lang == "zh" { model.specs_zh } else { model.specs }
#let flagship-specs = if lang == "zh" { r.flagship_specs_zh } else { r.flagship_specs }
#let spec-label(key) = {
  let labels = ui.at(lang)
  if key in labels { labels.at(key) } else { key.replace("_", " ") }
}
#let spec-value(key, value) = {
  if value == none { t("not_recorded") }
  else if key == "colours" { value.join(", ") }
  else { value }
}
#let spec-cells(model) = {
  let cells = ()
  for (key, value) in specs-for(model) {
    cells = cells + (
      [#text(size: 7pt, weight: "bold", fill: muted)[#spec-label(key)]],
      [#text(size: 7pt)[#spec-value(key, value)]],
    )
  }
  cells
}
#let range-cells() = {
  let cells = ()
  for model in r.models {
    let old = if model.old_previous_price != none { jtext(model.old_previous_price, "display") } else { t("no_price") }
    let posture = if model.featured { t("featured") } else { t("not_highlighted") }
    cells = cells + (
      [#jtext(model, "name")],
      [#jtext(model, "frame")],
      [#jtext(model, "status")],
      [#jtext(model.price, "display")],
      [#old],
      [#posture],
    )
  }
  cells
}
#let source-no(id) = {
  let n = 1
  for source in r.sources {
    if source.id == id { return n }
    n += 1
  }
  0
}
#let cite(ids) = {
  if ids.len() == 0 { return [] }
  for (i, id) in ids.enumerate() {
    if i > 0 { ", " }
    [#text(size: 7pt, fill: navy)[#("[" + str(source-no(id)) + "]")]]
  }
}
#let source-text(url) = {
  url
    .replace("/", "/\u{200B}")
    .replace("?", "?\u{200B}")
    .replace("&", "&\u{200B}")
    .replace("=", "=\u{200B}")
    .replace(".", ".\u{200B}")
    .replace("-", "-\u{200B}")
    .replace("_", "_\u{200B}")
}
#let url-line(url) = [
  #link(url)[#text(size: 6pt, fill: navy, hyphenate: true)[#source-text(url)]]
]
#let source-card(i, source) = block(
  fill: if calc.odd(i) { light-fill } else { white },
  stroke: 0.35pt + rule,
  inset: (x: 3.5pt, y: 0.5pt),
  breakable: false,
)[
  #grid(
    columns: (7mm, 1fr),
    [#text(size: 8.5pt, weight: "bold", fill: navy)[#(i + 1)]],
    [
      #text(weight: "bold", size: 6.8pt)[#source.id  —  #jtext(source, "title")]
      #if source.url != none [
        #linebreak()
        #url-line(source.url)
      ] else if source.urls.len() == 0 [
        #linebreak()
        #text(size: 7pt, fill: muted)[#t("url_not_stated")]
      ]
      #for url in source.urls [
        #linebreak()
        #url-line(url)
      ]
    ]
  )
]
#let source-cells() = {
  let cells = ()
  for (i, source) in r.sources.enumerate() {
    cells = cells + ([#source-card(i, source)],)
  }
  cells
}

#set page(
  paper: "a4",
  margin: (top: 13mm, bottom: 14mm, left: 16mm, right: 16mm),
  fill: white,
  footer: context [
    #line(length: 100%, stroke: 0.45pt + rule)
    #align(right)[#text(size: 7.5pt, fill: muted)[#jtext(r, "brand") / #jtext(r, "market")  •  #counter(page).display()]]
  ],
)
#set text(
  font: if lang == "zh" { ("Noto Sans CJK SC", "Noto Serif CJK SC") } else { ("Liberation Sans", "Noto Sans CJK SC", "DejaVu Sans") },
  size: 9.5pt,
  fill: ink,
  lang: lang,
  region: if lang == "zh" { "cn" } else { "us" },
)
#set par(leading: 0.58em, justify: false)
#set block(spacing: 5pt)

// Keep kicker + heading + rule together so labels never orphan at page bottoms.
#let section-title(kicker, title) = block(breakable: false, width: 100%, spacing: 0pt)[
  #text(size: 8pt, weight: "bold", fill: navy, tracking: 0.8pt)[#kicker]
  #v(2pt)
  #text(size: 18pt, weight: "bold", fill: ink)[#title]
  #v(3pt)
  #line(length: 100%, stroke: 1pt + navy)
]

// Pair a section title with its first body block so both move together.
#let section-lead(kicker, title, body) = block(breakable: false, width: 100%, spacing: 0pt)[
  #section-title(kicker, title)
  #v(6pt)
  #body
]

#let pill(label, color: navy, fill: pale) = box(
  fill: fill,
  stroke: 0.7pt + color,
  radius: 3pt,
  inset: (x: 6pt, y: 3pt),
)[#text(size: 7.5pt, weight: "bold", fill: color, tracking: 0.35pt)[#label]]
#let callout(title, body, fill: pale, stroke: rule, breakable: true) = block(
  fill: fill,
  stroke: 0.7pt + stroke,
  radius: 3pt,
  inset: 7pt,
  breakable: breakable,
)[
  #text(size: 8pt, weight: "bold", fill: navy, tracking: 0.45pt)[#title]
  #v(2pt)
  #body
]

#let range-callout-cells() = {
  let cells = ()
  for (i, item) in r.range_callouts.enumerate() {
    cells = cells + (
      callout(jtext(item, "title"), [#jtext(item, "text") #cite(item.source_ids)], fill: if calc.odd(i) { pale } else { light-fill }, breakable: false),
    )
  }
  cells
}

#let image-box(path, width: 62mm, height: 44mm) = {
  if path == none {
    block(fill: panel, radius: 3pt, inset: 6pt, width: width, height: height)[
      #align(center + horizon)[#text(size: 8pt, fill: muted)[#t("image_not_available")]]
    ]
  } else {
    block(fill: panel, radius: 3pt, inset: 2pt, width: width, height: height)[
      #align(center + horizon)[
        #image(asset-root + path, width: width - 4pt, height: height - 4pt, fit: "contain")
      ]
    ]
  }
}

// Compact, non-breakable profile card so two/three shorter profiles can share a page
// and the PRODUCT PROFILE kicker never sits alone at a page bottom.
#let product-profile-title(name) = block(breakable: false, width: 100%, spacing: 0pt)[
  #text(size: 7.5pt, weight: "bold", fill: navy, tracking: 0.8pt)[#t("product_profile")]
  #v(1.5pt)
  #text(size: 15pt, weight: "bold", fill: ink)[#name]
  #v(2pt)
  #line(length: 100%, stroke: 1pt + navy)
]

#let product-profile(model) = block(breakable: false, width: 100%, spacing: 6pt)[
  #product-profile-title(jtext(model, "name"))
  #v(3pt)
  #block(
    fill: white,
    stroke: 0.7pt + rule,
    radius: 3pt,
    inset: 4pt,
    width: 100%,
  )[
    #grid(
      columns: (0.88fr, 1.18fr),
      gutter: 3.5mm,
      [
        #image-box(model.image)
        #if model.image_caption != none [
          #v(1pt)
          #text(size: 6.5pt, fill: muted)[#jtext(model, "image_caption")]
        ]
        #if model.image_provenance != none [
          #v(0.5pt)
          #text(size: 6pt, fill: muted)[#t("image_source")  #cite(model.spec_source_ids)]
        ]
      ],
      [
        #text(size: 7pt, weight: "bold", fill: navy, tracking: 0.45pt)[#jtext(model, "frame")]
        #v(1pt)
        #text(size: 13pt, weight: "bold")[#jtext(model.price, "display")]
        #h(2pt)
        #text(size: 7pt, fill: muted)[#jtext(model.price, "currency")  •  #jtext(model, "status")  •  #jtext(model, "price_date")]
        #if model.sku != none [
          #v(0.5pt)
          #text(size: 6.5pt, fill: muted)[#t("sku"): #model.sku]
        ]
        #v(2pt)
        #if model.specs.len() == 0 [
          #text(size: 7.5pt, fill: muted)[#t("not_recorded")]
        ] else [
          #table(
            columns: (0.74fr, 1.26fr),
            inset: 2.4pt,
            stroke: 0.35pt + rule,
            table.header([#t("specification")], [#t("value")]),
            ..spec-cells(model),
          )
        ]
      ],
    )
  ]
  #if model.spec_note != none [
    #v(2pt)
    #callout(t("variant_note"), [#jtext(model, "spec_note") #cite(model.spec_source_ids)], fill: light-fill, breakable: false)
  ]
  #v(1pt)
  #text(size: 6.5pt, fill: muted)[#t("source_values") #cite(model.spec_source_ids)]
]

// Cover — fill the page with a larger hero; keep meta near the image.
#align(left)[
  #text(size: 8pt, weight: "bold", fill: navy, tracking: 1pt)[#jtext(r, "brand")  /  #jtext(r, "market")]
  #v(4mm)
  #text(size: 30pt, weight: "bold", fill: ink)[#jtext(r, "brand")]
  #v(1pt)
  #text(size: 14pt, fill: navy)[#t("current_lineup")]
  #v(4pt)
  #line(length: 34mm, stroke: 2pt + navy)
  #v(4pt)
  #text(size: 9.5pt, fill: muted)[#jtext(r, "scope")]
  #v(3.5mm)
  #grid(
    columns: (1fr, 1fr),
    gutter: 8mm,
    [
      #text(size: 8pt, weight: "bold", fill: navy)[#t("market")]
      #v(1pt)
      #text(size: 9.5pt)[#jtext(r, "market")]
    ],
    [
      #text(size: 8pt, weight: "bold", fill: navy)[#t("research_date")]
      #v(1pt)
      #text(size: 9.5pt)[#jtext(r, "date")]
    ],
  )
  #v(3.5mm)
  #if r.cover_image != none [
    #image-box(r.cover_image, width: 178mm, height: 148mm)
  ] else [
    #image-box(none, width: 178mm, height: 148mm)
  ]
  #v(2pt)
  #text(size: 7.5pt, fill: muted)[#jtext(r, "cover_caption") #cite(r.cover_source_ids)]
  #v(4mm)
  #line(length: 100%, stroke: 0.7pt + rule)
  #v(3pt)
  #grid(
    columns: (1fr, auto),
    [#text(size: 8pt, fill: muted)[#t("brief_label")]],
    [#text(size: 8pt, weight: "bold", fill: navy)[#jtext(r.decision, "label")]],
  )
]
#pagebreak()

// Executive summary
#section-lead(t("decision_brief"), t("executive_summary"), grid(
  columns: (1fr, 1fr, 1fr),
  gutter: 4mm,
  block(fill: pale, radius: 3pt, inset: 6pt, breakable: false)[
    #text(size: 8pt, weight: "bold", fill: navy)[#t("price_band")]
    #v(3pt)
    #text(size: 13pt, weight: "bold")[#jtext(r.price_band, "display")]
    #v(2pt)
    #text(size: 7.5pt, fill: muted)[#jtext(r.price_band, "basis")]
  ],
  block(fill: pale, radius: 3pt, inset: 6pt, breakable: false)[
    #text(size: 8pt, weight: "bold", fill: navy)[#t("highlighted_models")]
    #v(3pt)
    #text(size: 11pt, weight: "bold")[#r.models.filter(model => model.featured).map(model => jtext(model, "name")).join(" / ")]
    #v(2pt)
    #text(size: 7.5pt, fill: muted)[#r.models.filter(model => model.featured).len()  #t("flagship_count")]
  ],
  block(fill: navy, radius: 3pt, inset: 6pt, breakable: false)[
    #text(size: 8pt, weight: "bold", fill: white)[#t("decision")]
    #v(3pt)
    #text(size: 13pt, weight: "bold", fill: white)[#jtext(r.decision, "label")]
    #v(2pt)
    #text(size: 7.5pt, fill: white)[#t("follow_benchmark")]
  ],
))
#v(6pt)
#text(size: 10.5pt, weight: "bold")[#t("what_matters")]
#v(3pt)
#for item in r.key_takeaways [
  #block(inset: (left: 0pt, right: 0pt, top: 2pt, bottom: 2pt), breakable: true)[
    #grid(
      columns: (20mm, 1fr),
      gutter: 3mm,
      [#if item.inference { pill(t("inference"), color: warm, fill: warning-fill) } else { pill(t("fact")) }],
      [#jtext(item, "text") #cite(item.source_ids)]
    )
  ]
]
#v(6pt)
#grid(
  columns: (1.1fr, 0.9fr),
  gutter: 7mm,
  callout(t("why_decision"), [
    #for (i, reason) in r.decision.reasons.enumerate() [
      #block(inset: (left: 0pt, right: 0pt, top: 2pt, bottom: 3pt), breakable: true)[
        #text(fill: navy, weight: "bold")[•] #choose(reason, zh: r.decision.reasons_zh.at(i))
      ]
    ]
  ], fill: light-fill),
  callout(t("next_action"), [#jtext(r.decision, "next_commercial_action")], fill: pale),
)

// Range map — keep kicker/title with the summary and table so they never orphan.
#section-lead(t("range_map"), t("range_title"), [
  #text(size: 9pt)[#jtext(r, "range_summary")]
  #v(5pt)
  #text(size: 8.5pt)[
    #table(
      columns: (1.05fr, 1.12fr, 1.35fr, 0.72fr, 0.78fr, 1.05fr),
      inset: 3.5pt,
      stroke: 0.35pt + rule,
      table.header([#t("model")], [#t("frame")], [#t("status")], [#t("price")], [#t("previous")], [#t("evidence_posture")]),
      ..range-cells(),
    )
  ]
])
#v(5pt)
#grid(
  columns: (1fr, 1fr),
  gutter: 5mm,
  ..range-callout-cells(),
)

// Product profiles
#for model in r.models {
  if model.featured { product-profile(model) }
}

// Risks and unknowns
#section-lead(t("risk_register"), t("risks_title"), callout(
  t("largest_uncertainty"),
  [#jtext(r.decision, "largest_uncertainty")],
  fill: warning-fill,
  stroke: rgb("#d9b78f"),
  breakable: false,
))
#v(5pt)
#text(size: 10.5pt, weight: "bold")[#t("unresolved_conflicts")]
#v(3pt)
#for conflict in r.unresolved_conflicts [
  #block(
    fill: light-fill,
    stroke: 0.5pt + rule,
    radius: 3pt,
    inset: 7pt,
    breakable: false,
  )[
    #grid(
      columns: (1fr, auto),
      [#text(weight: "bold")[#jtext(conflict, "title")]],
      [#pill(jtext(conflict, "status"), color: warm, fill: warning-fill)]
    )
    #v(3pt)
    #text(size: 8.7pt)[#jtext(conflict, "detail") #cite(conflict.source_ids)]
  ]
]
#v(5pt)
#text(size: 10.5pt, weight: "bold")[#t("evidence_gaps")]
#v(2pt)
#for (i, gap) in r.evidence_gaps.enumerate() [
  #block(inset: (left: 0pt, right: 0pt, top: 1pt, bottom: 1pt), breakable: false)[
    #text(size: 8pt, fill: navy, weight: "bold")[•] #text(size: 8pt)[#if lang == "zh" { r.evidence_gaps_zh.at(i) } else { gap }]
  ]
]
#v(3pt)
#block(breakable: false)[
  #text(size: 10pt, weight: "bold")[#t("open_questions")]
  #v(1.5pt)
  #for (i, question) in r.open_questions.enumerate() [
    #grid(columns: (6mm, 1fr), gutter: 1.5mm, [#text(size: 8pt, weight: "bold", fill: navy)[#(i + 1)]], [#text(size: 8pt)[#if lang == "zh" { r.open_questions_zh.at(i) } else { question }]])
  ]
]

// Claims appendix
#section-lead(t("claims"), t("claims_title"), [
  #for claim in r.claims [
    #block(inset: (left: 0pt, right: 0pt, top: 0.8pt, bottom: 0.8pt), breakable: false)[
      #text(size: 7pt, weight: "bold", fill: navy)[#claim.id]
      #h(3pt)
      #text(size: 7pt)[#jtext(claim, "text") #cite(claim.source_ids)]
    ]
  ]
])

// Sources appendix
#section-lead(t("sources"), t("sources_title"), text(size: 8pt)[#t("source_refs")])
#v(2pt)
#if r.sources.len() >= 9 [
  #table(
    columns: (1fr, 1fr, 1fr),
    gutter: 2.5mm,
    inset: 0pt,
    stroke: none,
    ..source-cells(),
  )
] else [
  #table(
    columns: (1fr, 1fr),
    gutter: 3.5mm,
    inset: 0pt,
    stroke: none,
    ..source-cells(),
  )
]


