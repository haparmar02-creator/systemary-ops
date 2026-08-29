# YouTube Data API v3 / Analytics API v2 — current capability research

Compiled 2026-08-29 for Priority 3A. **Read the confidence caveat before
relying on anything here.**

## Network constraint that shaped this research

This session's egress proxy blocks all `*.google.com` domains outright
(`developers.google.com`, `support.google.com` both returned
`EGRESS_BLOCKED`) — not a page-specific block, a domain-level one. I
could not fetch Google's own documentation directly, so nothing below
is a primary-source read. `WebSearch` (which fetches server-side,
outside this session's proxy) still returned Google's own pages in
results and summarized them, so most of what follows traces back to
Google's docs at least secondhand. Where a claim came only from a
third-party blog and not from anything summarizing Google's own pages,
it's marked **UNVERIFIED** below and should be re-checked from a
network that can actually reach developers.google.com before anyone
relies on it for capacity planning.

## Upload capability (`videos.insert`)

- Requires OAuth 2.0, resumable upload protocol (the video file is the
  request body/media; `snippet` and `status` are the metadata parts).
- Required scope: `https://www.googleapis.com/auth/youtube.upload`
  (broader `.../auth/youtube` also covers it; `.../youtube.force-ssl`
  is the scope used for most read/write Data API calls including
  playlist/caption management).
- **Quota cost**: the long-standing, extensively-documented model
  (stable across YouTube Data API v3's public lifetime, corroborated
  across many independent sources over years) is **1,600 units per
  `videos.insert` call**, against a **default daily project quota of
  10,000 units** — i.e. about 6 uploads/day by default before you'd
  need to request a quota increase.
- **UNVERIFIED**: several 2026-dated marketing/SEO blogs (Blotato,
  bundle.social, postproxy.dev, zernio.com, socialcrawl.dev — none of
  them Google) claim a "June 1, 2026" restructuring that moved
  `videos.insert` into its own separate bucket at 1 unit/call with a
  100-call/day cap, independent of the general 10,000-unit pool. This
  is a suspiciously specific claim from non-authoritative sources, it
  wasn't corroborated by any Google-sourced result, and content-farm
  SEO sites chasing "2026 API guide" search traffic are a known
  pattern for fabricated specifics. **Treat the 1,600-unit model as
  the reliable default assumption for capacity planning** until this
  is confirmed or refuted against the actual Google Cloud Console
  quota page from a network that can reach it.

## Metadata update (`videos.update`) / thumbnails (`thumbnails.set`)

- `videos.update` lets you change title, description, tags, category,
  privacy status, etc. after upload — same `youtube.upload` /
  `youtube.force-ssl` scope territory.
- `thumbnails.set` uploads a custom thumbnail for a video. Long-
  standing, well-documented restriction: **custom thumbnails require
  the channel to be phone-verified** (a channel-level one-time human
  step in YouTube Studio, not something the API can do). This is a
  hard prerequisite Systemary's channel needs to satisfy before this
  adapter's thumbnail step can do anything real.

## Scheduled publishing

- Set `status.privacyStatus = "private"` and `status.publishAt =
  <RFC3339 timestamp>` on upload or via `videos.update`. YouTube
  auto-flips the video to public at that timestamp.
- You cannot set `publishAt` on a video whose `privacyStatus` is
  already `"public"` — scheduling only works through the
  private-then-auto-public path.
- Privacy status enum: `private`, `unlisted`, `public`.

## OAuth scopes (Data API)

| Scope | Purpose |
|---|---|
| `.../auth/youtube` | full account management |
| `.../auth/youtube.force-ssl` | most read/write Data API calls |
| `.../auth/youtube.readonly` | read-only |
| `.../auth/youtube.upload` | upload/manage videos |
| `.../auth/youtubepartner` | content-owner/partner level |
| `.../auth/youtubepartner-channel-audit` | channel audit (partner) |

## OAuth scopes (Analytics API v2)

| Scope | Purpose |
|---|---|
| `.../auth/yt-analytics.readonly` | view activity/engagement metrics |
| `.../auth/yt-analytics-monetary.readonly` | view revenue/ad metrics |

## Refresh-token behavior — this is the one that actually blocks us

Well-documented, long-standing Google OAuth behavior, not YouTube-
specific: an OAuth consent screen left in **Testing** publishing status
is treated as an unverified app, and **every refresh token it issues
expires after exactly 7 days**, plus a hard cap of 100 test users.
Moving the consent screen to **Production** removes the 7-day cap; for
scopes Google classifies as sensitive/restricted, that requires a full
OAuth app verification review (a security assessment Google runs,
timeline typically weeks). `youtube.upload` is a restricted scope, so
this project should expect to go through that review before relying on
a long-lived refresh token in production — a 7-day-expiring token is
fine for the dry-run/manual-test phase this build targets, not for
unattended autonomous publishing.

## Verification/review requirements

- Public-facing/production use of `youtube.upload` requires the OAuth
  consent screen to be verified (out of Testing mode) — see above.
- Requesting a quota increase above the 10,000-unit default requires
  submitting Google's Audit and Quota Extension form; review timeline
  is typically weeks to months per Google's own guidance repeated
  across sources.
- Automated/bulk actions are governed by the YouTube API Services
  Terms of Service and Developer Policies (prohibits deceptive,
  spammy, or abusive automated behavior; YouTube runs its own
  automated abuse detection over API-created content same as any
  other upload).

## YouTube Analytics API v2 — what Priority 3B would use

- Endpoint: `youtubeAnalytics/v2/reports:query` (channel reports) —
  metrics, dimensions, filters, sort as query parameters.
- Scope: `yt-analytics.readonly` for engagement/activity metrics;
  `yt-analytics-monetary.readonly` additionally required for revenue/ad
  metrics.
- Representative metrics: `views`, `estimatedMinutesWatched`, `likes`,
  `comments`, `shares`, `subscribersGained`, plus retention/CTR-shaped
  metrics via the relevant report types.
- Data delay: YouTube Analytics data is not real-time — same
  long-standing behavior as the Data API's own docs describe, typically
  a delay of hours to ~2 days depending on metric and how recent the
  activity is. Exact current delay figures should be re-verified from
  developers.google.com once this session (or a future one) can reach
  it — not confirmed independently in this research pass.
- There's also a separate bulk-download mechanism, the YouTube
  Reporting API v1 (`jobs`/`reports` resources), for large historical
  pulls rather than ad hoc queries — worth considering for Priority 3B
  if per-video daily metrics at scale are needed.

## Bottom line for Priority 3A

Nothing above blocks *building* the adapter and passing a dry run.
What it does mean concretely for this project:
1. A Google Cloud project + YouTube Data API v3 enabled + OAuth client
   (Desktop or Web type) has to exist before any real call can be
   made — none of that exists yet (see the main report).
2. The channel needs one-time phone verification before custom
   thumbnails will work.
3. Until the OAuth consent screen is moved out of Testing (which
   requires a Google review for the `youtube.upload` scope), any
   refresh token this project mints is only good for 7 days — fine
   for the private/unlisted manual test this phase targets, not for
   unattended autonomous publishing later.
4. Default quota (1,600 units/upload ÷ 10,000/day, if that model still
   holds) supports roughly 6 uploads/day without requesting an
   increase — plenty for Systemary's daily-content pacing.
