"""The central decision loop:

    READ STATE -> ASSESS BUSINESS -> IDENTIFY OPPORTUNITIES/PROBLEMS ->
    PRIORITIZE -> SELECT AGENT -> EXECUTE -> VERIFY RESULT ->
    UPDATE STATE -> REASSESS -> CONTINUE

`run_cycle` performs one full pass of that loop against a BusinessState.
`run_until_idle` drives repeated cycles, feeding each cycle's effect on
state into the next one, until nothing actionable is left -- this is
what lets a single new opportunity cascade through
research -> content_strategy -> script -> qc without a human re-invoking
the loop by hand.

READ STATE happens before this module is ever called (whatever fetched
the snapshot -- Claude via MCP tools, or a test fixture -- already did
it). EXECUTE is a caller-supplied function: in production that's Claude
performing the agent's role; in tests/dry-run it's simulate.py's
deterministic stub. This module owns everything deterministic in
between: which candidate wins, whether an agent is allowed to run yet,
whether its proposed state transition is legal, and how the result
folds back into state for the next cycle.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional

from orchestrator.agents import get as get_agent
from orchestrator.errors import RetryPolicy, run_with_retry
from orchestrator.memory import BusinessAssessment, BusinessState, assess
from orchestrator.priority import identify_candidate_actions, prioritize
from orchestrator.schema import ApprovalRequirement, Result, Task, TaskStatus
from orchestrator.state_machine import IllegalTransition, known_states, validate_transition

ExecuteFn = Callable[[Task], Result]

_TABLE_TO_STATE_LIST: dict[str, str] = {
    "Calendar": "calendar",
    "Clients/Leads": "leads",
    "Approvals": "approvals",
    "Experiments": "experiments",
    "Revenue": "revenue",
    "Competitors": "competitors",
}

_ENTITY_BY_TABLE: dict[str, str] = {
    "Calendar": "content",
    "Clients/Leads": "lead",
    "Approvals": "approval",
    "Experiments": "experiment",
}

# Airtable field name -> BusinessState record key. Every table's Status
# column maps the same way; content-specific fields are namespaced here
# because different tables reuse names (e.g. "Notes" everywhere).
_FIELD_KEY_MAP: dict[str, str] = {
    "Status": "status",
    "Topic": "topic",
    "Notes": "notes",
    "Platform": "platform",
    "Content Type": "content_type",
    "Content Pillar": "content_pillar",
    "Script Link": "script_link",
    "Asset Link": "asset_link",
    "Scheduled Time": "scheduled_time",
    "Published URL": "published_url",
    "Name": "name",
    "Brief": "brief",
}

_AGENT_TO_LOG_MARKER: dict[str, str] = {
    "research": "morning-research",
    "analytics": "evening-analytics",
    "revenue": "revenue-review",
    "growth": "weekly-growth-review",
}


@dataclass
class CycleReport:
    assessment: BusinessAssessment
    candidates_considered: int
    selected_task: Optional[Task]
    result: Optional[Result]
    skipped_reason: Optional[str] = None
    verification_problems: list[str] = field(default_factory=list)

    @property
    def acted(self) -> bool:
        return self.result is not None and self.selected_task is not None

    def summary(self) -> str:
        if not self.acted:
            return f"idle: {self.skipped_reason}"
        t, r = self.selected_task, self.result
        return (
            f"{t.agent} :: {t.objective} -> {r.status.value} "
            f"(score={t.priority_score:.0f}, {t.priority_reason})"
        )


def run_cycle(
    state: BusinessState,
    execute: ExecuteFn,
    dry_run: bool = True,
) -> CycleReport:
    # ASSESS BUSINESS
    assessment = assess(state)

    # IDENTIFY OPPORTUNITIES / PROBLEMS, then PRIORITIZE
    candidates = identify_candidate_actions(state, assessment)
    ranked = prioritize(candidates)

    # SELECT AGENT: first ranked task whose agent is actually enabled
    selected: Optional[Task] = None
    for task in ranked:
        spec = get_agent(task.agent)
        if spec.enabled:
            selected = task
            break

    if selected is None:
        reason = "nothing actionable" if not ranked else (
            f"{len(ranked)} candidate(s) found but every matching agent is disabled"
        )
        return CycleReport(assessment, len(ranked), None, None, skipped_reason=reason)

    selected.dry_run = dry_run
    spec = get_agent(selected.agent)

    if selected.approval_requirement == ApprovalRequirement.REQUIRED:
        blocked = Result(
            task_id=selected.task_id,
            agent=selected.agent,
            status=TaskStatus.BLOCKED_ON_APPROVAL,
            output={},
            evidence=[],
            errors=[],
            airtable_updates=[],
            next_recommended_action=f"owner approval required before executing: {selected.objective}",
        )
        return CycleReport(assessment, len(ranked), selected, blocked)

    # EXECUTE (with retry/timeout policy)
    result = run_with_retry(selected, execute, RetryPolicy.from_agent_spec(spec))

    # VERIFY RESULT: reject illegal state transitions before they ever
    # reach "update state" -- a bad agent output must never corrupt the
    # pipeline, dry-run or not.
    problems = verify_result(result, state)
    if problems:
        result = Result(
            task_id=result.task_id,
            agent=result.agent,
            status=TaskStatus.FAILED,
            output=result.output,
            evidence=result.evidence,
            errors=[*result.errors, *problems],
            airtable_updates=[],  # nothing gets applied if verification failed
            next_recommended_action=f"human review needed: {selected.agent} proposed an illegal transition",
        )

    # UPDATE STATE (in dry-run this mutates the in-memory snapshot only;
    # `intent.applied` stays False either way -- it only ever flips True
    # when a real, non-dry-run Airtable write actually happens, which
    # this module never performs itself)
    if result.status == TaskStatus.SUCCEEDED:
        apply_result_to_state(state, selected, result)

    return CycleReport(assessment, len(ranked), selected, result, verification_problems=problems)


def run_until_idle(
    state: BusinessState,
    execute: ExecuteFn,
    dry_run: bool = True,
    max_cycles: int = 25,
) -> list[CycleReport]:
    """REASSESS -> CONTINUE, repeatedly, until idle or max_cycles."""
    reports: list[CycleReport] = []
    for _ in range(max_cycles):
        report = run_cycle(state, execute, dry_run=dry_run)
        reports.append(report)
        if not report.acted:
            break
        if report.result and report.result.status not in (TaskStatus.SUCCEEDED,):
            # A failed/blocked/escalated cycle stops the cascade -- don't
            # keep chaining downstream agents on top of a bad result.
            break
    return reports


def verify_result(result: Result, state: BusinessState) -> list[str]:
    problems: list[str] = []
    for intent in result.airtable_updates:
        entity = _ENTITY_BY_TABLE.get(intent.table)
        if entity is None:
            continue
        new_status = intent.fields.get("Status")
        if new_status is None:
            continue
        if intent.record_id is None:
            if new_status not in known_states(entity):
                problems.append(f"create on {intent.table} uses unknown status {new_status!r}")
            continue
        list_name = _TABLE_TO_STATE_LIST.get(intent.table)
        records = getattr(state, list_name) if list_name else []
        current_record = next((r for r in records if r.get("id") == intent.record_id), None)
        if current_record is None:
            problems.append(f"update references unknown record {intent.record_id!r} in {intent.table}")
            continue
        current_status = current_record.get("status")
        try:
            validate_transition(entity, current_status, new_status)
        except IllegalTransition as exc:
            problems.append(str(exc))
    return problems


def apply_result_to_state(state: BusinessState, task: Task, result: Result) -> None:
    for intent in result.airtable_updates:
        list_name = _TABLE_TO_STATE_LIST.get(intent.table)
        if list_name is None:
            continue
        records = getattr(state, list_name)
        normalized = _normalize_fields(intent.fields)
        if intent.record_id is None:
            new_record = {"id": f"sim_{uuid.uuid4().hex[:10]}", **normalized}
            records.append(new_record)
        else:
            for r in records:
                if r.get("id") == intent.record_id:
                    r.update(normalized)
                    break
        intent.applied = True  # applied to the in-memory snapshot; see module docstring

    consumed = result.output.get("consumed_opportunity_ids")
    if consumed:
        state.opportunities = [o for o in state.opportunities if o.get("id") not in consumed]

    new_opportunities = result.output.get("new_opportunities")
    if new_opportunities:
        state.opportunities.extend(new_opportunities)

    marker = _AGENT_TO_LOG_MARKER.get(task.agent)
    if marker and marker not in state.daily_ops_log_today:
        state.daily_ops_log_today.append(marker)


def _normalize_fields(fields: dict) -> dict:
    return {_FIELD_KEY_MAP.get(k, k): v for k, v in fields.items()}
