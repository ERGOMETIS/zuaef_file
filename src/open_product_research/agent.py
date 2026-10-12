"""Use upstream Pydantic AI/Harness to run one research agent."""
from __future__ import annotations

from pathlib import Path

from .capability import make_product_research_capability
from .web_tools import make_local_fetch, make_local_search


def build_agent(model: str, case_dir: str | Path):
    """No subagents, own approval stack, dispatcher or checkpoint implementation."""
    from pydantic_ai import Agent
    from pydantic_ai.capabilities import LocalWorkspace, WebFetch, WebSearch
    from pydantic_ai_harness import FileSystem

    case_dir = Path(case_dir).expanduser().resolve()
    case_dir.mkdir(parents=True, exist_ok=True)
    return Agent(
        model,
        name="product-research",
        capabilities=[
            LocalWorkspace(str(case_dir)),
            FileSystem(tools=["read_file", "write_file", "edit_file", "list_directory"],
                       content_hashes=False, max_retries=5),
            WebSearch(local=make_local_search()),
            WebFetch(local=make_local_fetch(case_dir=case_dir)),
            make_product_research_capability(case_dir),
        ],
    )
