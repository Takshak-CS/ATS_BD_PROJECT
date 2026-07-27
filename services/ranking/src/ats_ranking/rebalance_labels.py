from __future__ import annotations

import argparse
import json
import math
import random
from collections import Counter
from collections import defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_INPUT_PATH = REPO_ROOT / "data" / "labels" / "resume_jd_relevance.jsonl"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "data" / "labels" / "resume_jd_relevance.rebalanced.jsonl"

SPLITS = ("train", "validation", "test")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rewrite split assignments for labeled job-resume pairs on a per-job basis."
    )
    parser.add_argument("--input-path", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--train-ratio", type=float, default=0.70)
    parser.add_argument("--validation-ratio", type=float, default=0.15)
    parser.add_argument("--test-ratio", type=float, default=0.15)
    parser.add_argument(
        "--min-eval-per-job",
        type=int,
        default=5,
        help="Minimum rows to place in both validation and test for each job when feasible.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    rows = load_rows(args.input_path)
    validate_rows(rows, args.input_path)

    original_summaries = summarize_by_job(rows)
    rewritten_rows = rebalance_rows(
        rows=rows,
        seed=args.seed,
        train_ratio=args.train_ratio,
        validation_ratio=args.validation_ratio,
        test_ratio=args.test_ratio,
        min_eval_per_job=args.min_eval_per_job,
    )
    rewritten_summaries = summarize_by_job(rewritten_rows)

    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    with args.output_path.open("w", encoding="utf-8") as handle:
        for row in rewritten_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"Input path: {args.input_path}")
    print(f"Output path: {args.output_path}")
    print(f"Seed: {args.seed}")
    print(f"Min validation/test rows per job: {args.min_eval_per_job}")
    print("--- BEFORE ---")
    print_summary(original_summaries)
    print("--- AFTER ---")
    print_summary(rewritten_summaries)
    return 0


def load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def validate_rows(rows: list[dict[str, Any]], path: Path) -> None:
    seen: set[tuple[str, str]] = set()
    for index, row in enumerate(rows, start=1):
        key = (str(row.get("job_id", "")).strip(), str(row.get("resume_id", "")).strip())
        if not key[0] or not key[1]:
            raise ValueError(f"Missing job_id or resume_id at {path}:{index}")
        if key in seen:
            raise ValueError(f"Duplicate labeled pair at {path}:{index}: {key}")
        seen.add(key)
        label = row.get("label")
        if not isinstance(label, int) or label not in {0, 1, 2, 3}:
            raise ValueError(f"Invalid label at {path}:{index}: {label}")


def summarize_by_job(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for row in rows:
        job_id = row["job_id"]
        bucket = summary.setdefault(
            job_id,
            {
                "count": 0,
                "split_counts": Counter(),
                "label_counts": Counter(),
            },
        )
        bucket["count"] += 1
        bucket["split_counts"][row.get("split") or "(missing)"] += 1
        bucket["label_counts"][row["label"]] += 1
    return summary


def print_summary(summary: dict[str, dict[str, Any]]) -> None:
    for job_id in sorted(summary):
        bucket = summary[job_id]
        split_counts = {split: bucket["split_counts"].get(split, 0) for split in SPLITS}
        label_counts = dict(sorted(bucket["label_counts"].items()))
        print(
            f"{job_id}: total={bucket['count']} "
            f"splits={split_counts} labels={label_counts}"
        )


def rebalance_rows(
    rows: list[dict[str, Any]],
    seed: int,
    train_ratio: float,
    validation_ratio: float,
    test_ratio: float,
    min_eval_per_job: int,
) -> list[dict[str, Any]]:
    rows_by_job: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for index, row in enumerate(rows):
        rows_by_job[row["job_id"]].append((index, row))

    split_by_index: dict[int, str] = {}
    for job_id, indexed_rows in rows_by_job.items():
        assignments = assign_job_splits(
            indexed_rows=indexed_rows,
            seed=seed,
            job_id=job_id,
            train_ratio=train_ratio,
            validation_ratio=validation_ratio,
            test_ratio=test_ratio,
            min_eval_per_job=min_eval_per_job,
        )
        split_by_index.update(assignments)

    rewritten_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        updated = dict(row)
        updated["split"] = split_by_index[index]
        rewritten_rows.append(updated)
    return rewritten_rows


def assign_job_splits(
    indexed_rows: list[tuple[int, dict[str, Any]]],
    seed: int,
    job_id: str,
    train_ratio: float,
    validation_ratio: float,
    test_ratio: float,
    min_eval_per_job: int,
) -> dict[int, str]:
    total = len(indexed_rows)
    validation_target, test_target = compute_eval_targets(
        total=total,
        validation_ratio=validation_ratio,
        test_ratio=test_ratio,
        min_eval_per_job=min_eval_per_job,
    )
    train_target = total - validation_target - test_target
    if train_target <= 0:
        raise ValueError(f"Not enough rows to allocate train/validation/test for job {job_id}")

    label_buckets: dict[int, list[int]] = defaultdict(list)
    for original_index, row in indexed_rows:
        label_buckets[int(row["label"])].append(original_index)

    for label, indices in label_buckets.items():
        random.Random(f"{seed}:{job_id}:{label}").shuffle(indices)

    label_counts = {label: len(indices) for label, indices in label_buckets.items()}
    validation_alloc = proportional_allocate(label_counts, validation_target)
    remaining_after_validation = {
        label: label_counts[label] - validation_alloc.get(label, 0) for label in label_counts
    }
    test_alloc = proportional_allocate(remaining_after_validation, test_target)

    assignments: dict[int, str] = {}
    for label in sorted(label_buckets):
        indices = label_buckets[label]
        val_count = validation_alloc.get(label, 0)
        test_count = test_alloc.get(label, 0)
        cursor = 0
        for original_index in indices[cursor : cursor + val_count]:
            assignments[original_index] = "validation"
        cursor += val_count
        for original_index in indices[cursor : cursor + test_count]:
            assignments[original_index] = "test"
        cursor += test_count
        for original_index in indices[cursor:]:
            assignments[original_index] = "train"

    if Counter(assignments.values()) != Counter(
        {"train": train_target, "validation": validation_target, "test": test_target}
    ):
        raise AssertionError(f"Split allocation mismatch for job {job_id}")
    return assignments


def compute_eval_targets(
    total: int,
    validation_ratio: float,
    test_ratio: float,
    min_eval_per_job: int,
) -> tuple[int, int]:
    validation_target = max(min_eval_per_job, int(round(total * validation_ratio)))
    test_target = max(min_eval_per_job, int(round(total * test_ratio)))

    max_eval_budget = total - 1
    if validation_target + test_target > max_eval_budget:
        overflow = validation_target + test_target - max_eval_budget
        trim_each = math.ceil(overflow / 2)
        validation_target = max(1, validation_target - trim_each)
        test_target = max(1, test_target - (overflow - trim_each))

    if validation_target + test_target >= total:
        raise ValueError(f"Unable to allocate non-empty train split for job size {total}")
    return validation_target, test_target


def proportional_allocate(counts: dict[int, int], target: int) -> dict[int, int]:
    if target < 0:
        raise ValueError("target must be non-negative")
    total = sum(counts.values())
    if target == 0 or total == 0:
        return {label: 0 for label in counts}
    if target > total:
        raise ValueError("target exceeds available rows")

    raw_allocations = {
        label: (count * target / total)
        for label, count in counts.items()
    }
    allocation = {
        label: min(counts[label], int(math.floor(raw)))
        for label, raw in raw_allocations.items()
    }
    assigned = sum(allocation.values())
    remainder = target - assigned
    ranked_labels = sorted(
        counts,
        key=lambda label: (
            -(raw_allocations[label] - allocation[label]),
            -counts[label],
            label,
        ),
    )

    while remainder > 0:
        progressed = False
        for label in ranked_labels:
            if allocation[label] >= counts[label]:
                continue
            allocation[label] += 1
            remainder -= 1
            progressed = True
            if remainder == 0:
                break
        if not progressed:
            raise AssertionError("Failed to distribute proportional allocation remainder")

    return allocation


if __name__ == "__main__":
    raise SystemExit(main())
