# Routine: post-production-qc

## Purpose
Checks Calendar records in PRODUCTION status for basic completeness once
a produced asset lands in Drive — file exists, correctly named and filed,
properly linked, and metadata is plausible. This is a mechanical
completeness check, not a creative or content-quality review. It does
NOT watch, judge, or verify the actual video/audio content — that
remains a human judgment call.

## Schedule
Every 6 hours

## Required connectors
- Airtable (Content Ops base)
- Google Drive

## Steps

1. Read all Airtable "Calendar" records where Status = PRODUCTION.

2. If none exist, log "nothing in PRODUCTION to check" and stop.

3. For each PRODUCTION record:

   a. **File existence check** — does the "Asset Link" field contain a
      URL, and does that file actually exist in Drive? If Asset Link is
      empty or the file can't be found, this is a hard fail — leave
      Status at PRODUCTION and note "no produced asset found."

   b. **Location/naming check** — is the file located in
      /Channel-Ops/03-Produced/, and does its filename follow the
      Content ID + Topic convention used by script-writer? Flag if not,
      but this alone does not block advancement — it's a note for
      tidiness, not a quality gate.

   c. **Metadata plausibility check** — read the file's available
      metadata (duration, file size, format). Compare duration loosely
      against the script's Content Type (a "Long-form" video running
      under 2 minutes, or a "Short" running over 3 minutes, is
      implausible and worth flagging as a likely wrong file or
      incomplete edit). This is a sanity check, not a precise judgment.

   d. **Script-link cross-check** — confirm the record still has a
      valid Script Link pointing to an existing script file, so the
      produced asset and its source script are both traceable from the
      same record.

4. Based on the checks:
   - **If the file existence check fails**: leave Status at PRODUCTION,
     log clearly what's missing.
   - **If existence and script-link checks pass but metadata looks
     implausible**: leave Status at PRODUCTION, flag the specific
     concern (e.g. "Long-form video is only 45 seconds — confirm this
     is the correct final file") for human review.
   - **If all checks pass**: advance Status to AWAITING_APPROVAL, with
     a note stating this is a mechanical completeness pass only — actual
     content quality (picture, audio, whether it matches what the
     script describes) has NOT been verified and still needs human
     review before this is treated as ready to publish.

5. Write a run summary to the Notion "Daily Ops Log":

   ## [Date] — post-production-qc
   🔥 IMPORTANT: (missing files or implausible metadata, or "none")
   💡 OPPORTUNITIES: (records advanced to AWAITING_APPROVAL)
   ✅ COMPLETED: (how many PRODUCTION records checked)
   🎯 NEXT ACTIONS: (what needs a human to actually watch/review)

## Error handling
- If a Drive file can't be read (permissions, wrong ID, etc.), treat
  this the same as "file existence check failed" — do not assume the
  file is fine just because a link exists.
- Never claim to have verified video/audio content quality — this
  routine's advancement to AWAITING_APPROVAL always means "mechanically
  complete," never "content confirmed good."

## Completion criteria
Run is complete when: all current PRODUCTION records have been checked
against all 4 criteria, each has either advanced to AWAITING_APPROVAL
(with the explicit "not content-reviewed" note) or remained at
PRODUCTION with specific missing/implausible items listed, and a Daily
Ops Log entry exists for this run.

## What this routine must NOT do
- Must not claim to have watched, judged, or verified actual video or
  audio content quality
- Must not advance a record with a missing or unreachable asset file
- Must not touch Approvals, Revenue, or Clients/Leads tables
- Must not publish or schedule anything
- Must not delete or overwrite any produced asset
