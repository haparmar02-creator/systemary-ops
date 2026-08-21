# Routine: script-writer

## Purpose
Writes full scripts for Calendar records in RESEARCH status, saves them
to Google Drive, links them back to Airtable, and advances the record to
SCRIPT status. Does not touch production/filming — that stays with the
human. Does not approve or publish anything.

## Schedule
Daily, 09:00 IST (runs after content-strategy, which finishes ~08:15-08:30)

## Required connectors
- Airtable (Content Ops base)
- Notion (Brand Memory & Business Ops)
- Google Drive

## Steps

1. Read the Notion "Brand Identity" and "Tone & Voice" pages — every
   script must match this voice exactly (direct, hands-on, shows real
   work, avoids hype language and vague AI-buzzword claims).

2. Read all Airtable "Calendar" records where Status = RESEARCH,
   ordered by Scheduled Time (soonest first).

3. If none exist, log "nothing in RESEARCH to script today" and stop —
   do not force a script for an IDEA-status record.

4. For each RESEARCH record, up to a maximum of 2 per run (matching
   content-strategy's pacing, so scripting never gets ahead of what
   was actually prioritized):

   a. Write a full script matching the record's Content Type and
      Content Pillar. Structure varies by type:
      - Long-form Build-Along: hook (first 15 seconds must state the
        specific real problem being solved), the actual build process
        in real steps (no skipped steps, no "and then magic happens"),
        a results/outcome section, a CTA.
      - Short/Reel: hook in the first 3 seconds, single clear point,
        no more than 60 seconds of spoken content.
      - What I'd Charge: build on the paired Build-Along's actual
        content (read that paired record if one is linked via Notes),
        give a real price anchored to the ranges in Notion "Business
        Strategy" (₹40,000-80,000 for single-workflow), explain what
        drives the price up or down.
      - Tool Comparison / Myth-Busting: follow the structure implied
        by the Content Pillar description in Notion.

   b. Never fabricate a result, statistic, client detail, or brand-voice claim not
grounded in the record's Notes or Brand Memory. This explicitly includes
general industry/market statistics stated as fact in a hook or body (e.g.
"small businesses lose X hours a week to Y") — a specific number needs a
real, checkable source. If no verified source is available, use qualitative
language instead of a specific figure (e.g. "loses real hours every week"
rather than "loses 23 hours a week"). Use [INSERT REAL EXAMPLE HERE]
placeholders instead of inventing numbers of any kind, client-specific or
general.

   c. Save the script as a Google Doc-compatible text file in Drive,
      under /Channel-Ops/01-Scripts/, named using the Calendar record's
      Content ID and Topic (e.g. "005-i-automated-a-real-clients-email-triage.md").

   d. Update the Calendar record:
      - Script Link: the Drive file's URL
      - Status: SCRIPT (from RESEARCH)
      - Notes: append one line noting the script is ready and flagging
        any [INSERT REAL EXAMPLE HERE] placeholders that still need a
        real example from the human before production

5. Write a run summary appended to the Notion "Daily Ops Log," using the
   same format as the other routines:

   ## [Date] — script-writer
   🔥 IMPORTANT: (any placeholders needing a real example, or "none")
   💡 OPPORTUNITIES: (which records were scripted, with Drive links)
   ✅ COMPLETED: (how many RESEARCH records reviewed, how many scripted)
   🎯 NEXT ACTIONS: (what the human should review or supply before
   production starts)

## Error handling
- If a tool call fails, retry once. If it fails again, log the failure
  plainly in the Daily Ops Log entry under a "⚠️ RISKS" line, leave that
  record's Status at RESEARCH, and move to the next record — do not
  advance a record to SCRIPT without a saved, linked script.
- Never fabricate a result, statistic, client detail, or brand-voice
  claim not grounded in the record's Notes or Brand Memory. Use
  [INSERT REAL EXAMPLE HERE] placeholders instead.

## Completion criteria
Run is complete when: all current RESEARCH records have been reviewed
(up to the 2-per-run cap), each scripted record has a saved Drive file,
a Script Link, and Status = SCRIPT, and a Daily Ops Log entry exists for
today — including zero-scripted days with an explicit note.

## What this routine must NOT do
- Must not touch production, filming, or editing
- Must not approve, publish, or schedule anything for posting
- Must not script more than 2 records in a single run
- Must not invent case studies, statistics, or client results
- Must not touch Approvals or Revenue tables
