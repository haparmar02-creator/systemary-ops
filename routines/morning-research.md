# Routine: morning-research

## Purpose
Daily scan for content opportunities matching Systemary's content pillars.
Writes new content ideas into the Airtable Calendar table as IDEA-status
records. Does not write scripts, does not publish anything, does not make
any irreversible decision.

## Schedule
Daily, 07:00 IST

## Required connectors
- Airtable (Content Ops base)
- Notion (Brand Memory & Business Ops)
- Web search

## Steps

1. Read the Notion page "Content Pillars" (under Brand Memory & Business
   Ops) to recall the 5 pillars: Build-Alongs, Tool Comparisons, What I'd
   Charge For This, Myth-Busting, Client Case Studies.

2. Read the Notion page "Business Strategy" for target audience and
   positioning context.

3. Read the Airtable "Competitors" table. For each competitor row, search
   the web for their most recent content (last 7 days). Update the
   "Notable Recent Content" and "Last Checked" fields with what you find.
   If the Competitors table is currently empty, skip this step and note
   it in the run log.

4. Run 3-5 web searches for current trends/discussion relevant to AI
   automation for small businesses, practical AI tool usage, and small
   business owner pain points — the actual audience this channel serves.

5. From steps 3-4, identify 3-7 concrete content opportunities. For each
   one, it must map to exactly one of the 5 content pillars and should
   have a clear "who is this for and why would they watch" answer before
   it qualifies — reject vague or generic ideas rather than force a
   quota.

6. For each qualifying idea, create a new record in the Airtable
   "Calendar" table:
   - Topic: a specific, concrete working title (not a vague theme)
   - Status: IDEA
   - Content Pillar: the matching pillar
   - Platform: your best guess (YouTube / Instagram / Both)
   - Content Type: your best guess (Long-form / Short / Reel)
   - Notes: one sentence on why this idea is worth making right now

7. Write a short run summary as a new entry appended to the Notion
   "Daily Ops Log" page, using this format:

   ## [Date]
   🔥 IMPORTANT: (anything requiring immediate attention, or "none")
   💡 OPPORTUNITIES: (how many ideas created, one-line list of topics)
   ✅ COMPLETED: (competitors checked, searches run)
   🎯 NEXT ACTIONS: (what the next routine — content-strategy — should
   look at first)

## Error handling
- If a tool call fails, retry once. If it fails again, log the failure
  plainly in the Daily Ops Log entry under a "⚠️ RISKS" line and stop
  that step — do not fabricate data to fill the gap.
- Never invent a competitor's content, a trend, or a statistic. If web
  search returns nothing useful, say so explicitly in the log.

## Completion criteria
Run is complete when: Competitors table is checked (or explicitly
skipped with a note), 3-7 new Calendar IDEA records exist (or zero, with
an explicit "nothing qualified today" note — never force low-quality
ideas to hit a number), and a Daily Ops Log entry exists for today's date.

## What this routine must NOT do
- Must not change any record's Status away from IDEA
- Must not write scripts, captions, or any publish-facing content
- Must not touch the Approvals or Revenue tables
- Must not delete or overwrite existing Calendar records
