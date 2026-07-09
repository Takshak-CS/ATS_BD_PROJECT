from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ats_ranking import __version__
from ats_ranking.config import load_postgres_settings
from ats_ranking.repository import RankingRepository
from ats_ranking.signals import compute_ranking_signals


@dataclass
class RankingRunResult:
    job_count: int
    ranked_candidate_count: int
    top_n: int
    job_ids: list[str]


def run_ranking_pipeline(env_file: Path, artifacts_dir: Path, top_n: int = 10) -> RankingRunResult:
    settings = load_postgres_settings(env_file)
    repository = RankingRepository(settings)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    with repository.connect() as connection:
        repository.ensure_schema(connection)
        jobs = repository.fetch_jobs(connection)
        if not jobs:
            raise RuntimeError("No job descriptions found. Run the embedding service first.")

        ranked_jobs = 0
        total_ranked_candidates = 0
        completed_job_ids: list[str] = []

        for job in jobs:
            candidates = repository.fetch_retrieval_candidates(connection, job["job_id"])
            if not candidates:
                continue

            ranked_rows = rank_candidates_for_job(job, candidates)

            repository.replace_rankings(connection, job["job_id"], ranked_rows)
            ranked_jobs += 1
            total_ranked_candidates += len(ranked_rows)
            completed_job_ids.append(job["job_id"])

            output_rows = [
                {
                    key: value
                    for key, value in row.items()
                    if key not in {"job_id"}
                }
                for row in ranked_rows[:top_n]
            ]
            write_json(
                artifacts_dir / f"{job['job_id']}.json",
                {
                    "job_id": job["job_id"],
                    "job_title": job["job_title"],
                    "top_n": top_n,
                    "ranked_candidates": output_rows,
                },
            )

        write_json(
            artifacts_dir / "manifest.json",
            {
                "service_version": __version__,
                "job_count": ranked_jobs,
                "ranked_candidate_count": total_ranked_candidates,
                "top_n": top_n,
            },
        )

    return RankingRunResult(
        job_count=ranked_jobs,
        ranked_candidate_count=total_ranked_candidates,
        top_n=top_n,
        job_ids=completed_job_ids,
    )


def run_incremental_ranking_pipeline(
    env_file: Path,
    artifacts_dir: Path,
    resume_id: str,
    top_n: int = 10,
    job_ids: list[str] | None = None,
) -> RankingRunResult:
    settings = load_postgres_settings(env_file)
    repository = RankingRepository(settings)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    with repository.connect() as connection:
        repository.ensure_schema(connection)
        target_job_ids = (
            repository.fetch_job_ids_for_resume(connection, resume_id)
            if job_ids is None
            else job_ids
        )

        ranked_jobs = 0
        total_ranked_candidates = 0
        completed_job_ids: list[str] = []

        for job_id in target_job_ids:
            job = repository.fetch_job(connection, job_id)
            if job is None:
                continue
            candidates = repository.fetch_retrieval_candidates(connection, job_id)
            ranked_rows = rank_candidates_for_job(job, candidates)
            repository.replace_rankings(connection, job_id, ranked_rows)
            ranked_jobs += 1
            total_ranked_candidates += len(ranked_rows)
            completed_job_ids.append(job_id)

            output_rows = [
                {key: value for key, value in row.items() if key not in {"job_id"}}
                for row in ranked_rows[:top_n]
            ]
            write_json(
                artifacts_dir / f"{job_id}.json",
                {
                    "job_id": job_id,
                    "job_title": job["job_title"],
                    "top_n": top_n,
                    "ranked_candidates": output_rows,
                },
            )

        write_json(
            artifacts_dir / "manifest.json",
            {
                "service_version": __version__,
                "mode": "incremental",
                "resume_id": resume_id,
                "job_count": ranked_jobs,
                "ranked_candidate_count": total_ranked_candidates,
                "top_n": top_n,
            },
        )

    return RankingRunResult(
        job_count=ranked_jobs,
        ranked_candidate_count=total_ranked_candidates,
        top_n=top_n,
        job_ids=completed_job_ids,
    )


def rank_candidates_for_job(job: dict, candidates: list[dict]) -> list[dict]:
    ranked_rows = []
    for candidate in candidates:
        signals = compute_ranking_signals(job, candidate)
        ranked_rows.append(
            {
                "job_id": job["job_id"],
                "resume_id": candidate["resume_id"],
                "name": candidate["name"],
                "email": candidate["email"],
                "retrieval_rank": candidate["retrieval_rank"],
                "semantic_similarity": signals.semantic_similarity,
                "skill_coverage": signals.skill_coverage,
                "experience_alignment": signals.experience_alignment,
                "education_match": signals.education_match,
                "role_relevance": signals.role_relevance,
                "final_score": signals.heuristic_score,
                "score_breakdown": signals.to_score_breakdown(),
            }
        )

    ranked_rows.sort(key=lambda row: (-row["final_score"], row["retrieval_rank"], row["resume_id"]))
    for rank_position, row in enumerate(ranked_rows, start=1):
        row["ranking_rank"] = rank_position
    return ranked_rows
def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
