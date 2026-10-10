"""Standalone command interface. A business result remains a file, not a run status."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path

from .render import render_preview, render_report

INPUT_TEMPLATE = """# Research request

- Lead: {lead}
- Target market: {market}
- Decision question: {goal}
- Research date: {today}

Research from live sources. Produce report.md and evidence.md, cite inspected pages,
preserve unresolved conflicts, use actual SKU-specific photos and give one commercial action.
"""


def init_case(path: Path, lead: str, market: str, goal: str) -> Path:
    path = path.expanduser().resolve()
    if path.exists() and any(path.iterdir()):
        raise FileExistsError(f"Nonempty case directory: {path}. Choose a fresh directory.")
    path.mkdir(parents=True, exist_ok=True)
    (path / "assets").mkdir(exist_ok=True)
    (path / "deliverables").mkdir(exist_ok=True)
    (path / "input.md").write_text(
        INPUT_TEMPLATE.format(lead=lead, market=market, goal=goal, today=date.today().isoformat()),
        encoding="utf-8",
    )
    return path


async def execute(path: Path, model: str, *, request_limit: int = 45) -> None:
    from pydantic_ai import UsageLimits
    from .agent import build_agent
    path = path.resolve()
    agent = build_agent(model, path)
    prompt = ("Research this case from input.md. Save actual report.md and evidence.md "
              "as you work. Cite source URLs and retain unknowns. "
              "Use authentic images only after matching the visible model and SKU. "
              "Stop when the report makes a useful business decision.")
    outcome = await agent.run(prompt, usage_limits=UsageLimits(request_limit=request_limit))
    print(str(outcome.output)[:2000])
    if not (path / "report.md").is_file():
        raise RuntimeError("The model returned without saving report.md. No report will be claimed.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Open, native-Harness product and competitor research")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Create a fresh research case")
    init.add_argument("case", type=Path)
    init.add_argument("--lead", required=True, help="URL, brand, model or natural-language lead")
    init.add_argument("--market", default="Europe")
    init.add_argument("--goal", default="Product benchmarking and OEM/ODM opportunities")
    run = commands.add_parser("run", help="Run the actual PydanticAI agent on an initialized case")
    run.add_argument("case", type=Path)
    run.add_argument("--model", default=os.environ.get("PYDANTIC_AI_MODEL", ""))
    run.add_argument("--request-limit", type=int, default=45)
    out = commands.add_parser("render", help="Render existing report.md and optional preview")
    out.add_argument("case", type=Path)
    out.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    if args.command == "init":
        print(init_case(args.case, args.lead, args.market, args.goal))
    elif args.command == "run":
        if not (args.case / "input.md").exists():
            parser.error("No input.md. Run `product-research init` first.")
        if not args.model:
            parser.error("Set --model or PYDANTIC_AI_MODEL")
        partial = False
        try:
            asyncio.run(execute(args.case, args.model, request_limit=args.request_limit))
        except Exception as exc:
            if not (args.case / "report.md").is_file():
                raise
            partial = True
            print(f"Research stopped; preserving partial report: {type(exc).__name__}: {exc}", file=sys.stderr)
        print(json.dumps(render_report(args.case), ensure_ascii=False))
        if partial:
            raise SystemExit(2)
    elif args.command == "render":
        print(json.dumps(render_report(args.case), ensure_ascii=False))
        if args.preview:
            for f in render_preview(args.case):
                print(f)


if __name__ == "__main__":
    main()
