# Existing routines vs. the Priority-2 agent registry

This is the reconciliation the Priority-2 build required: which of the
five pre-existing routines become which specialized agent, which stay
as scheduled routines, which the orchestrator can also call on demand,
which needed modification, and which are genuinely new. Nothing here
was thrown away.

## 1. morning-research.md -> Research Agent

**Unchanged.** Stays a 07:00 IST scheduled routine. Also directly
reusable by the orchestrator on demand — `agents.AGENTS["research"]`
points at this file, and `priority._opportunity_candidates` dispatches
the same agent role for ad hoc, event-driven opportunities (e.g. "a
competitor just posted something big") that enter the system outside
the daily cadence. In that ad hoc mode the agent's job narrows to
*evaluating* an already-surfaced opportunity rather than scanning for
new ones — same qualification bar, different trigger.

## 2. content-strategy.md -> Content Strategy Agent

**Unchanged**, with one clarified scope note. The routine's daily job
(IDEA -> RESEARCH pacing/prioritization) stays exactly as written and
scheduled at 08:00 IST. The broader Content Strategy Agent role in the
registry also covers a second mode: committing an ad hoc *qualified*
opportunity straight into the Calendar pipeline (deciding platform/
format/priority/pillar for something that didn't come from the daily
IDEA queue). That second mode isn't written up as its own routine file
yet — see "Not yet built as routines" below.

## 3. script-writer.md -> Script Agent

**Unchanged.** Stays a 09:00 IST scheduled routine, also directly
reusable on demand whenever the orchestrator finds Calendar records in
RESEARCH status outside the daily cadence.

## 4. production-qc.md -> QC Agent (gate 1 of 3)

**Modified.** This routine's Purpose/Steps previously said it advances
a clean SCRIPT record to REVIEW. That's wrong against the Priority-2
state machine, where REVIEW comes *after* production, not before it.
Fixed: it now advances SCRIPT -> PRODUCTION (a "you're cleared to
film" gate). The routine's actual checklist (fabrication/placeholder/
voice/structure/metadata) didn't need to change, only its target
status and the surrounding prose that described it.

## 5. post-production-qc.md -> QC Agent (gate 2 of 3)

**Modified.** Previously advanced a mechanically-complete PRODUCTION
record straight to AWAITING_APPROVAL, skipping REVIEW entirely and
skipping any actual content-quality check (which its own Purpose
section correctly says is out of scope — "does NOT watch, judge, or
verify"). Fixed: it now advances PRODUCTION -> REVIEW. The mechanical
completeness checklist (file existence, naming, metadata plausibility,
script-link cross-check) is unchanged.

## 6. content-qc.md -> QC Agent (gate 3 of 3) — NEW

**New routine, not modified from anything.** This fills the gap the
fix above created: something has to actually gate REVIEW ->
AWAITING_APPROVAL, and nothing did before. It's the full QC Agent pass
from the Priority-2 spec — factual accuracy, brand consistency,
copyright risk, platform requirements, monetization alignment — and
it's the routine that actually creates the Approvals record the owner
acts on. Scheduled the same every-6-hours cadence as post-production-qc
since it's immediately downstream of it.

## Not yet built as routines

These agent roles exist in `orchestrator/agents.py` but have no
`routine_file` yet — either because the work they'd do doesn't exist
as an automated capability in this environment, or because Priority 2
was explicitly scoped to not build them:

- **Production Agent** — `enabled=False`. Filming/editing/voice/visual
  coordination is a human step today. Registered so the orchestrator's
  state machine has a place to route to if that ever becomes
  automatable, but it is never dispatched.
- **Publishing Agent** — `enabled=False`, `default_approval=REQUIRED`.
  Explicitly out of scope for this phase per the Priority-2 brief
  ("do NOT build YouTube or Instagram publishing yet").
- **Community Agent** — enabled, but scoped narrowly today: only the
  Airtable-leads-via-Gmail follow-up path is live (Gmail is a wired
  connector in this environment). Comment/DM classification on
  YouTube/Instagram has no API access wired yet; any task that would
  need it must self-escalate rather than silently no-op. No routine
  file written yet for the lead-follow-up path — it's simple enough
  that the orchestrator dispatches it directly today (see
  `priority._lead_candidates`), but it should get one before this runs
  unattended for real.
- **Analytics Agent** and **Revenue Agent** — enabled, dispatchable by
  the orchestrator (`priority._analytics_candidate`,
  `priority._revenue_candidates`), but no dedicated routine file yet.
  Both are natural "evening" scheduled cognitive work
  (see docs/orchestrator/ARCHITECTURE.md's scheduling section) that
  should get routine files before Priority 3.
- **Growth Agent** — same as above; synthesizes the other agents'
  output into recommendations/experiments
  (`priority._growth_candidate`), no routine file yet, natural weekly
  cadence.

## Redundant routines

None. All five pre-existing routines map to real, still-needed work.

## The Gmail -> Gemini -> Airtable lead automation

Explicitly out of scope for this reconciliation, per instruction: it's
an existing business workflow living outside this repo (in Make/n8n/
Gemini), not part of the central orchestration architecture. It writes
into the same `Clients/Leads` table the orchestrator reads
(`priority._lead_candidates`), so the orchestrator sees its output as
ordinary state — it's a *source* into the same operational memory, on
the same footing as any other lead-intake channel, not something the
orchestrator drives or modifies. Nothing in this build touches it.
