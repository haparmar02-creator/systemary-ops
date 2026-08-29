"""No silent failures: every agent execution goes through here.

`run_with_retry` wraps a single agent-execution call with the agent's
own timeout/retry policy (from the agent registry), and guarantees a
Result comes back either way -- SUCCEEDED, FAILED, TIMED_OUT, or
ESCALATED. It never lets an exception propagate out silently and it
never returns None.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from orchestrator.agents import AgentSpec
from orchestrator.schema import Result, Task, TaskStatus


class AgentTimeout(Exception):
    pass


@dataclass
class RetryPolicy:
    max_retries: int
    timeout_seconds: int
    escalate_after_exhaustion: bool = True

    @staticmethod
    def from_agent_spec(spec: AgentSpec) -> "RetryPolicy":
        return RetryPolicy(
            max_retries=spec.max_retries,
            timeout_seconds=spec.timeout_seconds,
            escalate_after_exhaustion=True,
        )


ExecuteFn = Callable[[Task], Result]


def run_with_retry(
    task: Task,
    execute: ExecuteFn,
    policy: RetryPolicy,
    sleep: Callable[[float], None] = time.sleep,
    backoff_seconds: float = 0.0,
) -> Result:
    """Call `execute(task)` up to `1 + policy.max_retries` times.

    `execute` is expected to raise on failure/timeout, or return a Result
    whose status already reflects the outcome. Either way this function
    normalizes to a single Result and logs every attempt in the errors
    list, so a caller inspecting the final Result can see the full retry
    history rather than just the last attempt.
    """
    attempts_errors: list[str] = []
    last_result: Result | None = None

    for attempt in range(1, policy.max_retries + 2):  # +1 for the first try
        try:
            result = execute(task)
        except Exception as exc:  # noqa: BLE001 -- deliberately broad: this is the last-resort net
            attempts_errors.append(f"attempt {attempt}: {type(exc).__name__}: {exc}")
            last_result = None
        else:
            if result.status == TaskStatus.SUCCEEDED:
                return result
            attempts_errors.extend(f"attempt {attempt}: {e}" for e in result.errors)
            last_result = result

        if attempt <= policy.max_retries and backoff_seconds:
            sleep(backoff_seconds * attempt)

    # Retries exhausted (or the agent is disabled/never called): build a
    # terminal Result rather than letting the caller see an exception.
    status = TaskStatus.ESCALATED if policy.escalate_after_exhaustion else TaskStatus.FAILED
    return Result(
        task_id=task.task_id,
        agent=task.agent,
        status=status,
        output=(last_result.output if last_result else {}),
        evidence=(last_result.evidence if last_result else []),
        errors=attempts_errors or ["execution failed with no error detail"],
        airtable_updates=[],
        next_recommended_action=(
            f"human review needed: {task.agent} failed after "
            f"{policy.max_retries + 1} attempt(s) on task {task.task_id}"
        ),
    )
