from __future__ import annotations

import math
from typing import Any


def evaluate_score_fields(
    rows: list[dict[str, Any]],
    score_fields: list[str],
    min_relevant_label: int = 1,
) -> dict[str, object]:
    return {
        score_field: evaluate_ranker(rows, score_field=score_field, min_relevant_label=min_relevant_label)
        for score_field in score_fields
    }


def evaluate_ranker(
    rows: list[dict[str, Any]],
    score_field: str,
    min_relevant_label: int = 1,
) -> dict[str, object]:
    labeled_rows = [row for row in rows if row.get("label") is not None and row.get(score_field) is not None]
    grouped_rows = group_rows_by_job(labeled_rows)
    per_job: list[dict[str, Any]] = []

    for job_id, job_rows in grouped_rows.items():
        ranked_rows = sorted(
            job_rows,
            key=lambda row: (
                -float(row[score_field]),
                int(row.get("retrieval_rank") or 10**9),
                str(row["resume_id"]),
            ),
        )
        graded_labels = [int(row["label"]) for row in ranked_rows]
        relevant_total = sum(1 for label in graded_labels if label >= min_relevant_label)
        per_job.append(
            {
                "job_id": job_id,
                "job_title": ranked_rows[0].get("job_title"),
                "labeled_pair_count": len(ranked_rows),
                "relevant_pair_count": relevant_total,
                "precision_at_5": precision_at_k(graded_labels, 5, min_relevant_label=min_relevant_label),
                "recall_at_10": recall_at_k(
                    graded_labels,
                    10,
                    relevant_total=relevant_total,
                    min_relevant_label=min_relevant_label,
                ),
                "ndcg_at_10": ndcg_at_k(graded_labels, 10),
            }
        )

    def average(metric_name: str) -> float:
        if not per_job:
            return 0.0
        return round(sum(float(row[metric_name]) for row in per_job) / len(per_job), 6)

    jobs_with_relevant_labels = sum(1 for row in per_job if row["relevant_pair_count"] > 0)
    return {
        "score_field": score_field,
        "jobs_with_labels": len(per_job),
        "jobs_with_relevant_labels": jobs_with_relevant_labels,
        "labeled_pair_count": len(labeled_rows),
        "precision_at_5": average("precision_at_5"),
        "recall_at_10": average("recall_at_10"),
        "ndcg_at_10": average("ndcg_at_10"),
        "per_job": per_job,
    }


def precision_at_k(labels: list[int], k: int, min_relevant_label: int = 1) -> float:
    if k <= 0 or not labels:
        return 0.0
    limit = min(k, len(labels))
    hits = sum(1 for label in labels[:limit] if label >= min_relevant_label)
    return round(hits / limit, 6)


def recall_at_k(labels: list[int], k: int, relevant_total: int, min_relevant_label: int = 1) -> float:
    if k <= 0 or not labels or relevant_total <= 0:
        return 0.0
    hits = sum(1 for label in labels[: min(k, len(labels))] if label >= min_relevant_label)
    return round(hits / relevant_total, 6)


def ndcg_at_k(labels: list[int], k: int) -> float:
    if k <= 0 or not labels:
        return 0.0
    observed = dcg_at_k(labels, k)
    ideal = dcg_at_k(sorted(labels, reverse=True), k)
    if ideal <= 0:
        return 0.0
    return round(observed / ideal, 6)


def dcg_at_k(labels: list[int], k: int) -> float:
    score = 0.0
    for index, label in enumerate(labels[: min(k, len(labels))], start=1):
        gain = (2**int(label)) - 1
        score += gain / math.log2(index + 1)
    return score


def group_rows_by_job(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["job_id"]), []).append(row)
    return grouped
