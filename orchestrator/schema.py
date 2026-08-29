"""Task/Result envelope: the standard structure every agent call uses.

Nothing in this module talks to Airtable, Notion, or Drive. It is the
contract between the orchestrator and an agent execution function,
whatever that function turns out to be (a live Claude subagent call, or
the deterministic simulator used in tests).
"""
from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class ApprovalRequirement(str, Enum):
    """How much human sign-off a task needs before/after execution."""

    NONE = "none"                # proceed autonomously, no human involvement needed
    NOTIFY = "notify"            # proceed autonomously, tell the owner what happened
    REQUIRED = "required"        # do not execute (or do not take effect) until the owner approves


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED_ON_APPROVAL = "blocked_on_approval"
    TIMED_OUT = "timed_out"
    ESCALATED = "escalated"


@dataclass
class AirtableUpdateIntent:
    """A proposed write. In dry-run mode these are recorded, not applied."""

    table: str
    record_id: Optional[str]     # None means "create a new record"
    fields: dict[str, Any]
    applied: bool = False        # orchestrator flips this to True only on a real, non-dry-run apply


@dataclass
class Task:
    agent: str
    objective: str
    inputs: dict[str, Any]
    constraints: list[str]
    expected_output: str
    approval_requirement: ApprovalRequirement
    task_id: str = field(default_factory=lambda: f"task_{uuid.uuid4().hex[:12]}")
    created_at: str = field(default_factory=_now)
    dry_run: bool = True
    priority_score: float = 0.0
    priority_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["approval_requirement"] = self.approval_requirement.value
        return d


@dataclass
class Result:
    task_id: str
    agent: str
    status: TaskStatus
    output: dict[str, Any]
    evidence: list[str]
    errors: list[str]
    airtable_updates: list[AirtableUpdateIntent]
    next_recommended_action: Optional[str]
    completed_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @property
    def ok(self) -> bool:
        return self.status == TaskStatus.SUCCEEDED
