"""Use upstream Pydantic AI/Harness to run one research agent."""
from __future__ import annotations

from pathlib import Path

from .capability import make_product_research_capability


def build_agent(model: str, case_dir: str | Path):
    """No subagents, own approval stack, dispatcher or checkpoint implementation."""
    from pydantic_ai import Agent
    from pydantic_ai.capabilities import LocalWorkspace, WebSearch, WebFetch
    from pydantic_ai_harness import FileSystem

    case_dir = Path(case_dir).expanduser().resolve()
    case_dir.mkdir(parents=True, exist_ok=True)
    return Agent(
        model,
        name="product-research",
        capabilities=[
            LocalWorkspace(str(case_dir)),
            FileSystem(tools=["read_file", "write_file", "edit_file", "list_directory"],
                       content_hashes=False),
            WebSearch(local="duckduckgo"),
            WebFetch(local=True),
            make_product_research_capability(case_dir),
        ],
    )
