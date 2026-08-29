"""Legal state transitions for the four entity types Airtable tracks.

These graphs are the single source of truth for "is this transition
allowed" -- the orchestrator, the QC agent, and any human tooling should
all route status changes through here rather than writing a Status field
directly, so an illegal jump (e.g. IDEA -> PUBLISHED) is rejected before
it ever reaches Airtable.

IMPORTANT -- live data-integrity note (found 2026-08-29):
The Calendar table's live "Status" singleSelect field in Airtable has a
bug: "AWAITING_APPROVAL" is currently split into two separate choices,
"AWAITING" and "APPROVAL", plus a handful of stray blank-name choices
across Status/Content Type/Content Pillar. The Airtable MCP connector
available to this project has no delete-choice capability, so this
could not be fixed programmatically. CONTENT_STATES below uses the
correct single "AWAITING_APPROVAL" value (matching both the Priority-2
spec and the routine docs' own prose). Until the Airtable field is
fixed by hand, a live write of "AWAITING_APPROVAL" will either be
rejected by Airtable or (with typecast=True) silently create a 14th
stray choice -- see memory.py's `check_data_integrity` for the runtime
guard against this.
"""
from __future__ import annotations

from typing import Optional


class IllegalTransition(ValueError):
    def __init__(self, entity: str, current: str, target: str):
        super().__init__(
            f"Illegal {entity} transition: {current!r} -> {target!r}"
        )
        self.entity = entity
        self.current = current
        self.target = target


# Ordered pipeline. Order matters only for `is_forward`; the graph below
# is what actually gates legality (a status can only move to states its
# entry lists, terminal states have no entries).
CONTENT_STATES = [
    "IDEA",
    "RESEARCH",
    "SCRIPT",
    "PRODUCTION",
    "REVIEW",
    "AWAITING_APPROVAL",
    "APPROVED",
    "SCHEDULED",
    "PUBLISHED",
    "ANALYZING",
    "REPURPOSED",
]

CONTENT_TRANSITIONS: dict[str, list[str]] = {
    "IDEA": ["RESEARCH"],
    "RESEARCH": ["SCRIPT", "IDEA"],  # IDEA: content-strategy can bounce a bad pairing back
    "SCRIPT": ["PRODUCTION", "SCRIPT"],  # QC gate can leave it in SCRIPT with fix notes (no-op edge, see note below)
    "PRODUCTION": ["REVIEW", "PRODUCTION"],  # post-production-qc can leave it in PRODUCTION (missing asset)
    "REVIEW": ["AWAITING_APPROVAL", "PRODUCTION"],  # full QC pass can bounce back to PRODUCTION on failure
    "AWAITING_APPROVAL": ["APPROVED", "PRODUCTION"],  # owner rejects -> back for rework
    "APPROVED": ["SCHEDULED"],
    "SCHEDULED": ["PUBLISHED"],
    "PUBLISHED": ["ANALYZING"],
    "ANALYZING": ["REPURPOSED", "ANALYZING"],  # can stay under ongoing analysis
    "REPURPOSED": [],
}

LEAD_STATES = ["LEAD", "CONTACTED", "PROPOSAL", "WON", "LOST"]

LEAD_TRANSITIONS: dict[str, list[str]] = {
    "LEAD": ["CONTACTED", "LOST"],
    "CONTACTED": ["PROPOSAL", "LOST"],
    "PROPOSAL": ["WON", "LOST"],
    "WON": [],
    "LOST": [],
}

APPROVAL_STATES = ["PENDING", "APPROVED", "REJECTED"]

APPROVAL_TRANSITIONS: dict[str, list[str]] = {
    "PENDING": ["APPROVED", "REJECTED"],
    "APPROVED": [],
    "REJECTED": [],
}

EXPERIMENT_STATES = ["PLANNED", "RUNNING", "COMPLETE"]

EXPERIMENT_TRANSITIONS: dict[str, list[str]] = {
    "PLANNED": ["RUNNING"],
    "RUNNING": ["COMPLETE"],
    "COMPLETE": [],
}

_GRAPHS: dict[str, dict[str, list[str]]] = {
    "content": CONTENT_TRANSITIONS,
    "lead": LEAD_TRANSITIONS,
    "approval": APPROVAL_TRANSITIONS,
    "experiment": EXPERIMENT_TRANSITIONS,
}

_ORDERED_STATES: dict[str, list[str]] = {
    "content": CONTENT_STATES,
    "lead": LEAD_STATES,
    "approval": APPROVAL_STATES,
    "experiment": EXPERIMENT_STATES,
}


def known_states(entity: str) -> list[str]:
    return list(_ORDERED_STATES[entity])


def is_legal(entity: str, current: str, target: str) -> bool:
    """True if `current -> target` is an allowed edge for this entity type."""
    graph = _GRAPHS[entity]
    if current not in graph:
        return False
    return target in graph[current]


def validate_transition(entity: str, current: str, target: str) -> None:
    """Raise IllegalTransition if the move isn't allowed. No-op otherwise."""
    if current == target:
        return
    if not is_legal(entity, current, target):
        raise IllegalTransition(entity, current, target)


def is_forward(entity: str, current: str, target: str) -> Optional[bool]:
    """True/False if both states are on the canonical linear pipeline,
    None if either state is a side-branch (e.g. content REVIEW->PRODUCTION
    rework, lead ...->LOST) and "forward" isn't well-defined."""
    order = _ORDERED_STATES[entity]
    if current not in order or target not in order:
        return None
    return order.index(target) > order.index(current)
