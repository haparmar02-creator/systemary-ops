"""Deterministic stand-in for real agent execution, used only for tests
and `cli.py dry-run`.

In production, EXECUTE means Claude actually performs the specialized
agent's role (writing a real script, actually checking Drive for a
file, actually reading Notion for brand voice) and returns a Result.
This module fabricates plausible-but-fake Results with the same shape,
so the deterministic parts of the orchestrator (routing, state machine,
priority, retry/verify) can be exercised end-to-end without an LLM call,
without credentials, and without touching real Airtable/Notion/Drive.

Every output is clearly labeled "(simulated)" so nothing here could be
mistaken for a real script, a real QC finding, or real analytics.
"""
from __future__ import annotations

import uuid

from orchestrator.schema import AirtableUpdateIntent, Result, Task, TaskStatus


def simulate_agent_execution(task: Task) -> Result:
    handler = _HANDLERS.get(task.agent, _default_handler)
    return handler(task)


def _default_handler(task: Task) -> Result:
    return Result(
        task_id=task.task_id,
        agent=task.agent,
        status=TaskStatus.SUCCEEDED,
        output={"note": f"(simulated) no handler for agent {task.agent!r}; treated as a no-op success"},
        evidence=["simulated: default no-op handler"],
        errors=[],
        airtable_updates=[],
        next_recommended_action=None,
    )


def _research(task: Task) -> Result:
    raw_opportunities = task.inputs.get("opportunities")
    if raw_opportunities is not None:
        # Ad hoc evaluation mode: qualify what came in.
        qualified = [dict(o, qualified=True, evaluation="(simulated) meets the clear who/why bar")
                     for o in raw_opportunities]
        return Result(
            task_id=task.task_id,
            agent="research",
            status=TaskStatus.SUCCEEDED,
            output={
                "consumed_opportunity_ids": [o.get("id") for o in raw_opportunities],
                "new_opportunities": qualified,
            },
            evidence=[f"(simulated) evaluated {len(raw_opportunities)} raw opportunity(ies)"],
            errors=[],
            airtable_updates=[],
            next_recommended_action="content_strategy should decide platform/format/priority for the qualified opportunity(ies)",
        )

    # Scheduled cadence mode: scan and surface new opportunities.
    new_id = f"opp_{uuid.uuid4().hex[:8]}"
    return Result(
        task_id=task.task_id,
        agent="research",
        status=TaskStatus.SUCCEEDED,
        output={
            "new_opportunities": [{
                "id": new_id,
                "topic": "(simulated) a concrete, specific working title",
                "pillar": "Build-Along",
                "platform": "YouTube",
                "content_type": "Long-form",
                "why": "(simulated) clear who-is-this-for-and-why answer",
                "qualified": False,
            }],
        },
        evidence=["(simulated) daily competitor/trend scan"],
        errors=[],
        airtable_updates=[],
        next_recommended_action="research should evaluate the new opportunity before it enters the pipeline",
    )


def _content_strategy(task: Task) -> Result:
    opportunities = task.inputs.get("opportunities")
    if opportunities:
        selected = opportunities[:2]  # pacing rule: never more than 2 at once
        updates = [
            AirtableUpdateIntent(
                table="Calendar",
                record_id=None,
                fields={
                    "Status": "RESEARCH",
                    "Topic": o.get("topic", "(simulated) untitled"),
                    "Platform": o.get("platform", "YouTube"),
                    "Content Type": o.get("content_type", "Long-form"),
                    "Content Pillar": o.get("pillar", "Build-Along"),
                    "Notes": f"(simulated) committed from opportunity {o.get('id')}: {o.get('why', '')}",
                    "Scheduled Time": "2026-09-03T09:00:00Z",
                },
            )
            for o in selected
        ]
        return Result(
            task_id=task.task_id,
            agent="content_strategy",
            status=TaskStatus.SUCCEEDED,
            output={"consumed_opportunity_ids": [o.get("id") for o in selected]},
            evidence=[f"(simulated) committed {len(selected)} of {len(opportunities)} qualified opportunity(ies)"],
            errors=[],
            airtable_updates=updates,
            next_recommended_action="script agent should pick up the new RESEARCH record(s)",
        )

    # Daily cadence mode: advance existing IDEA records to RESEARCH.
    records = task.inputs.get("calendar_records", [])
    selected = records[:2]
    updates = [
        AirtableUpdateIntent(
            table="Calendar",
            record_id=r["id"],
            fields={
                "Status": "RESEARCH",
                "Scheduled Time": "2026-09-03T09:00:00Z",
                "Notes": "(simulated) prioritized: pairs well, underrepresented pillar",
            },
        )
        for r in selected
    ]
    return Result(
        task_id=task.task_id,
        agent="content_strategy",
        status=TaskStatus.SUCCEEDED,
        output={},
        evidence=[f"(simulated) advanced {len(selected)} of {len(records)} IDEA record(s)"],
        errors=[],
        airtable_updates=updates,
        next_recommended_action="script agent should pick up the newly-advanced RESEARCH record(s)",
    )


def _script(task: Task) -> Result:
    records = task.inputs.get("calendar_records", [])
    selected = records[:2]  # script-writer's own per-run cap
    updates = [
        AirtableUpdateIntent(
            table="Calendar",
            record_id=r["id"],
            fields={
                "Status": "SCRIPT",
                "Script Link": f"https://drive.example/simulated/{r['id']}.md",
                "Notes": "(simulated) script ready; no [INSERT REAL EXAMPLE HERE] placeholders",
            },
        )
        for r in selected
    ]
    return Result(
        task_id=task.task_id,
        agent="script",
        status=TaskStatus.SUCCEEDED,
        output={},
        evidence=[f"(simulated) scripted {len(selected)} of {len(records)} RESEARCH record(s)"],
        errors=[],
        airtable_updates=updates,
        next_recommended_action="qc should run the script gate before this reaches production",
    )


_QC_GATE_TRANSITIONS = {
    "script": "PRODUCTION",
    "post_production": "REVIEW",
    "full_qc": "AWAITING_APPROVAL",
}


def _qc(task: Task) -> Result:
    gate = task.inputs.get("gate", "script")
    target_status = _QC_GATE_TRANSITIONS[gate]
    records = task.inputs.get("calendar_records", [])

    updates = []
    approval_note = None
    for r in records:
        updates.append(AirtableUpdateIntent(
            table="Calendar",
            record_id=r["id"],
            fields={"Status": target_status, "Notes": f"(simulated) {gate} QC: clean pass"},
        ))
        if gate == "full_qc":
            updates.append(AirtableUpdateIntent(
                table="Approvals",
                record_id=None,
                fields={
                    "Brief": f"(simulated) approve for publish: {r.get('topic', r['id'])}",
                    "Content": [r["id"]],
                    "Type": "Content",
                    "Status": "Pending",
                    "Risk Reason": "(simulated) ordinary content decision, no elevated risk found",
                },
            ))
            approval_note = "none required to run QC itself; publish approval now queued for owner"

    evidence = [f"(simulated) {gate} QC gate: {len(records)} record(s) advanced to {target_status}"]
    output = {"approval_requirement_determined": "none" if gate != "full_qc" else "required_for_publish"}
    if approval_note:
        evidence.append(f"(simulated) approval determination: {approval_note}")

    return Result(
        task_id=task.task_id,
        agent="qc",
        status=TaskStatus.SUCCEEDED,
        output=output,
        evidence=evidence,
        errors=[],
        airtable_updates=updates,
        next_recommended_action=(
            "awaiting human production (asset not yet linked)" if gate == "script"
            else f"next pipeline stage is {target_status}"
        ),
    )


def _analytics(task: Task) -> Result:
    return Result(
        task_id=task.task_id, agent="analytics", status=TaskStatus.SUCCEEDED,
        output={}, evidence=["(simulated) refreshed performance data"], errors=[],
        airtable_updates=[], next_recommended_action=None,
    )


def _revenue(task: Task) -> Result:
    return Result(
        task_id=task.task_id, agent="revenue", status=TaskStatus.SUCCEEDED,
        output={}, evidence=["(simulated) reviewed revenue attribution"], errors=[],
        airtable_updates=[], next_recommended_action=None,
    )


def _growth(task: Task) -> Result:
    return Result(
        task_id=task.task_id, agent="growth", status=TaskStatus.SUCCEEDED,
        output={}, evidence=["(simulated) synthesized a recommendation"], errors=[],
        airtable_updates=[], next_recommended_action=None,
    )


def _community(task: Task) -> Result:
    return Result(
        task_id=task.task_id, agent="community", status=TaskStatus.SUCCEEDED,
        output={}, evidence=["(simulated) followed up on stalled leads"], errors=[],
        airtable_updates=[], next_recommended_action=None,
    )


_HANDLERS = {
    "research": _research,
    "content_strategy": _content_strategy,
    "script": _script,
    "qc": _qc,
    "analytics": _analytics,
    "revenue": _revenue,
    "growth": _growth,
    "community": _community,
}
