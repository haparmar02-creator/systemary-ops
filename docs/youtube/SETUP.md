# Setting up real YouTube publishing

## Current state (as of 2026-08-29)

Done, by the account owner, outside this repo:
- [x] Google Cloud project: "Systemary YouTube" (`systemary-youtube`)
- [x] YouTube Data API v3: enabled
- [x] OAuth consent screen: created, audience External
- [x] OAuth client: "Systemary YouTube Automation", type Desktop, JSON downloaded

Done, by Claude, in this repo:
- [x] `orchestrator/publishing/youtube_adapter.py` / `publishing_agent.py` /
      `idempotency.py` — the dry-run-capable adapter, eligibility gate,
      idempotency store (Priority 3A first pass)
- [x] `google-api-python-client`, `google-auth-oauthlib`, `google-auth`
      installed in a project-local venv (`.venv/`, gitignored) — the
      system Python's `cryptography` package was broken (missing native
      `_cffi_backend`), so these live in an isolated venv instead of
      touching system packages
- [x] `orchestrator/publishing/google_client.py` — the real
      `RealYouTubeClient` implementation (`GoogleYouTubeClient`), the
      only module in this codebase that imports
      `google-api-python-client`. Wires directly into the existing
      adapter via `real_client_factory` with no changes needed to
      `youtube_adapter.py` or `publishing_agent.py`.
- [x] `scripts/mint_youtube_refresh_token.py` — a script that mints a
      refresh token via the OAuth loopback flow. **Must run on your own
      machine, not in a Claude Code remote session** — see "Why this
      step can't run here" below.
- [x] `python3 -m orchestrator.cli youtube-auth-check` — verifies real
      credentials work (Phase 6) without uploading anything

**Not done — blocks TEST 2 (private/unlisted live upload):**
- [ ] Refresh token minted
- [ ] `YOUTUBE_CLIENT_ID` / `YOUTUBE_CLIENT_SECRET` / `YOUTUBE_REFRESH_TOKEN`
      set as environment variables wherever this code actually runs
- [ ] Channel phone verification (needed for thumbnails only, not for
      TEST 1/TEST 2 themselves)
- [ ] A harmless test video file for TEST 2

## Why the refresh-token step can't run in this session

This Claude Code session runs in an isolated cloud container — it has
no access to your Mac's filesystem, and more importantly, a Desktop
OAuth client's authorization redirect goes to `http://localhost:<port>`,
which only a browser on the *same machine* as the listening process can
reach. Since your browser is on your Mac, the process receiving that
redirect has to run on your Mac too. There's no way around this that
doesn't compromise the flow — it's how OAuth's loopback redirect is
designed to work, not a gap in this build.

## What you need to do

1. On your Mac, in a terminal:
   ```
   python3 -m venv .venv && source .venv/bin/activate
   pip install google-auth-oauthlib
   python3 scripts/mint_youtube_refresh_token.py --client-secret ~/Downloads/<your_downloaded_file>.json
   ```
   (pull this repo, or just copy `scripts/mint_youtube_refresh_token.py`
   to your Mac — it has no dependency on the rest of the repo.)
2. Your browser opens to Google's consent screen. Log in as the account
   that manages the Systemary channel and approve. If you see "Google
   hasn't verified this app" — expected, since the consent screen is in
   Testing mode. Click **Advanced**, then **Go to Systemary YouTube
   Automation (unsafe)**. This warning is normal for your own
   self-authorized project; nothing is actually wrong.
3. The script prints your `client_id` and a new `refresh_token` to your
   own terminal. Your `client_secret` is the `client_secret` field in
   the JSON file you already downloaded.
4. Set all three as environment variables in this Claude Code
   environment's own configuration (its settings, outside this chat —
   the same place environment variables and setup scripts for this
   environment are configured; see
   https://code.claude.com/docs/en/claude-code-on-the-web) — not by
   pasting them into this conversation. A new session/container may be
   needed for the environment to pick them up.
5. Tell me once that's done (a confirmation, not the values) and
   provide (or point me to) a harmless test video file. I'll pick up
   from there: `youtube-auth-check`, then TEST 2.

## Architecture (unchanged, confirmed still isolated)

    ORCHESTRATOR -> PUBLISHING AGENT -> YOUTUBE ADAPTER -> YouTube API

`youtube_adapter.py` still has zero import of `google-api-python-client`
— only `google_client.py` does, and only `google_client.py` and the CLI
import it, and only when a real (non-dry-run) call is actually being
made. `orchestrator.py` has no YouTube-specific code anywhere in it.
