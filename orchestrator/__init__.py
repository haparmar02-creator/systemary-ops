"""Central orchestration layer for Systemary.

Claude acts as the central autonomous orchestrator (CEO); specialized
agents (Research, Content Strategy, Script, Production, QC, Publishing,
Community, Analytics, Revenue, Growth) are workers; Airtable is
operational state; Notion is long-term business memory; Drive is asset
storage. This package holds the deterministic parts of that loop --
schemas, the state machine, the priority engine, the agent registry, and
the cycle driver -- so they can be tested and reasoned about without a
live LLM call or live credentials.

What this package deliberately does NOT do: it holds no Airtable/Notion/
Drive credentials and makes no network calls. "Read state" means turning
an already-fetched snapshot (typically produced by Claude via MCP tools)
into a BusinessState; "execute agent" is a caller-supplied function --
in production that's Claude performing the specialized-agent role, in
tests/dry-run it's a deterministic simulator (see simulate.py).
"""
