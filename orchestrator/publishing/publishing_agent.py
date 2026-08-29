"""Publishing Agent: the bridge between a Calendar record and the
YouTube adapter. The only module in this package that knows Airtable
field names (Status, Platform, Topic, Asset Link, ...).

The APPROVED-only, YouTube-only eligibility gate is enforced here in
code (`check_eligibility`), and `execute_publish` calls it before doing
anything else -- a record in IDEA/RESEARCH/SCRIPT/PRODUCTION/REVIEW/
AWAITING_APPROVAL is rejected before the adapter is ever touched, so
this is a hard gate, not a convention someone could accidentally skip.
"""
from __future__ import annotations

from typing import Any

from orchestrator.publishing.youtube_adapter import (
    DuplicateUploadPrevented,
    ExpiredCredentialsError,
    InvalidMetadataError,
    MissingCredentialsError,
    QuotaExceededError,
    TransientAPIError,
    YouTubeAdapter,
    YouTubeAdapterError,
    YouTubeUploadRequest,
)
from orchestrator.schema import AirtableUpdateIntent, Result, Task, TaskStatus

ELIGIBLE_STATUS = "APPROVED"
INELIGIBLE_STATUSES = (
    "IDEA", "RESEARCH", "SCRIPT", "PRODUCTION", "REVIEW", "AWAITING_APPROVAL",
)


class PublishEligibilityError(Exception):
    pass


def check_eligibility(record: dict[str, Any]) -> None:
    """Raises PublishEligibilityError for anything not APPROVED+YouTube.
    This is the hard gate the Priority 3A brief requires: IDEA through
    AWAITING_APPROVAL must never reach YouTube, enforced programmatically."""
    status = record.get("status")
    if status != ELIGIBLE_STATUS:
        raise PublishEligibilityError(
            f"record {record.get('id')!r} has status {status!r}, not "
            f"{ELIGIBLE_STATUS!r} -- publishing is only allowed from APPROVED."
        )
    platform = (record.get("platform") or "").strip().lower()
    if platform not in ("youtube", "both"):
        raise PublishEligibilityError(
            f"record {record.get('id')!r} has platform {record.get('platform')!r}, which doesn't include YouTube"
        )


def validate_metadata(record: dict[str, Any]) -> list[str]:
    """TEST 1 step 5: validate title/description/metadata before ever
    routing to the adapter. Returns a list of problems; empty = clean."""
    problems: list[str] = []
    if not record.get("topic"):
        problems.append("missing Topic (used as the video title)")
    if not record.get("asset_link"):
        problems.append("missing Asset Link (no produced video file to upload)")
    if not record.get("notes") and not record.get("caption"):
        problems.append("no Notes/Caption available to build a description from")
    return problems


def build_upload_request(record: dict[str, Any]) -> YouTubeUploadRequest:
    # Deliberately NOT truncated to YouTube's 100-char title limit here --
    # an over-length Topic is a real metadata problem the QC/content-strategy
    # step upstream should have caught. Silently truncating would hide it;
    # YouTubeUploadRequest.validate() surfaces it as InvalidMetadataError
    # instead, per the Priority 3A brief's "validate title/description/
    # metadata" test step.
    return YouTubeUploadRequest(
        video_file_path=record.get("asset_link", ""),
        title=record.get("topic") or "",
        description=record.get("caption") or record.get("notes") or "",
        tags=[record["content_pillar"]] if record.get("content_pillar") else [],
        privacy_status="unlisted",  # Priority 3A: never anything but private/unlisted
        thumbnail_path=record.get("thumbnail_path"),
    )


def execute_publish(
    record: dict[str, Any],
    adapter: YouTubeAdapter,
    task: Task,
    dry_run: bool = True,
) -> Result:
    """The bridge `agents.AGENTS["publishing"]` would be dispatched to
    call in production once enabled. Every path returns a Result --
    never raises out to a caller, matching the no-silent-failure rule
    the rest of this orchestrator follows."""
    try:
        check_eligibility(record)
    except PublishEligibilityError as exc:
        return _failed(task, [str(exc)], next_action="not eligible for publishing -- see error")

    metadata_problems = validate_metadata(record)
    if metadata_problems:
        return _failed(task, metadata_problems, next_action="fix metadata, then retry")

    upload_req = build_upload_request(record)
    idempotency_key = f"calendar:{record['id']}"

    try:
        outcome = adapter.upload(upload_req, idempotency_key, dry_run=dry_run)
    except DuplicateUploadPrevented as exc:
        # Not a failure: the desired end state (exactly one upload) already
        # holds. Distinguished from a fresh success via reused_existing so
        # tests/callers can tell "uploaded this run" from "correctly skipped".
        return Result(
            task_id=task.task_id, agent=task.agent, status=TaskStatus.SUCCEEDED,
            output={"video_id": exc.existing_video_id, "reused_existing": True},
            evidence=[f"idempotency: {exc}"], errors=[],
            airtable_updates=[],  # already written on the original successful run
            next_recommended_action=None,
        )
    except InvalidMetadataError as exc:
        return _failed(task, [f"InvalidMetadataError: {exc}"], next_action="fix metadata, then retry")
    except MissingCredentialsError as exc:
        return _failed(task, [f"MissingCredentialsError: {exc}"],
                        next_action="human: set YOUTUBE_CLIENT_ID/YOUTUBE_CLIENT_SECRET/"
                                    "YOUTUBE_REFRESH_TOKEN as secrets, never in source")
    except ExpiredCredentialsError as exc:
        return _failed(task, [f"ExpiredCredentialsError: {exc}"],
                        next_action="human: OAuth token expired/revoked -- re-authorize")
    except QuotaExceededError as exc:
        return _failed(task, [f"QuotaExceededError: {exc}"],
                        next_action="retry after daily quota reset, or request a quota increase")
    except TransientAPIError as exc:
        return _failed(task, [f"TransientAPIError: {exc}"], next_action="retry -- likely transient")
    except YouTubeAdapterError as exc:
        return _failed(task, [f"{type(exc).__name__}: {exc}"], next_action="human review needed")

    evidence = [f"{'DRY RUN' if dry_run else 'LIVE'} upload request built: {outcome.request_body}"]
    airtable_updates: list[AirtableUpdateIntent] = []
    if not dry_run:
        airtable_updates.append(AirtableUpdateIntent(
            table="Calendar",
            record_id=record["id"],
            fields={
                "Status": "SCHEDULED",
                "Published URL": f"https://youtu.be/{outcome.video_id}",
            },
        ))
        evidence.append(f"uploaded: video_id={outcome.video_id}")

    return Result(
        task_id=task.task_id, agent=task.agent, status=TaskStatus.SUCCEEDED,
        output={"video_id": outcome.video_id, "request_body": outcome.request_body, "dry_run": dry_run},
        evidence=evidence, errors=[], airtable_updates=airtable_updates,
        next_recommended_action=(
            "dry run only -- no upload performed, nothing on YouTube" if dry_run
            else "verify the upload on YouTube, then advance to PUBLISHED once confirmed live"
        ),
    )


def _failed(task: Task, errors: list[str], next_action: str) -> Result:
    return Result(
        task_id=task.task_id, agent=task.agent, status=TaskStatus.FAILED,
        output={}, evidence=[], errors=errors, airtable_updates=[],
        next_recommended_action=next_action,
    )
