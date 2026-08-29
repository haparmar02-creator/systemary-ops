# Routine: content-qc

## Purpose
The full QC Agent pass. Checks Calendar records in REVIEW status —
already mechanically complete per post-production-qc — against brand,
legal, and monetization standards before anything is put in front of
the owner for a publish decision. This is the last automated gate;
everything it advances lands in Approvals as a Pending row for the
owner. It does not watch/verify video content quality (that's
post-production-qc's mechanical checks plus the owner's own eyes) — it
checks the *claims and context around* the content: what it says,
whether it's on-brand, whether it's a legal/copyright risk, and
whether it fits the platform and monetization rules.

This routine did not exist before the Priority-2 orchestrator build.
It fills the REVIEW -> AWAITING_APPROVAL gap between post-production-qc
(PRODUCTION -> REVIEW, mechanical) and the owner's own AWAITING_APPROVAL
-> APPROVED decision. See orchestrator/state_machine.py.

## Schedule
Every 6 hours, same cadence as post-production-qc (it's downstream of it)

## Required connectors
- Airtable (Content Ops base)
- Notion (Brand Memory & Business Ops)
- Google Drive

## Steps

1. Read the Notion "Brand Identity" and "Tone & Voice" pages, and the
   Notion "Business Strategy" page for monetization/positioning
   context.

2. Read all Airtable "Calendar" records where Status = REVIEW.

3. If none exist, log "nothing in REVIEW to QC" and stop.

4. For each REVIEW record, read its script (Script Link) and any
   available caption/hashtags on the record, and check:

   a. **Factual accuracy / claims check** — same fabrication bar as
      production-qc's script gate, re-checked against the final
      script (things can drift during production/editing): any
      specific claim stated as fact must trace to Notes/Brand Memory
      or be an explicit placeholder.

   b. **Brand consistency check** — does the final caption/hashtags
      match Tone & Voice? Flag hype language or off-brand framing.

   c. **Copyright risk check** — does the script/caption reference
      third-party music, footage, logos, or quoted material without
      a clear license/attribution note? Flag anything unclear as a
      risk, don't assume it's fine.

   d. **Platform requirements check** — does the record have the
      fields the target Platform needs (Caption present, Hashtags
      present for Instagram; appropriate length for Content Type)?

   e. **Monetization alignment check** — does the content align with
      how Systemary actually monetizes (per Business Strategy —
      service/product pricing, affiliate disclosures if applicable)?
      Flag anything that could misrepresent pricing or create an
      undisclosed-endorsement risk.

5. Based on the checks:
   - **If any check in 4a-4c fails**: leave Status at REVIEW, write a
     specific note on what failed, and flag under 🔥 IMPORTANT — these
     three are high-severity findings.
   - **If only 4d/4e have minor gaps**: leave Status at REVIEW with a
     specific, actionable note; these are usually quick fixes, not a
     bounce back to production.
   - **If everything passes**: advance Status to AWAITING_APPROVAL, and
     create a new Airtable "Approvals" record:
     - Brief: one paragraph summarizing what this is and why it's
       ready
     - Content: linked to this Calendar record
     - Type: Content
     - Status: Pending
     - Risk Reason: explicit "no elevated risk found" or a note on
       anything borderline the owner should specifically look at
     This is the human-in-the-loop handoff — the orchestrator does not
     advance AWAITING_APPROVAL -> APPROVED itself; only the owner
     resolving the Approvals record does that (see AUTONOMY RULES in
     docs/orchestrator/ARCHITECTURE.md).

6. Write a run summary to the Notion "Daily Ops Log":

   ## [Date] — content-qc
   🔥 IMPORTANT: (any factual/brand/copyright findings, or "none")
   💡 OPPORTUNITIES: (records advanced to AWAITING_APPROVAL, with the
   Approvals record created for each)
   ✅ COMPLETED: (how many REVIEW records checked)
   🎯 NEXT ACTIONS: (what's now waiting on the owner in Approvals)

## Error handling
- If the script or produced asset can't be read, leave the record at
  REVIEW, log the access failure, and do not guess.
- Never advance a record with an unresolved factual/brand/copyright
  finding, regardless of how minor it seems — when in doubt, fail the
  check and let the owner decide.
- Never create a duplicate Approvals record for a Calendar record that
  already has a Pending one — check first.

## Completion criteria
Run is complete when: all current REVIEW records have been checked
against all 5 criteria, each has either advanced to AWAITING_APPROVAL
(with an Approvals record created) or remained at REVIEW with specific
notes, and a Daily Ops Log entry exists for this run.

## What this routine must NOT do
- Must not advance a record with an unresolved factual/brand/copyright
  finding
- Must not move a record to APPROVED — that is the owner's decision on
  the Approvals record, not this routine's
- Must not touch Revenue or Clients/Leads tables
- Must not publish or schedule anything
