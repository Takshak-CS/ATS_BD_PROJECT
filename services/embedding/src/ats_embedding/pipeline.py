from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ats_embedding import __version__
from ats_embedding.config import load_postgres_settings
from ats_embedding.embeddings import DEFAULT_MODEL_NAME
from ats_embedding.embeddings import EmbeddingGenerator
from ats_embedding.embeddings import build_candidate_embedding_text
from ats_embedding.embeddings import build_job_embedding_text
from ats_embedding.embeddings import compute_text_sha256
from ats_embedding.embeddings import to_serializable_vector
from ats_embedding.embeddings import write_json
from ats_embedding.faiss_index import CandidateFaissIndex
from ats_embedding.jd_ingestion import load_job_descriptions
from ats_embedding.models import RetrievalResult
from ats_embedding.repository import EmbeddingRepository


@dataclass
class EmbeddingRunResult:
    job_count: int
    candidate_count: int
    top_k: int
    model_name: str
    job_ids: list[str]


@dataclass
class IncrementalEmbeddingResult:
    resume_id: str
    affected_job_ids: list[str]
    model_name: str
    top_k: int


def run_embedding_pipeline(
    env_file: Path,
    jd_dir: Path,
    artifacts_dir: Path,
    model_name: str = DEFAULT_MODEL_NAME,
    top_k: int = 25,
) -> EmbeddingRunResult:
    settings = load_postgres_settings(env_file)
    repository = EmbeddingRepository(settings)
    generator = EmbeddingGenerator(model_name)
    faiss_index = CandidateFaissIndex()

    jobs = load_job_descriptions(jd_dir)
    if not jobs:
        raise RuntimeError(f"No job descriptions found in {jd_dir}")

    with repository.connect() as connection:
        repository.ensure_schema(connection)
        for job in jobs:
            repository.upsert_job_description(connection, job, compute_text_sha256(job.raw_text))

        candidate_rows = repository.fetch_candidate_profiles(connection)
        if not candidate_rows:
            raise RuntimeError("No candidate profiles found in PostgreSQL.")

        candidate_texts = [build_candidate_embedding_text(row) for row in candidate_rows]
        candidate_embeddings = generator.encode(candidate_texts)
        for row, text, vector in zip(candidate_rows, candidate_texts, candidate_embeddings):
            repository.upsert_candidate_embedding(
                connection=connection,
                resume_id=row["resume_id"],
                model_name=model_name,
                content_sha256=compute_text_sha256(text),
                embedding=to_serializable_vector(vector),
            )

        job_texts = [build_job_embedding_text(job) for job in jobs]
        job_embeddings = generator.encode(job_texts)
        for job, text, vector in zip(jobs, job_texts, job_embeddings):
            repository.upsert_job_embedding(
                connection=connection,
                job_id=job.job_id,
                model_name=model_name,
                content_sha256=compute_text_sha256(text),
                embedding=to_serializable_vector(vector),
            )

        index = faiss_index.build(candidate_embeddings)
        index_path = artifacts_dir / "faiss" / "candidate_profiles.index"
        faiss_index.write(
            index=index,
            path=index_path,
            metadata={
                "service_version": __version__,
                "model_name": model_name,
                "candidate_ids": [row["resume_id"] for row in candidate_rows],
                "embedding_dim": int(candidate_embeddings.shape[1]),
            },
        )

        retrieval_dir = artifacts_dir / "retrievals"
        for job, vector in zip(jobs, job_embeddings):
            scores, indices = faiss_index.search(index, vector, min(top_k, len(candidate_rows)))
            retrievals: list[RetrievalResult] = []
            for rank_position, (score, index_position) in enumerate(zip(scores, indices), start=1):
                if index_position < 0:
                    continue
                retrievals.append(
                    RetrievalResult(
                        job_id=job.job_id,
                        resume_id=candidate_rows[int(index_position)]["resume_id"],
                        retrieval_rank=rank_position,
                        semantic_similarity=float((float(score) + 1.0) / 2.0),
                    )
                )

            repository.replace_retrievals(connection, job.job_id, model_name, retrievals)
            write_json(
                retrieval_dir / f"{job.job_id}.json",
                {
                    "job_id": job.job_id,
                    "job_title": job.job_title,
                    "model_name": model_name,
                    "top_k": top_k,
                    "retrievals": [retrieval.to_dict() for retrieval in retrievals],
                },
            )

        manifest = {
            "service_version": __version__,
            "model_name": model_name,
            "job_count": len(jobs),
            "candidate_count": len(candidate_rows),
            "top_k": top_k,
            "artifacts_dir": str(artifacts_dir.resolve()),
        }
        write_json(artifacts_dir.resolve() / "manifest.json", manifest)

    return EmbeddingRunResult(
        job_count=len(jobs),
        candidate_count=len(candidate_rows),
        top_k=top_k,
        model_name=model_name,
        job_ids=[job.job_id for job in jobs],
    )


def run_incremental_embedding_pipeline(
    env_file: Path,
    jd_dir: Path,
    artifacts_dir: Path,
    resume_id: str,
    model_name: str = DEFAULT_MODEL_NAME,
    top_k: int = 25,
    generator: EmbeddingGenerator | None = None,
) -> IncrementalEmbeddingResult:
    settings = load_postgres_settings(env_file)
    repository = EmbeddingRepository(settings)
    embedding_generator = generator or EmbeddingGenerator(model_name)
    jobs = load_job_descriptions(jd_dir)
    if not jobs:
        raise RuntimeError(f"No job descriptions found in {jd_dir}")

    with repository.connect() as connection:
        repository.ensure_schema(connection)
        for job in jobs:
            repository.upsert_job_description(connection, job, compute_text_sha256(job.raw_text))

        candidate_row = repository.fetch_candidate_profile(connection, resume_id)
        if candidate_row is None:
            raise RuntimeError(f"Candidate profile not found for resume_id={resume_id}")

        candidate_text = build_candidate_embedding_text(candidate_row)
        candidate_vector = embedding_generator.encode([candidate_text])[0]
        repository.upsert_candidate_embedding(
            connection=connection,
            resume_id=resume_id,
            model_name=model_name,
            content_sha256=compute_text_sha256(candidate_text),
            embedding=to_serializable_vector(candidate_vector),
        )

        job_texts = [build_job_embedding_text(job) for job in jobs]
        job_vectors = embedding_generator.encode(job_texts)

        affected_job_ids: list[str] = []
        retrieval_dir = artifacts_dir.resolve() / "retrievals"
        for job, job_text, job_vector in zip(jobs, job_texts, job_vectors):
            repository.upsert_job_embedding(
                connection=connection,
                job_id=job.job_id,
                model_name=model_name,
                content_sha256=compute_text_sha256(job_text),
                embedding=to_serializable_vector(job_vector),
            )

            semantic_similarity = float((float(candidate_vector @ job_vector) + 1.0) / 2.0)
            current_rows = repository.fetch_job_retrievals(connection, job.job_id)
            top_rows, job_changed = merge_candidate_into_retrievals(
                job_id=job.job_id,
                resume_id=resume_id,
                semantic_similarity=semantic_similarity,
                current_rows=current_rows,
                top_k=top_k,
            )
            if not job_changed:
                continue

            retrievals = [
                RetrievalResult(
                    job_id=job.job_id,
                    resume_id=row["resume_id"],
                    retrieval_rank=index,
                    semantic_similarity=row["semantic_similarity"],
                )
                for index, row in enumerate(top_rows, start=1)
            ]
            repository.replace_retrievals(connection, job.job_id, model_name, retrievals)
            write_json(
                retrieval_dir / f"{job.job_id}.json",
                {
                    "job_id": job.job_id,
                    "job_title": job.job_title,
                    "model_name": model_name,
                    "top_k": top_k,
                    "retrievals": [retrieval.to_dict() for retrieval in retrievals],
                },
            )
            affected_job_ids.append(job.job_id)

        write_json(
            artifacts_dir.resolve() / "manifest.json",
            {
                "service_version": __version__,
                "model_name": model_name,
                "mode": "incremental",
                "resume_id": resume_id,
                "affected_job_ids": affected_job_ids,
                "top_k": top_k,
                "artifacts_dir": str(artifacts_dir.resolve()),
            },
        )

    return IncrementalEmbeddingResult(
        resume_id=resume_id,
        affected_job_ids=affected_job_ids,
        model_name=model_name,
        top_k=top_k,
    )


def merge_candidate_into_retrievals(
    job_id: str,
    resume_id: str,
    semantic_similarity: float,
    current_rows: list[dict],
    top_k: int,
) -> tuple[list[dict], bool]:
    existing_rows = [dict(row) for row in current_rows]
    was_present = any(row["resume_id"] == resume_id for row in existing_rows)
    merged_rows = [row for row in existing_rows if row["resume_id"] != resume_id]
    merged_rows.append(
        {
            "job_id": job_id,
            "resume_id": resume_id,
            "semantic_similarity": round(float(semantic_similarity), 12),
        }
    )
    merged_rows.sort(key=lambda row: (-row["semantic_similarity"], row["resume_id"]))
    top_rows = merged_rows[:top_k]
    is_present = any(row["resume_id"] == resume_id for row in top_rows)

    if not is_present and not was_present:
        return existing_rows, False

    normalized_rows = [
        {
            "job_id": job_id,
            "resume_id": row["resume_id"],
            "semantic_similarity": float(row["semantic_similarity"]),
        }
        for row in top_rows
    ]
    return normalized_rows, True
