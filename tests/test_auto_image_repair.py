from __future__ import annotations

from typing import Any

import pytest

from app import auto_image_repair
from app.auto_image_repair import ImageRepairHooks, repair_missing_images


class FakeCancelled(RuntimeError):
    pass


class FakeRepair:
    def __init__(
        self,
        *,
        concurrency: int,
        success_by_stage: dict[str, set[int]] | None = None,
        optimize_success_by_stage: dict[str, set[int]] | None = None,
        latest_job_result: dict[str, Any] | None = None,
        cancel_after_checks: int | None = None,
    ) -> None:
        self.concurrency = concurrency
        self.success_by_stage = success_by_stage or {}
        self.optimize_success_by_stage = optimize_success_by_stage or {}
        self.latest_job_result = latest_job_result
        self.cancel_after_checks = cancel_after_checks
        self.cancel_checks = 0
        self.repair_calls: list[tuple[str, list[int], int]] = []
        self.optimize_calls: list[tuple[str, list[int]]] = []
        self.set_step_calls: list[tuple[str, str, str]] = []
        self.failure_message_calls: list[list[int]] = []

    def hooks(self) -> ImageRepairHooks:
        return ImageRepairHooks(
            check_cancelled=self.check_cancelled,
            set_step=self.set_step,
            repair_burst_for_shots=self.repair_burst_for_shots,
            optimize_failed_image_prompts=self.optimize_failed_image_prompts,
            state_or_default=lambda job: {"story": {"shots": [{} for _ in range(200)]}},
            latest_job=self.latest_job,
            image_failure_message=self.image_failure_message,
            image_repair_concurrency=lambda job: self.concurrency,
            error_factory=RuntimeError,
        )

    def check_cancelled(self, job: dict[str, Any]) -> None:
        self.cancel_checks += 1
        if self.cancel_after_checks is not None and self.cancel_checks >= self.cancel_after_checks:
            raise FakeCancelled("cancelled")

    def set_step(self, job: dict[str, Any], key: str, status: str, **updates: Any) -> dict[str, Any]:
        self.set_step_calls.append((key, status, str(updates.get("detail") or "")))
        job = {**job}
        job["current_step"] = key
        job["step_status"] = status
        job.update(updates)
        return job

    def repair_burst_for_shots(
        self,
        job: dict[str, Any],
        indexes: list[int],
        stage: str,
        attempts_per_shot: int,
    ) -> tuple[set[int], dict[int, list[str]]]:
        self.repair_calls.append((stage, list(indexes), attempts_per_shot))
        successes = set(indexes) & self.success_by_stage.get(stage, set())
        errors = {index: [f"{stage} failed"] for index in indexes if index not in successes}
        return successes, errors

    def optimize_failed_image_prompts(self, job: dict[str, Any], indexes: list[int], stage: str) -> tuple[set[int], set[int]]:
        self.optimize_calls.append((stage, list(indexes)))
        successes = set(indexes) & self.optimize_success_by_stage.get(stage, set(indexes))
        failed = set(indexes) - successes
        return successes, failed

    def latest_job(self, job: dict[str, Any]) -> dict[str, Any] | None:
        return self.latest_job_result if self.latest_job_result is not None else job

    def image_failure_message(self, job: dict[str, Any], shots: list[Any], indexes: list[int]) -> str:
        self.failure_message_calls.append(list(indexes))
        return ", ".join(str(index) for index in indexes)


def image_attempts(calls: list[tuple[str, list[int], int]], stage: str) -> int:
    return sum(len(indexes) * attempts for call_stage, indexes, attempts in calls if call_stage == stage)


def test_first_repair_round_dispatches_all_when_under_concurrency():
    fake = FakeRepair(concurrency=100, success_by_stage={"retry1": set(range(30))})

    repair_missing_images({"input": {}}, list(range(30)), 30, hooks=fake.hooks())

    assert fake.repair_calls == [("retry1", list(range(30)), 1)]


def test_first_repair_round_batches_by_concurrency():
    fake = FakeRepair(concurrency=20, success_by_stage={"retry1": set(range(30))})

    repair_missing_images({"input": {}}, list(range(30)), 30, hooks=fake.hooks())

    assert fake.repair_calls == [
        ("retry1", list(range(20)), 1),
        ("retry1", list(range(20, 30)), 1),
    ]


def test_invalid_concurrency_falls_back_to_one_shot_batches():
    fake = FakeRepair(concurrency=0, success_by_stage={"retry1": {0, 1, 2}})

    repair_missing_images({"input": {}}, [0, 1, 2], 3, hooks=fake.hooks())

    assert fake.repair_calls == [
        ("retry1", [0], 1),
        ("retry1", [1], 1),
        ("retry1", [2], 1),
    ]


def test_retry9_batches_by_image_attempt_concurrency():
    fake = FakeRepair(
        concurrency=20,
        success_by_stage={
            "retry1": set(),
            "retry9": set(range(5)),
        },
    )

    repair_missing_images({"input": {}}, list(range(5)), 5, hooks=fake.hooks())

    retry9_calls = [call for call in fake.repair_calls if call[0] == "retry9"]
    assert retry9_calls == [
        ("retry9", [0, 1], 9),
        ("retry9", [2, 3], 9),
        ("retry9", [4], 9),
    ]
    assert image_attempts(fake.repair_calls, "retry9") == 45


def test_retry9_only_targets_remaining_failed_shots():
    retry1_success = set(range(7))
    retry9_targets = {7, 8, 9}
    fake = FakeRepair(
        concurrency=100,
        success_by_stage={
            "retry1": retry1_success,
            "retry9": retry9_targets,
        },
    )

    repair_missing_images({"input": {}}, list(range(10)), 10, hooks=fake.hooks())

    assert fake.repair_calls == [
        ("retry1", list(range(10)), 1),
        ("retry9", [7, 8, 9], 9),
    ]
    assert image_attempts(fake.repair_calls, "retry9") == 27


def test_optimized9_only_targets_prompts_that_optimized_successfully():
    fake = FakeRepair(
        concurrency=100,
        success_by_stage={
            "retry1": set(),
            "retry9": set(),
            "optimized9": {3},
        },
        optimize_success_by_stage={
            "optimized_after_retry9": {1, 3},
        },
    )

    with pytest.raises(RuntimeError) as exc_info:
        repair_missing_images({"input": {}}, [0, 1, 2, 3], 4, hooks=fake.hooks())

    assert fake.optimize_calls == [("optimized_after_retry9", [0, 1, 2, 3])]
    assert ("optimized9", [1, 3], 9) in fake.repair_calls
    assert fake.failure_message_calls == [[1, 2, 3]]
    assert "失败 3" in str(exc_info.value)


def test_infinite_retry_uses_four_image_bursts_for_remaining(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(auto_image_repair.time, "sleep", lambda seconds: None)
    remaining = {0, 1}
    fake = FakeRepair(
        concurrency=100,
        success_by_stage={
            "retry1": set(),
            "retry9": set(),
            "optimized9": set(),
            "infinite1_retry4": remaining,
        },
        optimize_success_by_stage={
            "optimized_after_retry9": remaining,
            "infinite_optimize_1": remaining,
        },
    )

    repair_missing_images({"input": {"auto_infinite_image_retry": True}}, [0, 1], 2, hooks=fake.hooks())

    assert fake.optimize_calls == [
        ("optimized_after_retry9", [0, 1]),
        ("infinite_optimize_1", [0, 1]),
    ]
    assert ("infinite1_retry4", [0, 1], 4) in fake.repair_calls


def test_cancelled_after_repair_call_stops_later_stages():
    fake = FakeRepair(concurrency=100, success_by_stage={"retry1": set()}, cancel_after_checks=2)

    with pytest.raises(FakeCancelled):
        repair_missing_images({"input": {}}, [0, 1], 2, hooks=fake.hooks())

    assert fake.repair_calls == [("retry1", [0, 1], 1)]
    assert fake.optimize_calls == []


def test_returns_latest_job_after_success():
    latest = {"job_id": "latest"}
    fake = FakeRepair(concurrency=100, success_by_stage={"retry1": {0}}, latest_job_result=latest)

    result = repair_missing_images({"input": {}}, [0], 1, hooks=fake.hooks())

    assert result is latest
