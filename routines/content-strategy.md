# Routine: content-strategy

## Purpose
Reviews all IDEA-status records in the Airtable Calendar table and decides
which ones advance toward production today. Sets priority order and target
dates. Does not write scripts — that is script-writer's job. This routine
only makes the "what next, and when" decision.

## Schedule
Daily, 08:00 IST (runs after morning-research, which finishes around 07:15-07:30)

## Required connectors
- Airtable (Content Ops base)
- Notion (Brand Memory & Business Ops)

## Steps

1. Read the Notion "Content Pillars" and "Business Strategy" pages for
   context on priorities and positioning.

2. Read all records in the Airtable "Calendar" table where Status = IDEA.

3. Check pillar balance: count how many PUBLISHED or SCHEDULED records
   exist per Content Pillar over the last 14 days (if the Analytics/
   history data doesn't exist yet, skip this check and note it in the log
   rather than guessing).

4. Prioritize IDEA records using this order of preference:
   a. Ideas that pair naturally (e.g. a Build-Along and its matching
      "What I'd Charge For This" follow-up) — advance both together,
      the case study before the pricing piece.
   b. Ideas from underrepresented pillars over ideas from
      overrepresented ones, to keep the 5-pillar mix balanced.
   c. Ideas with a clearer, more specific "who is this for" — reject
      or deprioritize vague ideas even if nothing better exists; it is
      fine to advance zero ideas on a given day.

5. Select 1-2 ideas to advance today (never more than 2 — this system
   is intentionally paced against real production capacity, not
   maximum throughput).

6. For each selected idea:
   - Change Status from IDEA to RESEARCH
   - Set Scheduled Time to a realistic target date (assume roughly
     2-3 days from today for a Short/Reel, 5-7 days for a Long-form,
     accounting for script + production + QC time)
   - Add a one-line note explaining why this idea was prioritized

7. Write a run summary appended to the Notion "Daily Ops Log," using the
   same format as morning-research:

   ## [Date] — content-strategy
   🔥 IMPORTANT: (anything requiring attention, or "none")
   💡 OPPORTUNITIES: (which ideas were advanced and why)
   ✅ COMPLETED: (how many IDEA records reviewed, how many advanced)
   🎯 NEXT ACTIONS: (what script-writer should pick up)

## Error handling
- If fewer than 1 idea qualifies for advancement, advance zero and say
  so explicitly — do not lower the bar just to hit a number.
- If pillar-balance history data isn't available, skip that check and
  note it rather than fabricating a balance assessment.

## Completion criteria
Run is complete when: all current IDEA records have been reviewed, 0-2
have been advanced to RESEARCH with a Scheduled Time and reasoning note,
and a Daily Ops Log entry exists for today.

## What this routine must NOT do
- Must not write scripts, captions, or any publish-facing content
- Must not create new Calendar records (that's morning-research's job)
- Must not advance more than 2 ideas in a single run
- Must not touch Approvals or Revenue tables
