# Setting up real YouTube publishing (human-controlled, out of scope for this build)

Nothing in this repo can do these steps for you -- they require your
Google account, a browser, and business decisions (which channel,
what branding). This is exactly the boundary the Priority 3A brief
draws between what Claude can build and what stays human-controlled.

1. **Google Cloud project.** Create one (or reuse an existing one) at
   console.cloud.google.com. Enable "YouTube Data API v3" for it.
2. **OAuth consent screen.** Configure it for the project. It starts in
   **Testing** mode -- fine for the private/unlisted manual test this
   phase targets, but refresh tokens it issues expire after 7 days (see
   docs/youtube/API_RESEARCH.md). Moving to Production for unattended
   use later requires a Google verification review for the
   `youtube.upload` scope.
3. **OAuth client.** Create an OAuth 2.0 Client ID (Desktop app type is
   simplest for a one-time manual authorization). Download the
   client_id/client_secret.
4. **Channel verification.** Verify the Systemary channel by phone in
   YouTube Studio -- required before `thumbnails.set` will work.
5. **Run the OAuth consent flow once**, manually, to mint a refresh
   token (e.g. `google-auth-oauthlib`'s installed-app flow, run
   locally on your machine -- not something this session can do, since
   it requires an interactive browser login as you).
6. **Store the three secrets as environment variables** wherever this
   orchestrator actually runs -- `YOUTUBE_CLIENT_ID`,
   `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`. Never in a file in
   this repo. `.gitignore` already blocks common credential filename
   patterns (`*token*.json`, `client_secret*.json`, `.env*`, `.state/`)
   as a backstop, but the actual rule is: these three values only ever
   live in a secrets manager or environment, never on disk in this repo.
7. **Wire a real client.** `YouTubeAdapter` takes a `real_client_factory`
   -- production code supplies a thin wrapper around
   `google-api-python-client`'s `build("youtube", "v3", credentials=...)`
   that implements the three methods `RealYouTubeClient` declares
   (`insert_video`, `set_thumbnail`, `update_video`). Nothing in this
   package imports that library itself, so it isn't a dependency of the
   orchestrator's core -- only of whatever supplies the real factory.

Once all seven are done, `orchestrator/publishing/publishing_agent.py`
and `youtube_adapter.py` are already built to use them (`dry_run=False`
+ `credentials_from_env` + a real `real_client_factory`) -- nothing in
those two files needs to change for that to work. What's still owed
before that path is exercised for real: TEST 2 (private/unlisted live
upload) from the Priority 3A brief, which is currently blocked exactly
here -- see the main report.
