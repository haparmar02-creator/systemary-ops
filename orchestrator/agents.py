"""The agent registry: who the workers are, what they touch, and how
much rope they get.

An "agent" here is a role, not a process -- in production, Claude
performs the role (directly, or via the Agent tool as a subagent),
following the mapped routine file's instructions where one exists.
`enabled=False` means the orchestrator must never dispatch a Task to
that agent yet, regardless of what the priority engine would otherwise
pick -- currently just Publishing, per explicit instruction not to build
YouTube/Instagram publishing in this phase.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from orchestrator.schema import ApprovalRequirement


@dataclass(frozen=True)
class AgentSpec:
    name: str
    purpose: str
    reads: tuple[str, ...]
    writes: tuple[str, ...]
    default_approval: ApprovalRequirement
    timeout_seconds: int
    max_retries: int
    routine_file: Optional[str]   # existing routines/*.md this agent role maps to, if any
    enabled: bool = True


AGENTS: dict[str, AgentSpec] = {
    "research": AgentSpec(
        name="research",
        purpose="Scan competitors and trends; surface content opportunities.",
        reads=("Notion:Content Pillars", "Notion:Business Strategy", "Airtable:Competitors",
               "Airtable:Analytics", "web search"),
        writes=("Airtable:Competitors", "opportunities (pre-Calendar)"),
        default_approval=ApprovalRequirement.NONE,
        timeout_seconds=900,
        max_retries=1,
        routine_file="routines/morning-research.md",
    ),
    "content_strategy": AgentSpec(
        name="content_strategy",
        purpose="Decide what advances from IDEA to RESEARCH, in what order, by when.",
        reads=("Airtable:Calendar[IDEA]", "Notion:Content Pillars", "Notion:Business Strategy"),
        writes=("Airtable:Calendar.status", "Airtable:Calendar.scheduled_time"),
        default_approval=ApprovalRequirement.NONE,
        timeout_seconds=600,
        max_retries=1,
        routine_file="routines/content-strategy.md",
    ),
    "script": AgentSpec(
        name="script",
        purpose="Write full scripts/captions/CTAs for RESEARCH records; advance to SCRIPT.",
        reads=("Airtable:Calendar[RESEARCH]", "Notion:Brand Identity", "Notion:Tone & Voice",
               "Notion:Case Studies", "Notion:Successful Hooks"),
        writes=("Drive:/Channel-Ops/01-Scripts/", "Airtable:Calendar.script_link",
                "Airtable:Calendar.status"),
        default_approval=ApprovalRequirement.NONE,
        timeout_seconds=1200,
        max_retries=1,
        routine_file="routines/script-writer.md",
    ),
    "production": AgentSpec(
        name="production",
        purpose=("Coordinate voice/visuals/video/captions/thumbnail into a final asset. "
                  "Currently a human-in-the-loop step (filming/editing); this agent role "
                  "exists in the registry for when that becomes automatable, but has no "
                  "routine file yet -- see docs/orchestrator/ARCHITECTURE.md."),
        reads=("Airtable:Calendar[SCRIPT->PRODUCTION gate output]", "Drive:/Channel-Ops/02-Raw/"),
        writes=("Drive:/Channel-Ops/03-Produced/", "Airtable:Calendar.asset_link",
                "Airtable:Calendar.status"),
        default_approval=ApprovalRequirement.NONE,
        timeout_seconds=1800,
        max_retries=0,
        routine_file=None,
        enabled=False,  # no automated production pipeline exists; human does this today
    ),
    "qc": AgentSpec(
        name="qc",
        purpose=("Gate content quality at two points: SCRIPT->PRODUCTION (script QC: "
                  "fabrication/voice/structure) and PRODUCTION->REVIEW (mechanical "
                  "completeness), plus the full REVIEW->AWAITING_APPROVAL pass (brand, "
                  "copyright, claims, platform requirements, monetization alignment)."),
        reads=("Airtable:Calendar[SCRIPT|PRODUCTION|REVIEW]", "Notion:Brand Identity",
               "Notion:Tone & Voice", "Drive:/Channel-Ops/03-Produced/"),
        writes=("Airtable:Calendar.status", "Airtable:Calendar.notes"),
        default_approval=ApprovalRequirement.NONE,
        timeout_seconds=900,
        max_retries=1,
        routine_file="routines/production-qc.md",  # + post-production-qc.md + content-qc.md
    ),
    "publishing": AgentSpec(
        name="publishing",
        purpose="Publish to YouTube/Instagram, schedule, set metadata/thumbnails, record Published URL.",
        reads=("Airtable:Calendar[APPROVED]",),
        writes=("Airtable:Calendar.published_url", "Airtable:Calendar.status"),
        default_approval=ApprovalRequirement.REQUIRED,  # posting publicly is never autonomous by default
        timeout_seconds=600,
        max_retries=0,
        routine_file=None,
        enabled=False,  # explicitly out of scope for this phase
    ),
    "community": AgentSpec(
        name="community",
        purpose=("Classify and respond to comments/DMs where API access permits; follow up on "
                  "Airtable leads (via Gmail, which is wired); escalate risk. Comment/DM platform "
                  "APIs are NOT yet wired -- only the Gmail-based lead-follow-up surface is live "
                  "today; anything requiring live comment/DM access must self-escalate rather than "
                  "silently no-op."),
        reads=("Airtable:Clients/Leads", "platform comments/DMs (not yet wired)", "Notion:Tone & Voice"),
        writes=("Airtable:Clients/Leads", "Gmail replies (low-risk only)"),
        default_approval=ApprovalRequirement.NOTIFY,  # low-risk replies proceed, then owner is told
        timeout_seconds=300,
        max_retries=2,
        routine_file=None,
    ),
    "analytics": AgentSpec(
        name="analytics",
        purpose="Analyze performance, retention, CTR, engagement, audience growth, platform differences.",
        reads=("Airtable:Analytics", "Airtable:Calendar[PUBLISHED]"),
        writes=("Airtable:Analytics", "Notion:Weekly Learnings"),
        default_approval=ApprovalRequirement.NONE,
        timeout_seconds=600,
        max_retries=1,
        routine_file=None,  # not yet built as a scheduled routine; see ARCHITECTURE.md
    ),
    "revenue": AgentSpec(
        name="revenue",
        purpose="Analyze and attribute revenue across affiliate/product/service/sponsorship/AdSense.",
        reads=("Airtable:Revenue", "Airtable:Calendar (Content Attribution)"),
        writes=("Airtable:Revenue.notes", "Notion:Weekly Learnings"),
        default_approval=ApprovalRequirement.NONE,
        timeout_seconds=600,
        max_retries=1,
        routine_file=None,
    ),
    "growth": AgentSpec(
        name="growth",
        purpose="Synthesize research+analytics+revenue into strategic recommendations/experiments.",
        reads=("Airtable:Analytics", "Airtable:Revenue", "Airtable:Experiments",
               "Notion:Weekly Learnings", "Notion:Business Strategy"),
        writes=("Airtable:Experiments", "Notion:Business Strategy (proposed changes only)"),
        default_approval=ApprovalRequirement.NOTIFY,
        timeout_seconds=900,
        max_retries=1,
        routine_file=None,
    ),
}

# Major strategic changes -- growth agent's proposals that would materially
# affect positioning, pricing, or pillar mix -- always require explicit
# approval regardless of the agent's default, per the autonomy rules.
MAJOR_STRATEGY_CHANGE_REQUIRES_APPROVAL = ApprovalRequirement.REQUIRED


def get(name: str) -> AgentSpec:
    if name not in AGENTS:
        raise KeyError(f"no such agent: {name!r}")
    return AGENTS[name]


def enabled_agents() -> dict[str, AgentSpec]:
    return {k: v for k, v in AGENTS.items() if v.enabled}
