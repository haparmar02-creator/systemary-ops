"""Business state: what the orchestrator reads, and what it means.

This module defines two things:

1. MEMORY_READS -- a declarative spec of exactly what must be fetched
   from Airtable / Notion / Drive on every cycle. It has no I/O of its
   own; whatever fetches state (today: Claude, via the MCP connectors
   already attached to this project) should read this spec and pull
   exactly these things, then build a BusinessState from the results.
2. BusinessState / BusinessAssessment -- the typed snapshot the rest of
   the orchestrator reasons over, and the pure function that turns a
   snapshot into answers to the 14 standing business-state questions.

No network calls, no credentials, nothing external. Feed it a dict (a
fixture in tests, a real Airtable/Notion snapshot in production) and it
tells you what's true right now.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from orchestrator.state_machine import known_states

MEMORY_READS: dict[str, dict[str, list[str]]] = {
    "airtable": {
        "base": ["Content Ops (apprrFf0k0HOgS4EX)"],
        "tables": [
            "Calendar",       # the content pipeline -- read in full every cycle
            "Analytics",      # performance data since the last cycle
            "Competitors",    # only rows updated since last morning-research pass
            "Experiments",    # RUNNING and recently-COMPLETE rows
            "Approvals",      # PENDING rows -- these are the human-in-the-loop queue
            "Revenue",        # rows since last revenue review
            "Clients/Leads",  # rows not in a terminal state (WON/LOST)
        ],
    },
    "notion": {
        "space": ["Brand Memory & Business Ops"],
        "pages": [
            "Brand Identity",       # QC agent + script agent voice/claims baseline
            "Tone & Voice",         # QC agent + script agent
            "Content Pillars",      # research + content-strategy agent
            "Business Strategy",    # sets `objective`; growth agent
            "Successful Hooks",     # script agent, research agent
            "Case Studies",         # script agent (What I'd Charge pieces), revenue agent
            "Weekly Learnings",     # growth agent input, written by growth agent
            "Daily Ops Log",        # every routine appends here; orchestrator reads recent
                                     # entries to avoid re-doing work already logged today
        ],
    },
    "drive": {
        "folders": [
            "/Channel-Ops/01-Scripts/",
            "/Channel-Ops/02-Raw/",           # production agent inputs
            "/Channel-Ops/03-Produced/",      # QC agent + publishing agent inputs
            "/Channel-Ops/04-Thumbnails/",
            "/Channel-Ops/05-Published-Archive/",
            "/Channel-Ops/Brand-Assets/",
            "/Channel-Ops/Client-Deliverables/",
        ],
    },
}


@dataclass
class BusinessState:
    """A single point-in-time snapshot. Build one per cycle."""

    as_of: str
    objective: str = ""
    calendar: list[dict[str, Any]] = field(default_factory=list)
    competitors: list[dict[str, Any]] = field(default_factory=list)
    analytics: list[dict[str, Any]] = field(default_factory=list)
    revenue: list[dict[str, Any]] = field(default_factory=list)
    leads: list[dict[str, Any]] = field(default_factory=list)
    experiments: list[dict[str, Any]] = field(default_factory=list)
    approvals: list[dict[str, Any]] = field(default_factory=list)
    opportunities: list[dict[str, Any]] = field(default_factory=list)  # research findings, pre-IDEA
    daily_ops_log_today: list[str] = field(default_factory=list)      # routine names already run today

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "BusinessState":
        known = {f for f in BusinessState.__dataclass_fields__}
        return BusinessState(**{k: v for k, v in d.items() if k in known})

    def calendar_by_status(self, status: str) -> list[dict[str, Any]]:
        return [r for r in self.calendar if r.get("status") == status]


@dataclass
class BusinessAssessment:
    """Direct answers to the 14 standing orchestrator questions."""

    objective: str
    today_priorities: list[str]
    in_production: list[dict[str, Any]]
    scheduled: list[dict[str, Any]]
    needs_approval: list[dict[str, Any]]
    recently_published: list[dict[str, Any]]
    performed_well: list[dict[str, Any]]
    performed_poorly: list[dict[str, Any]]
    generated_leads: list[dict[str, Any]]
    generated_revenue: list[dict[str, Any]]
    experiments_running: list[dict[str, Any]]
    opportunities: list[dict[str, Any]]
    blocked: list[dict[str, Any]]
    data_integrity_warnings: list[str]


# A record counts as "performing well" if it beats this retention/CTR bar,
# "poorly" if it falls under the low bar. Tunable; not a business secret,
# just a starting heuristic until the Analytics Agent has enough history
# to set its own thresholds per content pillar.
RETENTION_WELL = 0.45
RETENTION_POORLY = 0.20
CTR_WELL = 0.06
CTR_POORLY = 0.02


def assess(state: BusinessState) -> BusinessAssessment:
    in_production = state.calendar_by_status("PRODUCTION")
    scheduled = state.calendar_by_status("SCHEDULED")
    needs_approval = [
        a for a in state.approvals if a.get("status") == "Pending"
    ]
    recently_published = state.calendar_by_status("PUBLISHED")

    performed_well = [
        a for a in state.analytics
        if a.get("retention", 0) >= RETENTION_WELL or a.get("ctr", 0) >= CTR_WELL
    ]
    performed_poorly = [
        a for a in state.analytics
        if a.get("retention", 1) <= RETENTION_POORLY or a.get("ctr", 1) <= CTR_POORLY
    ]

    generated_leads = [
        lead for lead in state.leads if lead.get("status") not in ("Won", "Lost")
    ]
    generated_revenue = list(state.revenue)
    experiments_running = [
        e for e in state.experiments if e.get("status") == "RUNNING"
    ]

    blocked, warnings = _find_blocked_and_warnings(state)

    priorities = _today_priorities(state, needs_approval, blocked)

    return BusinessAssessment(
        objective=state.objective,
        today_priorities=priorities,
        in_production=in_production,
        scheduled=scheduled,
        needs_approval=needs_approval,
        recently_published=recently_published,
        performed_well=performed_well,
        performed_poorly=performed_poorly,
        generated_leads=generated_leads,
        generated_revenue=generated_revenue,
        experiments_running=experiments_running,
        opportunities=list(state.opportunities),
        blocked=blocked,
        data_integrity_warnings=warnings,
    )


def _find_blocked_and_warnings(
    state: BusinessState,
) -> tuple[list[dict[str, Any]], list[str]]:
    blocked: list[dict[str, Any]] = []
    warnings: list[str] = []
    valid_content_states = set(known_states("content"))

    for record in state.calendar:
        status = record.get("status")
        if status not in valid_content_states:
            blocked.append({**record, "block_reason": f"unrecognized status {status!r}"})
            if status in ("AWAITING", "APPROVAL"):
                warnings.append(
                    f"record {record.get('id')} has status {status!r} -- this is the "
                    "known Calendar.Status split-choice bug (AWAITING_APPROVAL was split "
                    "into two choices). Needs a manual Airtable fix; see state_machine.py."
                )
            else:
                warnings.append(
                    f"record {record.get('id')} has unrecognized status {status!r}"
                )
        if record.get("script_link") in (None, "") and status not in ("IDEA", "RESEARCH"):
            blocked.append({**record, "block_reason": "missing Script Link past SCRIPT stage"})

    for approval in state.approvals:
        if approval.get("status") == "Pending" and approval.get("age_hours", 0) > 48:
            blocked.append({**approval, "block_reason": "pending approval > 48h, needs owner attention"})

    return blocked, warnings


def _today_priorities(
    state: BusinessState,
    needs_approval: list[dict[str, Any]],
    blocked: list[dict[str, Any]],
) -> list[str]:
    priorities: list[str] = []
    if blocked:
        priorities.append(f"resolve {len(blocked)} blocked item(s)")
    if needs_approval:
        priorities.append(f"surface {len(needs_approval)} pending approval(s) to owner")
    if state.calendar_by_status("IDEA"):
        priorities.append("run content-strategy pass over new IDEA records")
    if state.calendar_by_status("RESEARCH"):
        priorities.append("script the prioritized RESEARCH records")
    if state.calendar_by_status("SCRIPT"):
        priorities.append("QC-gate SCRIPT records toward PRODUCTION")
    if state.calendar_by_status("PRODUCTION"):
        priorities.append("QC-gate produced assets toward REVIEW")
    if state.opportunities:
        priorities.append(f"evaluate {len(state.opportunities)} open research opportunit(y/ies)")
    return priorities
