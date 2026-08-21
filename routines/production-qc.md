# Routine: production-qc

## Purpose
Reviews Calendar records in SCRIPT status against a quality checklist
before they're allowed to advance. Does not fix problems itself — it
either advances a clean record to REVIEW, or leaves it in SCRIPT with
specific, actionable notes on what needs fixing. This is a gate, not
a production step.

## Schedule
Every 4 hours (this one runs more often than the daily routines, since
its job is to keep pace with whatever script-writer and manual human
edits produce, not to originate work on its own clock)

## Required connectors
- Airtable (Content Ops base)
- Notion (Brand Memory & Business Ops)
- Google Drive

## Steps

1. Read the Notion "Brand Identity" and "Tone & Voice" pages as the
   standard to check against.

2. Read all Airtable "Calendar" records where Status = SCRIPT.

3. If none exist, log "nothing in SCRIPT to review" and stop.

4. For each SCRIPT record, open its linked script file from Drive and
   check it against this list:

   a. **Fabrication check** — any specific statistic, result, or claim
      stated as fact must either trace to something in the record's
      Notes/Brand Memory, or be clearly marked as a placeholder
      (e.g. [INSERT REAL EXAMPLE HERE]). A specific unsourced number
      stated as fact anywhere in the script — hook, body, or
      elsewhere — is an automatic fail, not just in results sections.

   b. **Placeholder check** — count any remaining [INSERT REAL EXAMPLE
      HERE] markers. This is not automatically a fail (real content
      often isn't finalized yet), but it must be listed explicitly so
      a human knows what's still needed before filming/recording.

   c. **Voice check** — does the script match the Tone & Voice page
      (direct, hands-on, avoids hype language and vague AI-buzzword
      claims)? Flag specific lines that read as hype rather than
      rewriting them — this routine flags, it does not silently edit.

   d. **Structural check** — does the script have a hook, body, and
      CTA appropriate to its Content Type (per script-writer's
      structure rules)? Flag if a section is missing or clearly
      incomplete.

   e. **Metadata check** — does the Calendar record have a Script
      Link, correct Content Pillar, and correct Platform filled in?

5. Based on the checks:
   - **If the fabrication check fails**: leave Status at SCRIPT,
     write a specific note identifying the exact fabricated claim and
     its location in the script, and flag it under 🔥 IMPORTANT in
     the log — this is the highest-severity finding this routine can
     produce.
   - **If only placeholders remain (no fabrication, no voice/structure
     issues)**: advance Status to REVIEW, but add a note listing
     exactly which placeholders still need real content before
     filming — advancing to REVIEW does not mean "ready to film,"
     it means "ready for human eyes," which is accurate even with
     open placeholders.
   - **If voice or structural issues exist**: leave Status at SCRIPT,
     list the specific issues found, do not advance.
   - **If everything passes clean**: advance to REVIEW with a note
     confirming a clean pass.

6. Write a run summary to the Notion "Daily Ops Log":

   ## [Date] — production-qc
   🔥 IMPORTANT: (any fabrication findings — these are the only
   findings that belong in this section; everything else goes in
   the categories below)
   💡 OPPORTUNITIES: (records advanced to REVIEW, and with what
   remaining placeholder notes)
   ✅ COMPLETED: (how many SCRIPT records reviewed)
   🎯 NEXT ACTIONS: (what needs a human decision or fix)

## Error handling
- If a script file can't be opened from Drive, leave the record at
  SCRIPT, log the access failure plainly, and do not guess at its
  content to complete the review.
- This routine must never silently pass a record with an unresolved
  fabrication finding — when in doubt about whether something counts
  as fabrication, treat it as a fail and let a human make the final
  call, rather than assuming it's fine.

## Completion criteria
Run is complete when: all current SCRIPT records have been checked
against all 5 criteria, each has either advanced to REVIEW (with any
placeholder notes) or remained at SCRIPT (with specific fix notes),
and a Daily Ops Log entry exists for this run — including runs that
find nothing to review.

## What this routine must NOT do
- Must not edit, rewrite, or "fix" script content itself — it flags,
  a human or script-writer's next run fixes
- Must not advance a record with a fabrication finding, under any
  circumstance
- Must not advance more than what's actually in SCRIPT status —
  no artificial cap needed here since this is a gate, not a creator
- Must not touch Approvals, Revenue, or Clients/Leads tables
- Must not publish or schedule anything
