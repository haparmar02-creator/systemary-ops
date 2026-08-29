# Systemary orchestrator — architecture

This document explains what the code in `orchestrator/` does and why.
It is not a substitute for the code — where the two disagree, the code
is right. Read this first, then `orchestrator/*.py` docstrings for the
mechanics.

## The chain of command

Owner -> Claude (central orchestrator) -> specialized agents (workers)
-> Make/n8n/API/MCP (execution tools). Airtable is operational state.
Notion is long-term business memory. Google Drive is asset storage.
Analytics + Revenue are the feedback loop the priority engine reads.

"Agent" in this codebase is a **role**, not a separate process. Claude
performs the role directly, or via a subagent, following the mapped
routine file's instructions where one exists (`routines/*.md`,
reconciled against this build in `routines/AGENT_MAPPING.md`). Nothing
in `orchestrator/` holds Airtable/Notion/Drive credentials or makes a
network call — it is the deterministic core the orchestrating Claude
session calls into after fetching state via its own MCP tools.

## The decision loop, and what's actually code

```
READ STATE        -> whatever fetches a snapshot (Claude, via MCP tools;
                      a JSON fixture in tests) + memory.BusinessState.from_dict
ASSESS BUSINESS   -> memory.assess()                              [code]
IDENTIFY          -> priority.identify_candidate_actions()        [code]
PRIORITIZE        -> priority.prioritize()                        [code]
SELECT AGENT      -> orchestrator.run_cycle() (filters disabled)  [code]
EXECUTE           -> caller-supplied `execute(task) -> Result`    [Claude, or simulate.py in dry-run]
VERIFY RESULT     -> orchestrator.verify_result() + state_machine [code]
UPDATE STATE      -> orchestrator.apply_result_to_state()         [code]
REASSESS/CONTINUE -> orchestrator.run_until_idle()                [code]
```

Everything except EXECUTE itself is real, tested Python — see
`tests/`. EXECUTE is necessarily an LLM call in production (writing a
script, judging brand voice, evaluating a competitor's video) so it
can't be "coded" in the sense the rest of the loop is; what's coded
around it is the routing, retry, legality-checking, and state-folding
that make repeated EXECUTE calls compose into an autonomous cycle
instead of a pile of disconnected agent invocations.

## Agent registry

`orchestrator/agents.py`. Ten roles: research, content_strategy,
script, production, qc, publishing, community, analytics, revenue,
growth. Each has `reads`/`writes` (which memory sources), a default
`ApprovalRequirement`, a `RetryPolicy` (timeout + max_retries), and an
`enabled` flag. `production` and `publishing` are `enabled=False` —
production has no automated path yet (human films/edits), and
publishing is explicitly out of scope for this phase. A disabled
agent's tasks are never dispatched by `run_cycle`, regardless of how
they'd score — see `SELECT AGENT` in `orchestrator.py`.

## Task/Result contract

`orchestrator/schema.py`. Every agent call is a `Task` in, `Result`
out — `task_id`, `agent`, `objective`, `inputs`, `constraints`,
`expected_output`, `approval_requirement` on the way in;
`status`, `output`, `evidence`, `errors`, `airtable_updates`
(a list of *proposed* writes, `applied=False` until a real,
non-dry-run write actually happens), `next_recommended_action` on the
way out. This is what lets one agent's result become the next agent's
task input (see `priority.py`'s candidate generators reading
`assessment` fields that upstream agents populate).

## State machine

`orchestrator/state_machine.py`. Four entity types — content, lead,
approval, experiment — each a directed graph of legal transitions.
`orchestrator.verify_result()` checks every proposed transition before
`apply_result_to_state()` ever runs, dry-run or not. An illegal jump
(e.g. IDEA -> PUBLISHED) fails the whole result rather than partially
applying.

Content pipeline, as actually deployed in the live Airtable Status
field: `IDEA -> RESEARCH -> SCRIPT -> PRODUCTION -> REVIEW ->
AWAITING_APPROVAL -> APPROVED -> SCHEDULED -> PUBLISHED -> ANALYZING ->
REPURPOSED`, plus rework edges (REVIEW/AWAITING_APPROVAL back to
PRODUCTION). **Known live bug**: the Airtable Status field currently
has `AWAITING_APPROVAL` split into two separate choices, `AWAITING`
and `APPROVAL`, plus a few stray blank-name choices on Status/Content
Type/Content Pillar. This connector has no delete-choice capability, so
it couldn't be fixed programmatically — `state_machine.py`'s module
docstring and `memory._find_blocked_and_warnings()` both flag it; any
Calendar record actually carrying one of those broken statuses shows up
as a `blocked` item with an explicit warning rather than being silently
misread. Needs a manual fix in the Airtable UI.

## Priority engine (revenue-first)

`orchestrator/priority.py`. Seven categories, strictly descending
weights: revenue potential > lead potential > audience growth >
audience quality > retention > brand value > efficiency. A candidate's
urgency (how many items, how stale) only adjusts its score *within*
its category band — it can never cross into the next band up. This is
directly tested (`tests/test_priority.py`,
`test_a_single_revenue_row_outranks_a_pile_of_efficiency_work`): a
single real revenue-attribution task always outranks a pile of routine
housekeeping, which is the whole point of "views/followers/likes are
not success."

## Approval rules

Encoded as `ApprovalRequirement` on each `Task`: `NONE` (proceed,
no human step), `NOTIFY` (proceed, tell the owner what happened),
`REQUIRED` (do not execute — `run_cycle` never even calls the agent;
see `tests/test_orchestrator_dry_run.py::ApprovalRequiredBlocksExecutionTest`).
Ordinary content decisions default to `NONE` throughout the registry.
`REQUIRED` is reserved for what the Priority-2 brief actually listed:
today that's concretely wired for high-ticket service sales
(`priority.HIGH_TICKET_THRESHOLD_INR`, matching the ₹40,000 single-
workflow price floor in Notion Business Strategy) and for the
Publishing agent (disabled entirely, but its default approval is
`REQUIRED` for when it is built). Significant spending, account/
security changes, platform verification, legal/high-risk claims, and
major strategic changes are not yet concretely wired to a candidate
generator — there's no agent producing those kinds of tasks yet in
this phase — but the `ApprovalRequirement` mechanism they'd use already
exists and is tested; wiring them is adding a candidate generator, not
new infrastructure.

## Memory read/write rules

`orchestrator/memory.py`'s `MEMORY_READS` is the literal declarative
spec of what to pull each cycle from Airtable (7 tables), Notion
(8 pages), and Drive (7 folders) — see that module for the full list
and why each one matters to which agent. Writes go through
`Result.airtable_updates` (`AirtableUpdateIntent`: table, record_id
[`None` = create], fields) — never a direct, ad hoc write from inside
an agent's reasoning. That's what makes `verify_result()`'s legality
check possible at all: every write is a structured intent the
orchestrator can inspect before it lands.

## Failure handling

`orchestrator/errors.py`. `run_with_retry()` wraps every EXECUTE call
with the agent's own `RetryPolicy` (timeout + max_retries from the
registry). An exception or a non-SUCCEEDED result gets retried up to
the policy limit; exhausting retries produces an `ESCALATED` Result
with the full per-attempt error history and a concrete
`next_recommended_action` for a human — never a silent failure, never
a bare exception escaping to the caller. `run_until_idle()` stops the
cascade the moment a cycle doesn't succeed, rather than chaining more
agents on top of a bad result.

## Scheduled vs. event-driven work

**Scheduled cognitive work** (existing routines, cadence unchanged):
morning-research (07:00 IST daily), content-strategy (08:00 IST
daily), script-writer (09:00 IST daily), production-qc /
post-production-qc / content-qc (every 4h / 6h / 6h). Two more belong
here but don't have routine files yet (see
`routines/AGENT_MAPPING.md`): an evening analytics pass and a weekly
revenue/growth review — `priority.py` already gates on
`daily_ops_log_today` markers (`"evening-analytics"`,
`"revenue-review"`, `"weekly-growth-review"`) so wiring the routine
files later is additive, not a rework.

**Event-driven work**: a new lead, a new comment, a newly-published
video, an approval decision, production completion (asset linked), an
analytics threshold, an error. The orchestrator already responds to
the state changes these events cause (a new Calendar record, a new
Approvals row, a linked Asset Link) the same way it responds to
anything else it finds on a READ STATE pass — there's no separate
"event handler" code path, which is deliberate: an event is just
something that changed state before the next cycle looks at it. Wiring
live event delivery (e.g. a webhook waking a session) is
infrastructure outside this package's scope; the reaction logic itself
is already exercised by `run_cycle`/`run_until_idle`.

## What was NOT done in this phase

- No live scheduled trigger or event subscription was created. Nothing
  in this build runs on its own yet — it runs when explicitly invoked
  (dry-run demo via `python3 -m orchestrator.cli dry-run`, or a real
  Claude session calling into this package after fetching live state).
  Per the Priority-2 brief: dry-run first, real autonomous execution is
  a separate, explicit decision.
- No real Airtable/Notion/Drive write ever happens inside this package.
  `AirtableUpdateIntent.applied` only becomes `True` when
  `apply_result_to_state()` folds it into an in-memory `BusinessState`
  (dry-run or the demo's simulated cascade) — a real write is a
  decision for whatever's driving the loop (a live Claude session with
  MCP tools) to make explicitly, outside this package.
- Publishing and Production agents are registered but disabled, per
  explicit scope.

## Test plan

`tests/` (stdlib `unittest`, no dependencies to install):
- `test_schema.py` — Task/Result contract invariants.
- `test_state_machine.py` — every entity's legal/illegal transitions,
  including the AWAITING_APPROVAL split-choice regression guard.
- `test_priority.py` — revenue-first ordering (including the "one
  revenue task beats a pile of efficiency work" invariant) and
  individual candidate generators.
- `test_orchestrator_dry_run.py` — the required Priority-2 demonstration:
  a new opportunity cascades research -> content_strategy -> script ->
  qc -> idle, entirely in-memory, zero real writes, deterministic and
  reproducible; plus illegal-transition rejection, approval-required
  blocking (execute() never called), disabled-agent exclusion, and
  retry/escalation behavior.

Run everything: `python3 -m unittest discover -s tests -v`.
Run the human-readable dry-run trace: `python3 -m orchestrator.cli dry-run`.
