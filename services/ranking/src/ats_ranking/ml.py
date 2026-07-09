from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from ats_ranking.signals import MODEL_FEATURE_NAMES

try:
    from xgboost import XGBRanker
except ImportError:  # pragma: no cover - depends on optional dependency
    XGBRanker = None


class ModelDependencyError(RuntimeError):
    pass


@dataclass(frozen=True)
class RerankerTrainingResult:
    model: Any
    feature_names: list[str]
    train_row_count: int
    evaluation_row_count: int
    train_group_count: int
    evaluation_group_count: int
    evaluation_splits: list[str]


def train_xgboost_reranker(
    rows: list[dict[str, Any]],
    train_splits: tuple[str, ...] = ("train",),
    evaluation_splits: tuple[str, ...] = ("test", "validation", "train"),
    feature_names: tuple[str, ...] = MODEL_FEATURE_NAMES,
) -> tuple[RerankerTrainingResult, list[dict[str, Any]]]:
    if XGBRanker is None:
        raise ModelDependencyError(
            "XGBoost is not installed. Install the ranking service optional ML dependency "
            "before training the offline reranker."
        )

    labeled_rows = [row for row in rows if row.get("label") is not None]
    train_rows = sort_grouped_rows(row for row in labeled_rows if row.get("split") in train_splits)
    if not train_rows:
        raise RuntimeError(f"No labeled rows found for train split(s): {', '.join(train_splits)}")

    distinct_labels = {int(row["label"]) for row in train_rows}
    if len(distinct_labels) < 2:
        raise RuntimeError("Training requires at least two distinct relevance labels.")

    evaluation_rows: list[dict[str, Any]] = []
    used_evaluation_splits: list[str] = []
    for split_name in evaluation_splits:
        split_rows = sort_grouped_rows(row for row in labeled_rows if row.get("split") == split_name)
        if split_rows:
            evaluation_rows = split_rows
            used_evaluation_splits = [split_name]
            break

    if not evaluation_rows:
        evaluation_rows = train_rows
        used_evaluation_splits = ["train"]

    x_train = build_feature_matrix(train_rows, feature_names)
    y_train = np.asarray([float(row["label"]) for row in train_rows], dtype=float)
    train_groups = build_group_sizes(train_rows)

    x_eval = build_feature_matrix(evaluation_rows, feature_names)
    y_eval = np.asarray([float(row["label"]) for row in evaluation_rows], dtype=float)
    evaluation_groups = build_group_sizes(evaluation_rows)

    model = XGBRanker(
        objective="rank:ndcg",
        n_estimators=160,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.9,
        colsample_bytree=0.9,
        reg_lambda=1.0,
        random_state=42,
    )
    model.fit(
        x_train,
        y_train,
        group=train_groups,
        eval_set=[(x_eval, y_eval)],
        eval_group=[evaluation_groups],
        verbose=False,
    )

    predicted_scores = model.predict(x_eval)
    annotated_rows = []
    for row, predicted_score in zip(evaluation_rows, predicted_scores):
        next_row = dict(row)
        next_row["ml_score"] = round(float(predicted_score), 6)
        annotated_rows.append(next_row)

    return (
        RerankerTrainingResult(
            model=model,
            feature_names=list(feature_names),
            train_row_count=len(train_rows),
            evaluation_row_count=len(evaluation_rows),
            train_group_count=len(train_groups),
            evaluation_group_count=len(evaluation_groups),
            evaluation_splits=used_evaluation_splits,
        ),
        annotated_rows,
    )


def build_feature_matrix(rows: list[dict[str, Any]], feature_names: tuple[str, ...]) -> np.ndarray:
    return np.asarray(
        [
            [float(row.get(feature_name, 0.0) or 0.0) for feature_name in feature_names]
            for row in rows
        ],
        dtype=float,
    )


def build_group_sizes(rows: list[dict[str, Any]]) -> list[int]:
    counts: list[int] = []
    current_job_id: str | None = None
    current_count = 0
    for row in rows:
        job_id = str(row["job_id"])
        if current_job_id is None:
            current_job_id = job_id
        if job_id != current_job_id:
            counts.append(current_count)
            current_job_id = job_id
            current_count = 0
        current_count += 1
    if current_job_id is not None:
        counts.append(current_count)
    return counts


def sort_grouped_rows(rows) -> list[dict[str, Any]]:
    return sorted(
        list(rows),
        key=lambda row: (
            str(row["job_id"]),
            int(row.get("retrieval_rank") or 10**9),
            str(row["resume_id"]),
        ),
    )
