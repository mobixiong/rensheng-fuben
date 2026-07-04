from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ImageRepairHooks:
    check_cancelled: Callable[[dict[str, Any]], None]
    set_step: Callable[..., dict[str, Any]]
    repair_burst_for_shots: Callable[[dict[str, Any], list[int], str, int], tuple[set[int], dict[int, list[str]]]]
    optimize_failed_image_prompts: Callable[[dict[str, Any], list[int], str], tuple[set[int], set[int]]]
    state_or_default: Callable[[dict[str, Any]], dict[str, Any]]
    latest_job: Callable[[dict[str, Any]], dict[str, Any] | None]
    image_failure_message: Callable[[dict[str, Any], list[Any], list[int]], str]
    image_repair_concurrency: Callable[[dict[str, Any]], int]
    error_factory: Callable[[str], Exception]


@dataclass(frozen=True)
class ImageRepairPolicy:
    single_retry_size: int = 1
    burst_size: int = 9
    infinite_burst_size: int = 4


def _positive_int(value: Any, default: int = 1) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return max(1, int(default))


def chunk_indexes(indexes: list[int], size: int) -> list[list[int]]:
    clean = sorted(set(indexes))
    chunk_size = _positive_int(size)
    return [clean[index:index + chunk_size] for index in range(0, len(clean), chunk_size)]


def _stage_chunk_size(repair_concurrency: int, attempts_per_shot: int) -> int:
    return max(1, _positive_int(repair_concurrency) // _positive_int(attempts_per_shot))


def _remaining_after_repair(indexes: list[int], repaired: set[int]) -> list[int]:
    return [index for index in indexes if index not in repaired]


def _merge_failed_indexes(indexes: list[int], failed: set[int]) -> list[int]:
    return sorted(set(indexes) | set(failed))


def _repair_stage(
    job: dict[str, Any],
    indexes: list[int],
    *,
    stage: str,
    attempts_per_shot: int,
    detail_factory: Callable[[list[int], int, int], str],
    progress_base: float,
    progress_span: float,
    repair_concurrency: int,
    hooks: ImageRepairHooks,
) -> tuple[dict[str, Any], set[int], dict[int, list[str]]]:
    repaired_indexes: set[int] = set()
    errors_by_index: dict[int, list[str]] = {}
    batches = chunk_indexes(indexes, _stage_chunk_size(repair_concurrency, attempts_per_shot))
    for batch_position, batch in enumerate(batches, 1):
        hooks.check_cancelled(job)
        job = hooks.set_step(
            job,
            "images",
            "waiting",
            detail=detail_factory(batch, batch_position, len(batches)),
            progress=progress_base + progress_span * (batch_position - 1) / max(len(batches), 1),
        )
        repaired, errors = hooks.repair_burst_for_shots(job, batch, stage, attempts_per_shot)
        hooks.check_cancelled(job)
        repaired_indexes.update(repaired)
        for index, values in errors.items():
            errors_by_index.setdefault(index, []).extend(values)
    return job, repaired_indexes, errors_by_index


def repair_missing_images(
    job: dict[str, Any],
    missing_indexes: list[int],
    total: int,
    *,
    hooks: ImageRepairHooks,
    policy: ImageRepairPolicy = ImageRepairPolicy(),
) -> dict[str, Any]:
    remaining = sorted(set(missing_indexes))
    repair_concurrency = hooks.image_repair_concurrency(job)

    if remaining:
        job, repaired, _errors = _repair_stage(
            job,
            remaining,
            stage="retry1",
            attempts_per_shot=policy.single_retry_size,
            detail_factory=lambda batch, position, total_batches: (
                f"{len(batch)} 个失败镜头正在先各补抽 1 张（批次 {position}/{total_batches}）"
            ),
            progress_base=0.76,
            progress_span=0.02,
            repair_concurrency=repair_concurrency,
            hooks=hooks,
        )
        remaining = _remaining_after_repair(remaining, repaired)

    if remaining:
        job, repaired, _errors = _repair_stage(
            job,
            remaining,
            stage="retry9",
            attempts_per_shot=policy.burst_size,
            detail_factory=lambda batch, position, total_batches: (
                f"{len(batch)} 个失败镜头正在按并发上限 {repair_concurrency} 批量补抽 {len(batch) * policy.burst_size} 张"
                f"（批次 {position}/{total_batches}）"
            ),
            progress_base=0.79,
            progress_span=0.02,
            repair_concurrency=repair_concurrency,
            hooks=hooks,
        )
        remaining = _remaining_after_repair(remaining, repaired)

    optimize_failed: set[int] = set()
    if remaining:
        hooks.check_cancelled(job)
        job = hooks.set_step(
            job,
            "images",
            "waiting",
            detail=f"{len(remaining)} 个失败镜头 9 连抽失败，正在优化提示词",
            progress=0.82,
        )
        optimized, optimize_failed = hooks.optimize_failed_image_prompts(job, remaining, "optimized_after_retry9")
        remaining = [index for index in remaining if index in optimized]
        hooks.check_cancelled(job)

    if remaining:
        job, repaired, _errors = _repair_stage(
            job,
            remaining,
            stage="optimized9",
            attempts_per_shot=policy.burst_size,
            detail_factory=lambda batch, position, total_batches: (
                f"{len(batch)} 个失败镜头优化后正在按并发上限 {repair_concurrency} 批量补抽 {len(batch) * policy.burst_size} 张"
                f"（批次 {position}/{total_batches}）"
            ),
            progress_base=0.84,
            progress_span=0.015,
            repair_concurrency=repair_concurrency,
            hooks=hooks,
        )
        remaining = _remaining_after_repair(remaining, repaired)

    remaining = _merge_failed_indexes(remaining, optimize_failed)
    if remaining and (job.get("input") or {}).get("auto_infinite_image_retry"):
        round_index = 1
        while remaining:
            hooks.check_cancelled(job)
            job = hooks.set_step(
                job,
                "images",
                "waiting",
                detail=f"无限重抽第 {round_index} 轮：{len(remaining)} 个失败镜头优化提示词",
                progress=0.855,
            )
            optimized, optimize_failed = hooks.optimize_failed_image_prompts(job, remaining, f"infinite_optimize_{round_index}")
            retry_indexes = [index for index in remaining if index in optimized]
            hooks.check_cancelled(job)
            if retry_indexes:
                job, repaired, _errors = _repair_stage(
                    job,
                    retry_indexes,
                    stage=f"infinite{round_index}_retry4",
                    attempts_per_shot=policy.infinite_burst_size,
                    detail_factory=lambda batch, position, total_batches: (
                        f"无限重抽第 {round_index} 轮：按并发上限 {repair_concurrency} 批量补抽"
                        f" {len(batch) * policy.infinite_burst_size} 张（批次 {position}/{total_batches}）"
                    ),
                    progress_base=0.858,
                    progress_span=0.01,
                    repair_concurrency=repair_concurrency,
                    hooks=hooks,
                )
            else:
                repaired = set()
            remaining = _merge_failed_indexes(_remaining_after_repair(remaining, repaired), optimize_failed)
            round_index += 1
            if remaining:
                time.sleep(1)

    if remaining:
        state = hooks.state_or_default(job)
        shots = ((state.get("story") or {}).get("shots") or [])
        failure_detail = hooks.image_failure_message(job, shots, [index + 1 for index in remaining]) if isinstance(shots, list) else ""
        suffix = f"失败镜头：{failure_detail}" if failure_detail else f"失败镜头：{', '.join(str(index + 1) for index in remaining)}"
        success = max(0, int(total) - len(remaining))
        raise hooks.error_factory(f"图片自动补救后仍未完成：成功 {success}/{total}，失败 {len(remaining)}。{suffix}")
    hooks.check_cancelled(job)
    return hooks.latest_job(job) or job
