"""The only module in this codebase that knows YouTube's request shapes.

    ORCHESTRATOR -> PUBLISHING AGENT -> YouTubeAdapter -> YouTube API

SECURITY: real-mode credentials come from environment variables only
(YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN), read
fresh at call time via `credentials_from_env()`. Nothing in this module
reads a credential from a repo file, hardcodes one, logs one, or puts
one in an exception message -- `OAuthCredentials.__repr__` is
overridden specifically so an accidental `print(credentials)` or
traceback can't leak one.

SAFETY: `build_upload_request` allow-lists privacy_status to exactly
{"private", "unlisted"}. There is no parameter, flag, or code path in
this file that can produce a "public" request body. Per the Priority 3A
brief, lifting that is a deliberate future change to this file, not a
runtime option anywhere else in the codebase.

This module has zero hard dependency on google-api-python-client (or
any HTTP library) -- `RealYouTubeClient` is a Protocol; production
wires a real implementation in via `real_client_factory`. That's what
makes dry-run mode (and every test in this package) run with nothing
installed beyond the standard library.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Protocol

from orchestrator.publishing.idempotency import IdempotencyStore

_ALLOWED_PRIVACY_STATUSES = {"private", "unlisted"}


class PrivacyStatus(str, Enum):
    PRIVATE = "private"
    UNLISTED = "unlisted"
    # PUBLIC is deliberately not a member of this enum -- see module docstring.


class YouTubeAdapterError(Exception):
    """Base class for every error this adapter raises."""


class MissingCredentialsError(YouTubeAdapterError):
    pass


class InvalidMetadataError(YouTubeAdapterError):
    pass


class QuotaExceededError(YouTubeAdapterError):
    pass


class ExpiredCredentialsError(YouTubeAdapterError):
    pass


class TransientAPIError(YouTubeAdapterError):
    """Network timeout, 5xx, etc. -- the kind of failure worth retrying."""


class DuplicateUploadPrevented(YouTubeAdapterError):
    """Raised, never silently swallowed, when idempotency blocks a repeat
    upload -- callers see exactly what happened instead of a silent no-op."""

    def __init__(self, idempotency_key: str, existing_video_id: str):
        super().__init__(
            f"upload for {idempotency_key!r} already happened "
            f"(video_id={existing_video_id!r}); refusing to re-upload"
        )
        self.idempotency_key = idempotency_key
        self.existing_video_id = existing_video_id


@dataclass
class YouTubeUploadRequest:
    video_file_path: str
    title: str
    description: str
    tags: list[str] = field(default_factory=list)
    category_id: str = "22"  # People & Blogs -- caller should set the real one
    privacy_status: str = PrivacyStatus.UNLISTED.value
    publish_at: Optional[str] = None  # RFC3339; only valid with privacy_status="private"
    made_for_kids: bool = False
    thumbnail_path: Optional[str] = None

    def validate(self) -> list[str]:
        problems: list[str] = []
        if not self.title or not self.title.strip():
            problems.append("title is empty")
        elif len(self.title) > 100:
            problems.append(f"title exceeds YouTube's 100-character limit ({len(self.title)} chars)")
        if len(self.description) > 5000:
            problems.append(f"description exceeds YouTube's 5000-character limit ({len(self.description)} chars)")
        if self.publish_at and self.privacy_status != PrivacyStatus.PRIVATE.value:
            problems.append("publish_at requires privacy_status='private' (YouTube only schedules private videos)")
        if not self.video_file_path:
            problems.append("video_file_path is empty")
        if self.privacy_status not in _ALLOWED_PRIVACY_STATUSES:
            problems.append(
                f"privacy_status {self.privacy_status!r} is not allowed in this phase "
                f"(only {sorted(_ALLOWED_PRIVACY_STATUSES)} -- public publishing is not yet enabled)"
            )
        return problems


@dataclass
class UploadOutcome:
    dry_run: bool
    request_body: dict[str, Any]
    video_id: Optional[str]  # set only on a real, non-dry-run success
    idempotency_key: str
    reused_existing: bool = False


@dataclass
class OAuthCredentials:
    client_id: str
    client_secret: str
    refresh_token: str

    def __repr__(self) -> str:  # never let a stray print/log leak these
        return "OAuthCredentials(<redacted>)"


class CredentialsProvider(Protocol):
    def __call__(self) -> OAuthCredentials: ...


def credentials_from_env() -> OAuthCredentials:
    """The only sanctioned way to get real credentials into this adapter:
    environment variables, read fresh at call time. Never a file in
    this repo, never a hardcoded value, never printed."""
    client_id = os.environ.get("YOUTUBE_CLIENT_ID")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")
    missing = [
        name for name, val in [
            ("YOUTUBE_CLIENT_ID", client_id),
            ("YOUTUBE_CLIENT_SECRET", client_secret),
            ("YOUTUBE_REFRESH_TOKEN", refresh_token),
        ] if not val
    ]
    if missing:
        raise MissingCredentialsError(
            f"missing environment variable(s): {', '.join(missing)}. "
            "Real (non-dry-run) uploads require these to be set as secrets, "
            "never committed to source. See docs/youtube/SETUP.md."
        )
    return OAuthCredentials(client_id, client_secret, refresh_token)  # type: ignore[arg-type]


class RealYouTubeClient(Protocol):
    """What a real client must support. Implemented in production by a
    thin wrapper around google-api-python-client -- that dependency is
    never imported by this module, only by whatever supplies a
    `real_client_factory` to YouTubeAdapter, so this module (and every
    test in this package) works with nothing beyond the stdlib."""

    def insert_video(self, request_body: dict, media_file_path: str) -> str:
        """Performs the resumable upload; returns the new video's ID."""
        ...

    def set_thumbnail(self, video_id: str, thumbnail_path: str) -> None: ...

    def update_video(self, video_id: str, request_body: dict) -> None: ...


class YouTubeAdapter:
    def __init__(
        self,
        idempotency_store: IdempotencyStore,
        credentials_provider: CredentialsProvider = credentials_from_env,
        real_client_factory=None,  # Callable[[OAuthCredentials], RealYouTubeClient] | None
    ):
        self._store = idempotency_store
        self._credentials_provider = credentials_provider
        self._real_client_factory = real_client_factory

    def build_upload_request(self, req: YouTubeUploadRequest) -> dict[str, Any]:
        if req.privacy_status not in _ALLOWED_PRIVACY_STATUSES:
            raise ValueError(
                f"privacy_status {req.privacy_status!r} is refused in this phase "
                f"-- only {sorted(_ALLOWED_PRIVACY_STATUSES)} are allowed; see module docstring"
            )
        status: dict[str, Any] = {
            "privacyStatus": req.privacy_status,
            "selfDeclaredMadeForKids": req.made_for_kids,
        }
        if req.publish_at:
            status["publishAt"] = req.publish_at
        return {
            "snippet": {
                "title": req.title,
                "description": req.description,
                "tags": req.tags,
                "categoryId": req.category_id,
            },
            "status": status,
        }

    def upload(
        self,
        req: YouTubeUploadRequest,
        idempotency_key: str,
        dry_run: bool = True,
    ) -> UploadOutcome:
        problems = req.validate()
        if problems:
            raise InvalidMetadataError("; ".join(problems))

        existing = self._store.get(idempotency_key)
        if existing is not None:
            raise DuplicateUploadPrevented(idempotency_key, existing["video_id"])

        request_body = self.build_upload_request(req)

        if dry_run:
            return UploadOutcome(
                dry_run=True, request_body=request_body, video_id=None,
                idempotency_key=idempotency_key,
            )

        client = self._get_real_client()
        try:
            video_id = client.insert_video(request_body, req.video_file_path)
        except Exception as exc:  # noqa: BLE001 -- classified below, never swallowed
            raise _classify_client_error(exc) from exc

        # Record success BEFORE the (non-fatal) thumbnail step: the video
        # exists on YouTube now, so a retry must never re-upload it even
        # if the thumbnail step below fails.
        self._store.record(idempotency_key, video_id)

        if req.thumbnail_path:
            try:
                client.set_thumbnail(video_id, req.thumbnail_path)
            except Exception as exc:  # noqa: BLE001
                raise _classify_client_error(exc) from exc

        return UploadOutcome(
            dry_run=False, request_body=request_body, video_id=video_id,
            idempotency_key=idempotency_key,
        )

    def _get_real_client(self) -> RealYouTubeClient:
        if self._real_client_factory is None:
            raise YouTubeAdapterError(
                "no real YouTube client configured for this adapter instance "
                "-- production wiring must supply a real_client_factory "
                "(a thin google-api-python-client wrapper). See docs/youtube/SETUP.md."
            )
        credentials = self._credentials_provider()  # raises MissingCredentialsError if unset
        return self._real_client_factory(credentials)


def _classify_client_error(exc: Exception) -> YouTubeAdapterError:
    """Best-effort mapping of whatever the real client raises into this
    adapter's typed error hierarchy, so errors.py's retry policy can make
    a sane retry/escalate decision without knowing anything about the
    Google client library's own exception types."""
    text = str(exc).lower()
    if "quota" in text:
        return QuotaExceededError(str(exc))
    if any(t in text for t in ("invalid_grant", "unauthorized", "401", "expired")):
        return ExpiredCredentialsError(str(exc))
    if any(t in text for t in ("timeout", "timed out", "connection", "500", "502", "503", "504")):
        return TransientAPIError(str(exc))
    return TransientAPIError(str(exc))
