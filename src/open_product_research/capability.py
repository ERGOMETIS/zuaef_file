"""Native PydanticAI Capability. No second agent loop or router."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .media import find_product_images, save_product_image

INSTRUCTIONS = """\
You own one client's product- and competitor-research result. Write a report the client can use.

WORK SEQUENCE
1. Read input.md and clarify the subject, decision, market, year and exact products.
2. Write a concise provisional report.md EARLY. Research can improve it; never wait until
   every possible source has been searched before writing a useful result.
3. Search the web and READ decisive pages. A search snippet alone is not page evidence.
   Check official product/configuration sites first; use dealer and reviews for gaps.
4. Create evidence.md with direct URLs, visit date, exact claim, model/version/market and
   a page locator (heading, passage or image caption). Preserve conflicting values.
5. Write a catalog.md table when multiple SKUs matter. Keep family, SKU, region and year distinct.
   UNKNOWN is better than borrowing details from a sibling model.
6. Discover genuine product photographs from inspected product pages, use the image tools,
   and insert them into report.md as ![model name](assets/filename.jpg).
   Download success does NOT prove that a photo belongs to the named SKU. Cross-check the
   original page and visible model, version, color and generation before using it.
7. Near each photo, present a compact table: market price/currency/date, motor, torque,
   battery Wh, transmission, brakes, speed class, product version. Put 'not confirmed'
   on any missing field instead of inventing figures.
8. Compare relevant competing products and synthesize OEM/ODM opportunities. If factory
   capabilities, BOM, certifications or commercial terms are absent, explicitly decline
   to promise manufacturing feasibility, MOQ, FOB or margin.
9. Make ONE decision (FOLLOW / HOLD_FOR_EVIDENCE / DO_NOT_FOLLOW), give up to 3 reasons,
   largest uncertainty, and ONE next commercial action.
10. Update report.md, evidence.md and unknowns.md as the research progresses.
    Your report should clearly distinguish fact, proxy, inference and unknown in natural language.

DO NOT treat prices as transactions, ratings as sales, similar frames as a shared OEM,
marketing certification claims as verified certificates, or different market/year variants
as a single SKU. Never invent references, image rights, sales numbers or factory costs.
For unavailable or blocked pages, document the limitation. Partial useful work is better
than an empty run. The client report does not mention agent tooling or internal run checks.
The host renders and visually reviews the final PDF after you save report.md.
"""


def make_product_research_capability(case_dir: str | Path):
    """Instantiate the actual AbstractCapability, importing framework on demand."""
    from pydantic_ai.capabilities import AbstractCapability
    from pydantic_ai import FunctionToolset

    directory = Path(case_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)

    @dataclass
    class ProductResearchCapability(AbstractCapability):
        id: str | None = "open_product_research"

        def get_instructions(self) -> str:
            return INSTRUCTIONS

        def get_toolset(self):
            tools = FunctionToolset()

            @tools.tool_plain
            def inspect_product_images(page_url: str) -> list[dict[str, str]]:
                """Inspect public HTML for actual image URLs. Candidate URLs are not SKU proof."""
                return find_product_images(page_url)

            @tools.tool_plain
            def capture_product_image(image_url: str, source_page: str, sku: str) -> dict[str, str]:
                """Save an inspected, genuine product photo with URL provenance to assets/."""
                return save_product_image(directory, image_url, source_page, sku)

            return tools

    return ProductResearchCapability()
