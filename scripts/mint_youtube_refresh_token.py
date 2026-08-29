#!/usr/bin/env python3
"""Mint a YouTube Data API v3 refresh token.

RUN THIS ON YOUR OWN MACHINE (the one with the browser and the
downloaded OAuth client JSON) -- it CANNOT run inside a remote/cloud
Claude Code session. The Desktop OAuth client's redirect goes to
http://localhost:<port>, which only your own machine's browser can
reach; that's an inherent property of the OAuth loopback flow, not a
limitation of this script.

Setup (once, on your Mac):

    python3 -m venv .venv && source .venv/bin/activate
    pip install google-auth-oauthlib

Run:

    python3 scripts/mint_youtube_refresh_token.py \
        --client-secret ~/Downloads/<your_downloaded_client_secret_file>.json

This opens your default browser to Google's consent screen. Log in as
the account that owns/manages the Systemary YouTube channel and
approve access.

If you see "Google hasn't verified this app" -- expected, since the
OAuth consent screen is still in Testing mode. Click "Advanced", then
"Go to <your project name> (unsafe)". That warning appears because the
app hasn't gone through Google's review yet, not because anything is
actually wrong -- it's normal for a project you created and control,
being authorized by its own owner.

When it finishes, this prints your client_id (not a secret by itself)
and the new refresh_token to THIS terminal, on YOUR machine, under
your control -- not to any Claude Code session, not to any chat, not
to any file. Copy these three values into wherever you're setting this
project's environment variables:

    YOUTUBE_CLIENT_ID       (printed below)
    YOUTUBE_CLIENT_SECRET   (the "client_secret" field in the JSON you downloaded)
    YOUTUBE_REFRESH_TOKEN   (printed below)
"""
from __future__ import annotations

import argparse
import json
import sys

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    sys.exit(
        "google-auth-oauthlib is not installed. Run:\n"
        "  python3 -m venv .venv && source .venv/bin/activate\n"
        "  pip install google-auth-oauthlib\n"
        "then re-run this script inside that venv."
    )

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--client-secret", required=True, help="path to the downloaded OAuth client JSON")
    args = parser.parse_args()

    with open(args.client_secret) as f:
        client_config = json.load(f)
    client_id = client_config.get("installed", client_config.get("web", {})).get("client_id")
    if not client_id:
        sys.exit(f"could not find a client_id in {args.client_secret} -- is this the right file?")

    flow = InstalledAppFlow.from_client_secrets_file(args.client_secret, SCOPES)
    # Starts a temporary local web server to receive the OAuth redirect --
    # this is the step that requires running on your own machine.
    credentials = flow.run_local_server(port=0)

    if not credentials.refresh_token:
        sys.exit(
            "Google did not return a refresh token. This usually means you've "
            "already authorized this app before and Google is reusing an old "
            "grant. Revoke access at https://myaccount.google.com/permissions "
            "for this app, then re-run this script."
        )

    print("\n=== Authorization complete ===")
    print("Store these as environment variables wherever this project reads")
    print("them from. Do not paste them into a chat message or commit them.\n")
    print(f"YOUTUBE_CLIENT_ID={client_id}")
    print("YOUTUBE_CLIENT_SECRET=<the \"client_secret\" field in your downloaded JSON file>")
    print(f"YOUTUBE_REFRESH_TOKEN={credentials.refresh_token}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
