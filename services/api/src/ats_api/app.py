from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware

from ats_api.config import ApiSettings
from ats_api.config import load_api_settings
from ats_api.config import load_postgres_settings
from ats_api.repository import ApiRepository


REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_ENV_FILE = REPO_ROOT / ".env"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the recruiter-facing ATS API service.")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--reload", action="store_true")
    return parser


def create_app(
    settings: ApiSettings | None = None,
    repository: ApiRepository | None = None,
) -> FastAPI:
    app_settings = settings or load_api_settings(DEFAULT_ENV_FILE)
    app = FastAPI(title="ATS Candidate API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(app_settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.repository = repository or ApiRepository(load_postgres_settings(DEFAULT_ENV_FILE))

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/jobs")
    def list_jobs(request: Request) -> dict[str, object]:
        repo = get_repository(request)
        with repo.connect() as connection:
            jobs = repo.fetch_jobs(connection)
        return {"jobs": jobs}

    @app.get("/jobs/{job_id}/rankings")
    def list_job_rankings(job_id: str, request: Request) -> dict[str, object]:
        repo = get_repository(request)
        with repo.connect() as connection:
            job = repo.fetch_job(connection, job_id)
            if job is None:
                raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
            rankings = repo.fetch_job_rankings(connection, job_id)
        return {"job": job, "rankings": rankings}

    @app.get("/jobs/{job_id}/rankings/{resume_id}")
    def get_ranking_detail(job_id: str, resume_id: str, request: Request) -> dict[str, object]:
        repo = get_repository(request)
        with repo.connect() as connection:
            job = repo.fetch_job(connection, job_id)
            if job is None:
                raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
            detail = repo.fetch_ranking_detail(connection, job_id, resume_id)
            if detail is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Ranking not found for job {job_id} and resume {resume_id}",
                )

        ranking = {
            "job_id": detail["job_id"],
            "resume_id": detail["resume_id"],
            "retrieval_rank": detail["retrieval_rank"],
            "ranking_rank": detail["ranking_rank"],
            "semantic_similarity": detail["semantic_similarity"],
            "skill_coverage": detail["skill_coverage"],
            "experience_alignment": detail["experience_alignment"],
            "education_match": detail["education_match"],
            "role_relevance": detail["role_relevance"],
            "final_score": detail["final_score"],
            "score_breakdown": detail["score_breakdown"],
            "created_at": detail["ranking_created_at"],
            "updated_at": detail["ranking_updated_at"],
        }
        candidate_profile = {
            "resume_id": detail["resume_id"],
            "source_filename": detail["source_filename"],
            "source_path": detail["source_path"],
            "source_sha256": detail["source_sha256"],
            "parser_version": detail["parser_version"],
            "parsed_at": detail["parsed_at"],
            "name": detail["name"],
            "email": detail["email"],
            "phone": detail["phone"],
            "skills": detail["skills"],
            "education_count": detail["education_count"],
            "experience_count": detail["experience_count"],
            "project_count": detail["project_count"],
            "warning_count": detail["warning_count"],
            "profile_json": detail["profile_json"],
        }
        return {
            "job": job,
            "ranking": ranking,
            "candidate_profile": candidate_profile,
        }

    return app


def get_repository(request: Request) -> ApiRepository:
    return request.app.state.repository


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    env_file = args.env_file
    settings = load_api_settings(env_file)
    if args.host:
        settings = ApiSettings(host=args.host, port=settings.port, cors_origins=settings.cors_origins)
    if args.port is not None:
        settings = ApiSettings(host=settings.host, port=args.port, cors_origins=settings.cors_origins)

    app = create_app(settings=settings, repository=ApiRepository(load_postgres_settings(env_file)))
    uvicorn.run(app, host=settings.host, port=settings.port, reload=args.reload)
    return 0
