"""The ONLY module in this codebase that imports google-api-python-client
or google-auth. Satisfies `youtube_adapter.RealYouTubeClient`. Nothing
else under orchestrator/ imports these libraries directly -- that's
what keeps the adapter (and everything above it) testable without them
installed, per the ORCHESTRATOR -> PUBLISHING AGENT -> YOUTUBE ADAPTER
-> YouTube API separation.

This module never logs a credential. `google.oauth2.credentials.Credentials`
holds the refresh token in memory only, passed straight to the client
library; nothing here prints it, and `OAuthCredentials.__repr__` (in
youtube_adapter.py) is already redacted for anything upstream that
might try.
"""
from __future__ import annotations

from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

from orchestrator.publishing.youtube_adapter import OAuthCredentials

_TOKEN_URI = "https://oauth2.googleapis.com/token"
_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _build_service(credentials: OAuthCredentials):
    google_creds = Credentials(
        token=None,  # forces an immediate refresh using the refresh_token below
        refresh_token=credentials.refresh_token,
        client_id=credentials.client_id,
        client_secret=credentials.client_secret,
        token_uri=_TOKEN_URI,
        scopes=_SCOPES,
    )
    return build("youtube", "v3", credentials=google_creds, cache_discovery=False)


class GoogleYouTubeClient:
    """Real implementation of youtube_adapter.RealYouTubeClient."""

    def __init__(self, credentials: OAuthCredentials):
        self._service = _build_service(credentials)

    def insert_video(self, request_body: dict[str, Any], media_file_path: str) -> str:
        media = MediaFileUpload(media_file_path, chunksize=-1, resumable=True)
        request = self._service.videos().insert(
            part="snippet,status", body=request_body, media_body=media,
        )
        response = None
        while response is None:
            _status, response = request.next_chunk()
        return response["id"]

    def set_thumbnail(self, video_id: str, thumbnail_path: str) -> None:
        self._service.thumbnails().set(
            videoId=video_id, media_body=MediaFileUpload(thumbnail_path),
        ).execute()

    def update_video(self, video_id: str, request_body: dict[str, Any]) -> None:
        body = {"id": video_id, **request_body}
        self._service.videos().update(
            part=",".join(request_body.keys()), body=body,
        ).execute()

    def get_authenticated_channel(self) -> dict[str, Any]:
        """Phase 6 auth verification: confirms the refresh token works and
        the YouTube API client can be constructed, by querying the
        authorized account's own channel. Returns only non-sensitive
        channel info (id, title) -- never touches the token itself."""
        response = self._service.channels().list(part="snippet", mine=True).execute()
        items = response.get("items", [])
        if not items:
            return {"channel_found": False}
        channel = items[0]
        return {
            "channel_found": True,
            "channel_id": channel.get("id"),
            "channel_title": channel.get("snippet", {}).get("title"),
        }


def real_client_factory(credentials: OAuthCredentials) -> GoogleYouTubeClient:
    return GoogleYouTubeClient(credentials)


def verify_authentication(credentials: OAuthCredentials) -> dict[str, Any]:
    """Phase 6: load credentials, refresh, construct the client, query
    the channel. Never uploads anything. Never returns a token."""
    try:
        client = GoogleYouTubeClient(credentials)
        info = client.get_authenticated_channel()
        return {"status": "PASS", **info}
    except HttpError as exc:
        return {"status": "FAIL", "error": f"HttpError {exc.resp.status}: {exc.reason}"}
    except Exception as exc:  # noqa: BLE001 -- surfaced to the caller, never swallowed
        return {"status": "FAIL", "error": f"{type(exc).__name__}: {exc}"}
