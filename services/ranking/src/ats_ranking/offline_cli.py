from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ats_ranking import __version__
from ats_ranking.cli import DEFAULT_ENV_FILE
from ats_ranking.config import load_postgres_settings
from ats_ranking.evaluation import evaluate_score_fields
from ats_ranking.labels import build_label_lookup
from ats_ranking.labels import default_split_for_job
from ats_ranking.labels import load_relevance_labels
from ats_ranking.labels import summarize_labels
from ats_ranking.ml import ModelDependencyError
from ats_ranking.ml import train_xgboost_reranker
from ats_ranking.pipeline import rank_candidates_for_job
from ats_ranking.repository import RankingRepository
from ats_ranking.signals import MODEL_FEATURE_NAMES
from ats_ranking.signals import apply_business_rules
from ats_ranking.signals import compute_ranking_signals


REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_OFFLINE_ARTIFACTS_DIR = REPO_ROOT / "data" / "processed" / "ranking" / "offline"
DEFAULT_DATASET_PATH = DEFAULT_OFFLINE_ARTIFACTS_DIR / "ranking_dataset.jsonl"
DEFAULT_EVALUATION_PATH = DEFAULT_OFFLINE_ARTIFACTS_DIR / "heuristic_evaluation.json"
DEFAULT_LABELS_PATH = REPO_ROOT / "data" / "labels" / "resume_jd_relevance.jsonl"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline ranking evaluation and reranker tooling.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export-dataset", help="Export retrieved job-resume pairs as offline features.")
    export_parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    export_parser.add_argument("--output-path", type=Path, default=DEFAULT_DATASET_PATH)
    export_parser.add_argument("--labels-path", type=Path, default=None)
    export_parser.add_argument("--only-labeled", action="store_true")

    evaluate_parser = subparsers.add_parser("evaluate", help="Evaluate one or more score fields from an offline dataset.")
    evaluate_parser.add_argument("--dataset-path", type=Path, default=DEFAULT_DATASET_PATH)
    evaluate_parser.add_argument("--output-path", type=Path, default=DEFAULT_EVALUATION_PATH)
    evaluate_parser.add_argument("--score-field", action="append", default=[])
    evaluate_parser.add_argument("--min-relevant-label", type=int, default=1)

    train_parser = subparsers.add_parser("train-reranker", help="Train and compare an offline XGBoost reranker.")
    train_parser.add_argument("--dataset-path", type=Path, default=DEFAULT_DATASET_PATH)
    train_parser.add_argument("--artifacts-dir", type=Path, default=DEFAULT_OFFLINE_ARTIFACTS_DIR / "xgboost")
    train_parser.add_argument("--train-split", action="append", default=["train"])
    train_parser.add_argument("--evaluation-split", action="append", default=["test", "validation", "train"])
    train_parser.add_argument("--min-relevant-label", type=int, default=1)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    if args.command == "export-dataset":
        try:
            summary = export_feature_dataset(
                env_file=args.env_file,
                output_path=args.output_path.resolve(),
                labels_path=args.labels_path.resolve() if args.labels_path else None,
                only_labeled=args.only_labeled,
            )
        except RuntimeError as exc:
            print(exc)
            return 1
        print(
            f"Exported {summary['row_count']} row(s) across {summary['job_count']} job(s) "
            f"to {args.output_path.resolve()}."
        )
        return 0

    if args.command == "evaluate":
        rows = load_jsonl(args.dataset_path.resolve())
        score_fields = args.score_field or infer_score_fields(rows)
        report = evaluate_score_fields(rows, score_fields=score_fields, min_relevant_label=args.min_relevant_label)
        write_json(args.output_path.resolve(), report)
        print(
            f"Evaluated {len(score_fields)} score field(s) across "
            f"{report[score_fields[0]]['jobs_with_labels'] if score_fields else 0} labeled job(s)."
        )
        return 0

    if args.command == "train-reranker":
        rows = load_jsonl(args.dataset_path.resolve())
        artifacts_dir = args.artifacts_dir.resolve()
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        try:
            training_result, evaluation_rows = train_xgboost_reranker(
                rows,
                train_splits=tuple(args.train_split),
                evaluation_splits=tuple(args.evaluation_split),
                feature_names=MODEL_FEATURE_NAMES,
            )
        except (ModelDependencyError, RuntimeError) as exc:
            print(exc)
            return 1

        predicted_rows: list[dict[str, Any]] = []
        for row in evaluation_rows:
            adjusted_score, penalty, reasons = apply_business_rules(row["ml_score"], row)
            next_row = dict(row)
            next_row["ml_adjusted_score"] = adjusted_score
            next_row["ml_business_rule_penalty"] = penalty
            next_row["ml_business_rule_reasons"] = reasons
            predicted_rows.append(next_row)

        comparison = evaluate_score_fields(
            predicted_rows,
            score_fields=infer_score_fields(predicted_rows, include_model_scores=True),
            min_relevant_label=args.min_relevant_label,
        )
        predictions_path = artifacts_dir / "evaluation_predictions.jsonl"
        comparison_path = artifacts_dir / "comparison.json"
        metadata_path = artifacts_dir / "metadata.json"
        model_path = artifacts_dir / "xgboost_reranker.json"
        write_jsonl(predictions_path, predicted_rows)
        write_json(comparison_path, comparison)
        write_json(
            metadata_path,
            {
                "service_version": __version__,
                "model_type": "xgboost_rank_ndcg",
                "feature_names": training_result.feature_names,
                "train_row_count": training_result.train_row_count,
                "evaluation_row_count": training_result.evaluation_row_count,
                "train_group_count": training_result.train_group_count,
                "evaluation_group_count": training_result.evaluation_group_count,
                "evaluation_splits": training_result.evaluation_splits,
                "predictions_path": str(predictions_path),
                "comparison_path": str(comparison_path),
            },
        )
        training_result.model.save_model(model_path)
        print(
            f"Trained offline XGBoost reranker on {training_result.train_row_count} labeled row(s). "
            f"Comparison written to {comparison_path}."
        )
        return 0

    print(f"Unsupported command: {args.command}")
    return 1


def export_feature_dataset(
    env_file: Path,
    output_path: Path,
    labels_path: Path | None,
    only_labeled: bool,
) -> dict[str, object]:
    labels = load_relevance_labels(labels_path) if labels_path else []
    label_lookup = build_label_lookup(labels)
    repository = RankingRepository(load_postgres_settings(env_file))
    rows: list[dict[str, Any]] = []

    with repository.connect() as connection:
        repository.ensure_schema(connection)
        jobs = repository.fetch_jobs(connection)
        if not jobs:
            raise RuntimeError("No jobs found in PostgreSQL. Run the embedding and ranking pipeline first.")

        for job in jobs:
            candidates = repository.fetch_retrieval_candidates(connection, job["job_id"])
            if not candidates:
                continue
            heuristic_rows = rank_candidates_for_job(job, candidates)
            heuristic_index = {row["resume_id"]: row for row in heuristic_rows}

            for candidate in candidates:
                label = label_lookup.get((job["job_id"], candidate["resume_id"]))
                if only_labeled and label is None:
                    continue

                signals = compute_ranking_signals(job, candidate)
                heuristic_adjusted_score, business_penalty, business_reasons = apply_business_rules(
                    signals.heuristic_score,
                    signals,
                )
                heuristic_row = heuristic_index[candidate["resume_id"]]
                split = None
                if label is not None:
                    split = label.split or default_split_for_job(job["job_id"])

                rows.append(
                    {
                        "job_id": job["job_id"],
                        "job_title": job["job_title"],
                        "resume_id": candidate["resume_id"],
                        "candidate_name": candidate.get("name"),
                        "label": label.label if label is not None else None,
                        "split": split,
                        "label_source": label.source if label is not None else None,
                        "label_notes": label.notes if label is not None else None,
                        "retrieval_rank": candidate["retrieval_rank"],
                        "heuristic_rank": heuristic_row["ranking_rank"],
                        "heuristic_score": signals.heuristic_score,
                        "heuristic_adjusted_score": heuristic_adjusted_score,
                        "business_rule_penalty": business_penalty,
                        "business_rule_reasons": business_reasons,
                        **signals.to_feature_dict(),
                    }
                )

    write_jsonl(output_path, rows)
    manifest_path = output_path.with_suffix(".manifest.json")
    summary = {
        "service_version": __version__,
        "row_count": len(rows),
        "job_count": len({row["job_id"] for row in rows}),
        "labeled_row_count": sum(1 for row in rows if row.get("label") is not None),
        "feature_names": list(MODEL_FEATURE_NAMES),
        "output_path": str(output_path),
        "labels_path": str(labels_path) if labels_path else None,
        "label_summary": summarize_labels(labels) if labels else None,
    }
    write_json(manifest_path, summary)
    return summary


def infer_score_fields(
    rows: list[dict[str, Any]],
    include_model_scores: bool = False,
) -> list[str]:
    candidates = ["heuristic_score", "heuristic_adjusted_score"]
    if include_model_scores:
        candidates.extend(["ml_score", "ml_adjusted_score"])
    return [field_name for field_name in candidates if any(row.get(field_name) is not None for row in rows)]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    path.write_text(payload, encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
