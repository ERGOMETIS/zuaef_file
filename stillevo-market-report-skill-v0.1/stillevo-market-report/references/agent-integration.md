# Agent integration: minimal execution slice

This skill describes a repeatable document production capability. It does **not** automatically become a worker, PydanticAI tool, or WorkLPG job just by copying `SKILL.md`.

## Suitable invocation

Ask your executing agent:

> Use the `stillevo-market-report` skill to convert this completed research into a customer-readable report. Preserve all evidence URLs, currency, region, as-of date, and unknowns. Use only local product photos supplied with the research. Produce PDF and HTML. Do not redo research, invent missing prices/specs, or build a new app. Open the rendered PDF and fix visible layout defects. Return the output file paths and known open questions.

The Agent needs local filesystem and a shell tool. Run from the skill root:

```bash
python scripts/build_report.py --input /ABS/PATH/report.json --out-dir /ABS/PATH/output
```

## PydanticAI / Code Agent

- Let the Agent produce or review the JSON and call the script through its **existing** shell/file tools. No new platform abstraction is needed.
- This render command does not itself perform research, inspect URLs, or supervise another Agent.
- A separate code Agent may spot-check the generated PDF if the workflow already contains one. Do not mandate a second worker as a design requirement.

## WorkLPG (optional)

Register the output file as an Artifact and use the existing Receipt mechanism to record input JSON, output PDF/HTML paths, render success/failure, and remaining open questions. Use the current WorkLPG schema; this Skill does not define a replacement schema.
