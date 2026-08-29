"""Revenue-first prioritization.

Views/followers/likes are not the objective; profitable audience growth
is. That ordering is encoded directly as category weights: a candidate
action tagged REVENUE always outranks one tagged EFFICIENCY, no matter
how many efficiency items are queued up. Within a category, more urgent
or higher-volume items score a little higher, but categories never
invert -- a pile of low-value busywork should never outscore a single
real revenue-attribution task.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from orchestrator.memory import BusinessAssessment, BusinessState
from orchestrator.schema import ApprovalRequirement, Task


class Category(str, Enum):
    REVENUE = "revenue_potential"
    LEADS = "lead_potential"
    GROWTH = "audience_growth"
    QUALITY = "audience_quality"
    RETENTION = "retention"
    BRAND = "brand_value"
    EFFICIENCY = "efficiency"


# Strictly descending. A category boundary is never crossed by urgency
# bonuses (each category's band is 100 points wide, bonuses cap at 20).
WEIGHTS: dict[Category, float] = {
    Category.REVENUE: 700,
    Category.LEADS: 600,
    Category.GROWTH: 500,
    Category.QUALITY: 400,
    Category.RETENTION: 300,
    Category.BRAND: 200,
    Category.EFFICIENCY: 100,
}

_URGENCY_CAP = 20.0


@dataclass
class Candidate:
    task: Task
    category: Category
    reason: str
    urgency: float = 0.0  # 0..1, scaled into the category's band at score time

    def score(self) -> float:
        return WEIGHTS[self.category] + min(self.urgency, 1.0) * _URGENCY_CAP


def identify_candidate_actions(
    state: BusinessState, assessment: BusinessAssessment
) -> list[Candidate]:
    candidates: list[Candidate] = []
    candidates += _revenue_candidates(state, assessment)
    candidates += _lead_candidates(assessment)
    candidates += _opportunity_candidates(state)
    candidates += _research_cadence_candidate(state)
    candidates += _pipeline_candidates(state)
    candidates += _analytics_candidate(state, assessment)
    candidates += _growth_candidate(state, assessment)
    return candidates


def prioritize(candidates: list[Candidate]) -> list[Task]:
    ranked = sorted(candidates, key=lambda c: c.score(), reverse=True)
    tasks: list[Task] = []
    for c in ranked:
        c.task.priority_score = c.score()
        c.task.priority_reason = f"[{c.category.value}] {c.reason}"
        tasks.append(c.task)
    return tasks


# ---- candidate generators -------------------------------------------------

def _revenue_candidates(state: BusinessState, assessment: BusinessAssessment) -> list[Candidate]:
    if "revenue-review" in state.daily_ops_log_today:
        return []
    unattributed = [r for r in state.revenue if not r.get("content_attribution")]
    if not state.revenue:
        return []
    urgency = min(len(unattributed) / 5.0, 1.0)
    return [Candidate(
        task=Task(
            agent="revenue",
            objective="Review recent revenue rows and attribute them to content/source.",
            inputs={"revenue_rows": state.revenue, "unattributed_count": len(unattributed)},
            constraints=["Do not invent attribution; leave unclear rows unattributed with a note."],
            expected_output="Revenue rows updated with Notes; Weekly Learnings entry if a pattern is clear.",
            approval_requirement=ApprovalRequirement.NONE,
        ),
        category=Category.REVENUE,
        reason=f"{len(state.revenue)} revenue row(s) to review, {len(unattributed)} unattributed",
        urgency=urgency,
    )]


# Matches Notion "Business Strategy"'s single-workflow price anchor
# (script-writer.md: ₹40,000-80,000). A proposal at or above this line is
# a high-ticket service sale -- per the autonomy rules, that always
# requires explicit owner approval before Claude proceeds, regardless of
# how routine everything else about the lead has been.
HIGH_TICKET_THRESHOLD_INR = 40_000


def _lead_candidates(assessment: BusinessAssessment) -> list[Candidate]:
    if not assessment.generated_leads:
        return []
    candidates: list[Candidate] = []

    high_ticket = [
        l for l in assessment.generated_leads
        if l.get("status") == "Proposal" and (l.get("value") or 0) >= HIGH_TICKET_THRESHOLD_INR
    ]
    if high_ticket:
        candidates.append(Candidate(
            task=Task(
                agent="community",
                objective="Prepare to close a high-ticket proposal -- owner sign-off required before proceeding.",
                inputs={"leads": high_ticket},
                constraints=["Do not send anything or commit to terms without explicit owner approval."],
                expected_output="A drafted next step, held for owner approval.",
                approval_requirement=ApprovalRequirement.REQUIRED,
            ),
            category=Category.LEADS,
            reason=f"{len(high_ticket)} high-ticket proposal(s) (>= INR {HIGH_TICKET_THRESHOLD_INR:,})",
            urgency=1.0,
        ))

    stale = [
        l for l in assessment.generated_leads
        if l.get("status") == "Lead" and l.get("days_since_first_contact", 0) >= 2
    ]
    if stale:
        candidates.append(Candidate(
            task=Task(
                agent="community",
                objective="Follow up on leads sitting in LEAD status for 2+ days.",
                inputs={"leads": stale},
                constraints=["Low-risk, templated follow-up only; escalate anything ambiguous."],
                expected_output="Leads moved to CONTACTED with a logged touchpoint, or escalated.",
                approval_requirement=ApprovalRequirement.NOTIFY,
            ),
            category=Category.LEADS,
            reason=f"{len(stale)} lead(s) stalled in LEAD status 2+ days",
            urgency=min(len(stale) / 3.0, 1.0),
        ))

    return candidates


def _opportunity_candidates(state: BusinessState) -> list[Candidate]:
    """Two-phase intake for opportunities that entered the system ad hoc
    (event-driven), as opposed to the scheduled morning-research scan
    which qualifies and writes Calendar IDEA records in one routine pass.

    Phase 1 (raw): Research Agent evaluates whether it's real -- same bar
    as morning-research's "clear, specific who/why" qualification.
    Phase 2 (qualified): Content Strategy Agent decides platform/format/
    priority and commits it to the Calendar pipeline.
    """
    raw = [o for o in state.opportunities if not o.get("qualified")]
    qualified = [o for o in state.opportunities if o.get("qualified")]
    candidates: list[Candidate] = []

    if raw:
        candidates.append(Candidate(
            task=Task(
                agent="research",
                objective="Evaluate newly-surfaced opportunities for validity before committing pipeline capacity.",
                inputs={"opportunities": raw},
                constraints=["Reject vague ideas rather than forcing a quota, same bar as the daily scan."],
                expected_output="Each opportunity marked qualified with reasoning, or rejected.",
                approval_requirement=ApprovalRequirement.NONE,
            ),
            category=Category.GROWTH,
            reason=f"{len(raw)} raw opportunit(y/ies) awaiting research evaluation",
            urgency=min(len(raw) / 3.0, 1.0),
        ))

    if qualified:
        candidates.append(Candidate(
            task=Task(
                agent="content_strategy",
                objective="Decide platform/format/priority and commit qualified opportunities to the Calendar pipeline.",
                inputs={"opportunities": qualified},
                constraints=["Advance at most 2 ideas per pacing rule."],
                expected_output="Qualified opportunities written to Calendar (IDEA or RESEARCH) with reasoning.",
                approval_requirement=ApprovalRequirement.NONE,
            ),
            category=Category.GROWTH,
            reason=f"{len(qualified)} qualified opportunit(y/ies) awaiting a Calendar commit decision",
            urgency=min(len(qualified) / 3.0, 1.0),
        ))

    return candidates


def _research_cadence_candidate(state: BusinessState) -> list[Candidate]:
    if "morning-research" in state.daily_ops_log_today:
        return []
    return [Candidate(
        task=Task(
            agent="research",
            objective="Run the daily competitor/trend scan for new content opportunities.",
            inputs={},
            constraints=["Reject vague ideas rather than forcing a quota."],
            expected_output="0-7 new opportunities, or an explicit 'nothing qualified' note.",
            approval_requirement=ApprovalRequirement.NONE,
        ),
        category=Category.GROWTH,
        reason="daily research scan has not run yet today",
        urgency=0.3,
    )]


_PIPELINE_STAGE_TO_TASK: dict[str, tuple[str, str, dict[str, Any], Category]] = {
    "IDEA": ("content_strategy", "Prioritize IDEA records for advancement to RESEARCH.",
             {}, Category.GROWTH),
    "RESEARCH": ("script", "Write scripts for the prioritized RESEARCH records.",
                 {}, Category.GROWTH),
    "SCRIPT": ("qc", "Run the script QC gate (fabrication/voice/structure) toward PRODUCTION.",
               {"gate": "script"}, Category.QUALITY),
    "PRODUCTION": ("qc", "Run the post-production completeness gate toward REVIEW.",
                   {"gate": "post_production"}, Category.QUALITY),
    "REVIEW": ("qc", "Run the full QC pass (brand, copyright, claims, monetization) toward AWAITING_APPROVAL.",
               {"gate": "full_qc"}, Category.QUALITY),
}


def _pipeline_candidates(state: BusinessState) -> list[Candidate]:
    candidates: list[Candidate] = []
    for stage, (agent, objective, extra_inputs, category) in _PIPELINE_STAGE_TO_TASK.items():
        records = state.calendar_by_status(stage)
        if stage == "PRODUCTION":
            # Post-production QC needs a produced asset to check; records
            # still waiting on the human filming/editing step are not
            # actionable by any agent yet -- that's correct, not a bug.
            records = [r for r in records if r.get("asset_link")]
        if not records:
            continue
        candidates.append(Candidate(
            task=Task(
                agent=agent,
                objective=objective,
                inputs={"calendar_records": records, **extra_inputs},
                constraints=[],
                expected_output=f"{stage} records advanced or explicitly held with notes.",
                approval_requirement=ApprovalRequirement.NONE,
            ),
            category=category,
            reason=f"{len(records)} Calendar record(s) in {stage}",
            urgency=min(len(records) / 4.0, 1.0),
        ))
    return candidates


def _analytics_candidate(state: BusinessState, assessment: BusinessAssessment) -> list[Candidate]:
    if "evening-analytics" in state.daily_ops_log_today:
        return []
    if not assessment.recently_published and not state.analytics:
        return []
    urgency = min(len(assessment.performed_poorly) / 3.0, 1.0)
    return [Candidate(
        task=Task(
            agent="analytics",
            objective="Refresh performance data for recently published content.",
            inputs={"published": assessment.recently_published},
            constraints=[],
            expected_output="Analytics rows updated; standout over/under performers noted.",
            approval_requirement=ApprovalRequirement.NONE,
        ),
        category=Category.RETENTION,
        reason=f"{len(assessment.recently_published)} published record(s) may have fresh performance data",
        urgency=urgency,
    )]


def _growth_candidate(state: BusinessState, assessment: BusinessAssessment) -> list[Candidate]:
    if "weekly-growth-review" in state.daily_ops_log_today:
        return []
    signal = assessment.performed_well or assessment.performed_poorly or assessment.experiments_running
    if not signal:
        return []
    return [Candidate(
        task=Task(
            agent="growth",
            objective="Synthesize recent performance/revenue/experiment signal into a recommendation.",
            inputs={
                "performed_well": assessment.performed_well,
                "performed_poorly": assessment.performed_poorly,
                "experiments_running": assessment.experiments_running,
            },
            constraints=["Major strategic changes require explicit owner approval before acting."],
            expected_output="A Weekly Learnings entry, and/or a new Experiments row.",
            approval_requirement=ApprovalRequirement.NOTIFY,
        ),
        category=Category.GROWTH,
        reason="performance/experiment signal available for synthesis",
        urgency=0.4,
    )]
