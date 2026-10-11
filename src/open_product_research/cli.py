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
    from pydantic_ai.exceptions import UsageLimitExceeded
    from .agent import build_agent
    path = path.resolve()
    agent = build_agent(model, path)
    prompt = ("Research this case from input.md. Save actual report.md and evidence.md "
              "as you work. Cite source URLs and retain unknowns. "
              "Use authentic images only after matching the visible model and SKU. "
              "Stop when the report makes a useful business decision.")
    # Cheap models narrate instead of acting: they end turns without tool calls
    # (PydanticAI treats that as completion) and they happily fetch for twenty
    # requests without ever writing a file. Both shapes land in the same place
    # — no report.md — so one loop handles them: keep the SAME conversation and
    # order a hard deliverable-first action until the file exists or the
    # attempt budget runs out. Never claim a result we do not have.
    nudge = ("STOP narrating. Your FIRST tool call this turn must be write_file "
             "saving report.md with everything researched so far — imperfect is "
             "fine, facts first. Then write_file evidence.md. After both files "
             "exist, keep improving them with further research.")
    continue_nudge = (
        "report.md exists but is a SKELETON with empty placeholder sections. "
        "This turn: fill EVERY section of report.md with the researched facts "
        "(you already have the SKU catalog — use it), then write evidence.md "
        "listing each source URL, visit date and the exact claim it supports. "
        "Do not stop until both files are complete documents."
    )

    def deliverables_ready() -> bool:
        report = path / "report.md"
        evidence = path / "evidence.md"
        if not (report.is_file() and evidence.is_file()):
            return False
        text = report.read_text(encoding="utf-8")
        hollow = ("provisional working document", "populated from inspected pages",
                  "*(Lineup", "*(EU EPAC", "*(Dutch price")
        return len(text) >= 4_000 and not any(marker in text for marker in hollow)

    outcome = None
    last_error: Exception | None = None
    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            if outcome is None:
                first = continue_nudge if (path / "report.md").is_file() else prompt
                outcome = await agent.run(first, usage_limits=UsageLimits(request_limit=request_limit))
            else:
                outcome = await agent.run(
                    continue_nudge if (path / "report.md").is_file() else nudge,
                    message_history=outcome.all_messages(),
                    usage_limits=UsageLimits(request_limit=request_limit),
                )
            last_error = None
        except UsageLimitExceeded as exc:
            last_error = exc
        except Exception as exc:  # noqa: BLE001 — e.g. tool retry exhaustion
            if deliverables_ready():
                # The model kept polishing after the deliverables were already
                # complete and tripped over its own feet. Ship what we have.
                print(f"run interrupted after deliverables complete: {type(exc).__name__}",
                      file=sys.stderr)
                break
            raise
        if deliverables_ready():
            break
        reason = type(last_error).__name__ if last_error else "deliverables incomplete"
        print(f"attempt {attempt + 1}/{max_attempts}: {reason}; continuing", file=sys.stderr)
    if outcome is not None:
        print(str(outcome.output)[:2000])
    if not (path / "report.md").is_file():
        detail = f": {last_error}" if last_error else ""
        raise RuntimeError(
            "The model returned without saving report.md. No report will be claimed." + detail
        )


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
