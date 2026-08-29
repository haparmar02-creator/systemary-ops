import unittest

from orchestrator.publishing.idempotency import InMemoryIdempotencyStore
from orchestrator.publishing.publishing_agent import (
    build_upload_request,
    check_eligibility,
    execute_publish,
    validate_metadata,
    PublishEligibilityError,
    INELIGIBLE_STATUSES,
)
from orchestrator.publishing.youtube_adapter import (
    DuplicateUploadPrevented,
    ExpiredCredentialsError,
    InvalidMetadataError,
    MissingCredentialsError,
    QuotaExceededError,
    TransientAPIError,
    YouTubeAdapter,
    YouTubeUploadRequest,
)
from orchestrator.schema import ApprovalRequirement, Task, TaskStatus


def make_task() -> Task:
    return Task(
        agent="publishing", objective="publish an approved video", inputs={},
        constraints=[], expected_output="uploaded or a clear reason it wasn't",
        approval_requirement=ApprovalRequirement.NONE,
    )


def approved_record(**overrides) -> dict:
    record = {
        "id": "rec_test01",
        "status": "APPROVED",
        "platform": "YouTube",
        "topic": "I automated a real client's invoice reminders",
        "asset_link": "/local/path/to/final_video.mp4",
        "notes": "clean pass",
        "content_pillar": "Build-Along",
    }
    record.update(overrides)
    return record


class SpyClient:
    """Fails the test if insert_video is ever called -- used to prove
    the eligibility/metadata gates block *before* touching the adapter."""

    def insert_video(self, request_body, media_file_path):
        raise AssertionError("insert_video must never be called for an ineligible/invalid record")

    def set_thumbnail(self, video_id, thumbnail_path):
        raise AssertionError("set_thumbnail must never be called")

    def update_video(self, video_id, request_body):
        raise AssertionError("update_video must never be called")


class FakeYouTubeClient:
    """Deterministic stand-in for google-api-python-client, used only in
    tests. `next_video_id` / `raise_on_insert` let each test script
    exactly one call's outcome."""

    def __init__(self, next_video_id="yt_fake123", raise_on_insert=None):
        self.next_video_id = next_video_id
        self.raise_on_insert = raise_on_insert
        self.insert_calls = 0
        self.thumbnail_calls = 0

    def insert_video(self, request_body, media_file_path):
        self.insert_calls += 1
        if self.raise_on_insert:
            raise self.raise_on_insert
        return self.next_video_id

    def set_thumbnail(self, video_id, thumbnail_path):
        self.thumbnail_calls += 1

    def update_video(self, video_id, request_body):
        pass


def real_adapter(store, client, credentials_provider=lambda: object()):
    return YouTubeAdapter(
        idempotency_store=store,
        credentials_provider=credentials_provider,
        real_client_factory=lambda creds: client,
    )


class Test1DryRun(unittest.TestCase):
    """TEST 1 from the Priority 3A brief: read the record, verify
    eligibility, verify required fields, validate metadata, route to the
    adapter in dry-run mode, produce the exact request, upload nothing."""

    def test_dry_run_produces_exact_request_and_uploads_nothing(self):
        store = InMemoryIdempotencyStore()
        adapter = YouTubeAdapter(idempotency_store=store)  # no real_client_factory at all
        task = make_task()
        record = approved_record()

        result = execute_publish(record, adapter, task, dry_run=True)

        self.assertEqual(result.status, TaskStatus.SUCCEEDED)
        self.assertIsNone(result.output["video_id"])
        self.assertTrue(result.output["dry_run"])
        body = result.output["request_body"]
        self.assertEqual(body["snippet"]["title"], record["topic"])
        self.assertEqual(body["status"]["privacyStatus"], "unlisted")
        self.assertNotIn("publishAt", body["status"])
        self.assertEqual(result.airtable_updates, [])  # nothing written, dry run
        self.assertIn("DRY RUN", result.evidence[0])
        self.assertIsNone(store.get(f"calendar:{record['id']}"))  # dry run never touches idempotency


class EligibilityGateTest(unittest.TestCase):
    """The approval gate must be enforced programmatically -- IDEA through
    AWAITING_APPROVAL must never reach the adapter."""

    def test_every_ineligible_status_is_rejected_before_touching_adapter(self):
        store = InMemoryIdempotencyStore()
        adapter = YouTubeAdapter(idempotency_store=store, real_client_factory=lambda c: SpyClient())
        for status in INELIGIBLE_STATUSES:
            with self.subTest(status=status):
                record = approved_record(status=status)
                result = execute_publish(record, adapter, make_task(), dry_run=False)
                self.assertEqual(result.status, TaskStatus.FAILED)
                self.assertIn(status, result.errors[0])

    def test_check_eligibility_raises_directly(self):
        with self.assertRaises(PublishEligibilityError):
            check_eligibility(approved_record(status="SCRIPT"))

    def test_non_youtube_platform_is_rejected(self):
        store = InMemoryIdempotencyStore()
        adapter = YouTubeAdapter(idempotency_store=store, real_client_factory=lambda c: SpyClient())
        record = approved_record(platform="Instagram")
        result = execute_publish(record, adapter, make_task(), dry_run=False)
        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertIn("Instagram", result.errors[0])

    def test_both_platform_is_eligible(self):
        check_eligibility(approved_record(platform="Both"))  # must not raise


class MetadataValidationTest(unittest.TestCase):
    def test_missing_asset_link_blocks_before_adapter(self):
        store = InMemoryIdempotencyStore()
        adapter = YouTubeAdapter(idempotency_store=store, real_client_factory=lambda c: SpyClient())
        record = approved_record(asset_link=None)
        result = execute_publish(record, adapter, make_task(), dry_run=False)
        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertTrue(any("Asset Link" in e for e in result.errors))

    def test_missing_topic_blocks(self):
        problems = validate_metadata(approved_record(topic=""))
        self.assertTrue(any("Topic" in p for p in problems))

    def test_clean_record_has_no_problems(self):
        self.assertEqual(validate_metadata(approved_record()), [])


class PrivacyStatusGuardTest(unittest.TestCase):
    """Never Public: this phase hard-refuses anything but private/unlisted,
    in code, not just by convention."""

    def test_public_request_is_refused_by_the_adapter(self):
        store = InMemoryIdempotencyStore()
        adapter = YouTubeAdapter(idempotency_store=store)
        req = YouTubeUploadRequest(
            video_file_path="/x.mp4", title="t", description="d", privacy_status="public",
        )
        with self.assertRaises(ValueError):
            adapter.build_upload_request(req)

    def test_public_request_fails_validation_too(self):
        req = YouTubeUploadRequest(
            video_file_path="/x.mp4", title="t", description="d", privacy_status="public",
        )
        problems = req.validate()
        self.assertTrue(any("privacy_status" in p for p in problems))

    def test_default_request_from_a_record_is_unlisted_never_public(self):
        req = build_upload_request(approved_record())
        self.assertEqual(req.privacy_status, "unlisted")


class IdempotencyTest(unittest.TestCase):
    """RUN -> SUCCESS; RUN SAME TASK AGAIN -> NO DUPLICATE UPLOAD."""

    def test_second_run_of_the_same_record_does_not_reupload(self):
        store = InMemoryIdempotencyStore()
        client = FakeYouTubeClient(next_video_id="yt_abc123")
        adapter = real_adapter(store, client)
        record = approved_record()

        first = execute_publish(record, adapter, make_task(), dry_run=False)
        self.assertEqual(first.status, TaskStatus.SUCCEEDED)
        self.assertEqual(first.output["video_id"], "yt_abc123")
        self.assertEqual(client.insert_calls, 1)
        self.assertEqual(first.airtable_updates[0].fields["Status"], "SCHEDULED")

        second = execute_publish(record, adapter, make_task(), dry_run=False)
        self.assertEqual(second.status, TaskStatus.SUCCEEDED)
        self.assertTrue(second.output["reused_existing"])
        self.assertEqual(second.output["video_id"], "yt_abc123")
        self.assertEqual(client.insert_calls, 1)  # still 1 -- no second upload
        self.assertEqual(second.airtable_updates, [])  # nothing new to write

    def test_dry_run_never_records_idempotency_so_it_cannot_block_the_real_run(self):
        store = InMemoryIdempotencyStore()
        record = approved_record()
        dry_adapter = YouTubeAdapter(idempotency_store=store)
        execute_publish(record, dry_adapter, make_task(), dry_run=True)
        self.assertIsNone(store.get(f"calendar:{record['id']}"))

        client = FakeYouTubeClient()
        real = real_adapter(store, client)
        result = execute_publish(record, real, make_task(), dry_run=False)
        self.assertEqual(result.status, TaskStatus.SUCCEEDED)
        self.assertFalse(result.output.get("reused_existing", False))

    def test_adapter_raises_duplicate_directly(self):
        store = InMemoryIdempotencyStore()
        store.record("calendar:rec_x", "yt_existing")
        adapter = real_adapter(store, FakeYouTubeClient())
        with self.assertRaises(DuplicateUploadPrevented):
            adapter.upload(
                YouTubeUploadRequest(video_file_path="/x.mp4", title="t", description="d"),
                "calendar:rec_x", dry_run=False,
            )


class FailureHandlingTest(unittest.TestCase):
    """Each case must produce an error state + a concrete next_recommended_action.
    No silent failures."""

    def _run_with_error(self, exc: Exception):
        store = InMemoryIdempotencyStore()
        client = FakeYouTubeClient(raise_on_insert=exc)
        adapter = real_adapter(store, client)
        result = execute_publish(approved_record(), adapter, make_task(), dry_run=False)
        return result

    def test_invalid_metadata_title_too_long(self):
        store = InMemoryIdempotencyStore()
        adapter = real_adapter(store, FakeYouTubeClient())
        record = approved_record(topic="x" * 200)
        result = execute_publish(record, adapter, make_task(), dry_run=False)
        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertTrue(any("InvalidMetadataError" in e for e in result.errors))
        self.assertIsNotNone(result.next_recommended_action)

    def test_expired_oauth(self):
        result = self._run_with_error(Exception("invalid_grant: token has been expired or revoked"))
        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertTrue(any("ExpiredCredentialsError" in e for e in result.errors))
        self.assertIn("re-authorize", result.next_recommended_action)

    def test_quota_error(self):
        result = self._run_with_error(Exception("quotaExceeded: The request cannot be completed"))
        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertTrue(any("QuotaExceededError" in e for e in result.errors))
        self.assertIn("quota", result.next_recommended_action.lower())

    def test_network_timeout(self):
        result = self._run_with_error(TimeoutError("Connection timed out"))
        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertTrue(any("TransientAPIError" in e for e in result.errors))
        self.assertIn("retry", result.next_recommended_action.lower())

    def test_generic_api_error_5xx(self):
        result = self._run_with_error(Exception("500 Internal Server Error"))
        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertTrue(any("TransientAPIError" in e for e in result.errors))

    def test_missing_credentials_never_calls_the_real_client(self):
        store = InMemoryIdempotencyStore()
        client = SpyClient()

        def raise_missing():
            raise MissingCredentialsError("missing environment variable(s): YOUTUBE_CLIENT_ID")

        adapter = YouTubeAdapter(
            idempotency_store=store, credentials_provider=raise_missing,
            real_client_factory=lambda creds: client,
        )
        result = execute_publish(approved_record(), adapter, make_task(), dry_run=False)
        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertTrue(any("MissingCredentialsError" in e for e in result.errors))
        self.assertIn("secrets", result.next_recommended_action)

    def test_no_real_client_configured_at_all_fails_cleanly(self):
        store = InMemoryIdempotencyStore()
        adapter = YouTubeAdapter(idempotency_store=store)  # no real_client_factory
        result = execute_publish(approved_record(), adapter, make_task(), dry_run=False)
        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertIsNotNone(result.next_recommended_action)

    def test_thumbnail_failure_does_not_undo_a_successful_upload(self):
        store = InMemoryIdempotencyStore()
        client = FakeYouTubeClient()
        client.set_thumbnail = lambda *a, **k: (_ for _ in ()).throw(Exception("500 thumbnail service down"))
        adapter = real_adapter(store, client)
        record = approved_record(thumbnail_path="/thumb.png")

        result = execute_publish(record, adapter, make_task(), dry_run=False)
        self.assertEqual(result.status, TaskStatus.FAILED)  # this call reports the thumbnail failure...
        # ...but the video WAS recorded as uploaded, so a retry won't re-upload it:
        self.assertIsNotNone(store.get(f"calendar:{record['id']}"))


class CredentialsSecurityTest(unittest.TestCase):
    def test_credentials_repr_never_leaks_secrets(self):
        from orchestrator.publishing.youtube_adapter import OAuthCredentials
        creds = OAuthCredentials(client_id="id123", client_secret="SUPERSECRET", refresh_token="REFRESHTOKEN")
        self.assertNotIn("SUPERSECRET", repr(creds))
        self.assertNotIn("REFRESHTOKEN", repr(creds))
        self.assertNotIn("id123", repr(creds))

    def test_credentials_from_env_reports_missing_vars_without_leaking_present_ones(self):
        import os
        from orchestrator.publishing.youtube_adapter import credentials_from_env
        saved = {k: os.environ.pop(k, None) for k in
                 ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN")}
        try:
            with self.assertRaises(MissingCredentialsError) as ctx:
                credentials_from_env()
            self.assertIn("YOUTUBE_CLIENT_ID", str(ctx.exception))
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v


if __name__ == "__main__":
    unittest.main()
