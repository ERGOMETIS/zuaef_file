# STILLEVO Market Report Skill (v0.1)

A standalone Agent Skill for turning verified research data into clean A4 HTML/PDF client reports.

## Quick start

```bash
cd stillevo-market-report
python -m pip install -r requirements.txt
python scripts/build_report.py --input examples/demo_report.json --out-dir output/demo
```

No external API, account, browser, or model is required for rendering. The sample report and bicycle illustrations are fictional and not suitable for actual customer delivery.

## Using real research

1. Copy `examples/demo_report.json` to a case directory, e.g. `research/vanmoof/report.json`.
2. Replace every sample fact with the actual findings and source IDs.
3. Save real, permitted product images in `research/vanmoof/images/` and change the `image` paths.
4. Run:

```bash
python scripts/build_report.py --input research/vanmoof/report.json --out-dir output/vanmoof
```

Outputs: `report.pdf`, portable `report.html`, and `build_notes.txt`.

For one-off formatting, do not build a new UI or schema infrastructure. WorkLPG may register the resulting PDF and associated receipt as an Artifact independently.
