# Architecture and boundaries

## Intent

A one-agent, outcome-owned research slice. Native PydanticAI calls tools; the product capability contributes decision semantics and image-source tools; the host renders already-written Markdown to PDF.

## What is in scope

- `capability.py`: native `AbstractCapability`; English domain instructions; two image operations.
- `agent.py`: composes official run features and the business capability, without a new loop.
- `media.py`: deterministic HTML image discovery and image byte capture with source metadata.
- `render.py`: deterministic report layout and page-by-page previews.
- `cli.py`: case creation, real Agent execution and rendering.

## What is explicitly out of scope

Case service, profile registry, agent registry, skill installer, graph database, web front-end, all-industry schema, scoring gates, authorization daemon, user management, payments, tool-retry policy, automatic editing of prompts and benchmark harness.

## Identity discipline

An image byte hash proves what was saved, not which model it depicts. A model name attached to a file is an **asserted research label**. Identity needs a source page with matching SKU/model-year/market, plus human review for customer publication.

## Future changes

A new tool should address one reproduced failure in an actual client report. For distribution as a teaching resource, include runnable examples but do not bundle copyrighted brand pictures or completed client reports without rights.
