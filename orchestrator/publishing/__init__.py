"""Publishing execution infrastructure (Priority 3A: YouTube first).

    ORCHESTRATOR -> PUBLISHING AGENT -> YOUTUBE ADAPTER -> YouTube API

`publishing_agent.py` is the only module that knows about Calendar
records/Airtable field names. `youtube_adapter.py` is the only module
that knows about YouTube's request shapes. Neither the orchestrator nor
the adapter reaches across that boundary -- which is what lets Instagram
show up later as a sibling adapter (`instagram_adapter.py`) behind the
same publishing agent, without touching this package's YouTube code.

Nothing in this package is wired into the orchestrator's autonomous
dispatch loop yet (`agents.AGENTS["publishing"].enabled` is still
False) -- per Priority 3A, publishing only runs when explicitly
invoked (CLI/tests), never as something the orchestrator decides to do
on its own cycle.
"""
