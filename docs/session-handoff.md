# Session Handoff

## Current Project Status

- Parser MVP is complete and remains the active source of candidate profiles.
- Job description ingestion, embedding generation, FAISS retrieval, and initial
  ranking are now implemented for local Ubuntu development.
- PostgreSQL now stores candidate profiles, job descriptions, embeddings,
  semantic retrievals, and ranking results.
- A recruiter-facing FastAPI read service is now implemented under
  `services/api`.
- A FastAPI ingestion upload service is now implemented under
  `services/ingestion`.
- Kafka-compatible event helpers now exist under `shared/src/ats_shared/events`.
- Additive Redpanda consumer entry points now exist for parser, embedding, and
  ranking, and the ingestion service can now publish `resume.uploaded` through
  either the legacy CLI helper or the new HTTP upload path.
- A React + Vite recruiter UI now exists under `services/frontend`, including a
  recruiter-side upload panel wired to the ingestion API.

## What Has Already Been Implemented

- `services/parser`
  - resume extraction and structured parsing
  - parser manifest with warning and missing-field summary
  - PostgreSQL persistence into `public.candidate_profiles`
- `services/embedding`
  - job description ingestion from `data/raw/job_descriptions`
  - PostgreSQL tables:
    - `job_descriptions`
    - `candidate_profile_embeddings`
    - `job_description_embeddings`
    - `job_candidate_retrievals`
  - sentence-transformer embeddings with `all-MiniLM-L6-v2`
  - FAISS index artifact generation under `data/processed/embedding/faiss`
  - top-N semantic retrieval outputs under `data/processed/embedding/retrievals`
- `services/ranking`
  - heuristic scoring combining semantic similarity, skill coverage, experience
    alignment, education match, and role relevance
  - PostgreSQL persistence into `public.job_candidate_rankings`
  - ranking artifacts under `data/processed/ranking`
- `services/api`
  - FastAPI read endpoints:
    - `GET /jobs`
    - `GET /jobs/{job_id}/rankings`
    - `GET /jobs/{job_id}/rankings/{resume_id}`
  - Dockerfile and local README
- `shared`
  - topic constants for:
    - `resume.uploaded`
    - `resume.parsed`
    - `resume.embedded`
    - `candidate.ranked`
  - shared JSON producer and consumer wrappers using `confluent-kafka`
- `services/ingestion`
  - FastAPI endpoints:
    - `GET /health`
    - `POST /uploads/resumes`
  - raw request-body upload contract using:
    - `x-filename`
    - optional `x-resume-id`
  - local upload staging under `data/raw/uploads/` so the current parser
    consumer can read `source_path` without parser changes
  - retained local publisher helper to seed `resume.uploaded` events from a
    file already on disk
- `services/frontend`
  - Vite React UI wired to the API
  - job list, ranking list, candidate detail view
  - ingestion upload panel wired to `POST /uploads/resumes`
  - optional `VITE_INGESTION_API_BASE_URL`

## What Was Verified

- Parser batch: `97` resumes processed, `0` parser failures.
- Candidate profile persistence: `97` rows in `public.candidate_profiles`.
- Job description ingestion: `3` rows in `public.job_descriptions`.
- Embeddings:
  - `97` candidate embeddings
  - `3` job embeddings
- Retrieval:
  - `75` retrieval rows in `public.job_candidate_retrievals` for `top_k=25`
- Ranking:
  - `75` ranking rows in `public.job_candidate_rankings`
  - rankings generated for `3` jobs
- Unit tests exist for parser, JD parsing, config/reporting helpers, and ranking
  feature functions.
- New verification completed:
  - API unit tests: `3` passing
  - ingestion API unit tests: `3` passing
  - combined API + ingestion test run: `6` passing
  - syntax compilation across `shared`, `ingestion`, and `api` source and test
    trees
- Still not verified in this session:
  - live Redpanda consumer-chain execution
  - live ingestion-to-parser upload through the running HTTP service
  - frontend production build, because `services/frontend/node_modules` is not
    present in the current workspace

## Known Limitations

- Parser quality issues still propagate into ranking, especially for some names
  and sparse skill extraction.
- Ranking is heuristic-first and not calibrated on labeled hiring outcomes.
- Experience alignment is estimated from parser-derived entries, not a dedicated
  normalized experience timeline.
- The event-driven flow is additive and local-development oriented. The
  embedding and ranking consumers currently refresh full-stage artifacts on each
  event rather than performing fine-grained incremental updates.
- The new ingestion API stages uploads on the local filesystem for compatibility
  with the current parser consumer. MinIO is still part of the infra stack, but
  uploads are not yet mirrored there.
- End-to-end runtime verification across ingestion -> Redpanda -> parser ->
  embedding -> ranking -> API -> frontend has not been executed in this Codex
  session.

## Exact Next Step

- Run the live local integration in separate terminals and verify one upload all
  the way through the pipeline:
  1. `docker compose -f infra/docker-compose.yml up -d redpanda postgres minio`
  2. `PYTHONPATH=shared/src:services/parser/src python3 -m ats_parser.consumer`
  3. `PYTHONPATH=shared/src:services/embedding/src python3 -m ats_embedding.consumer`
  4. `PYTHONPATH=shared/src:services/ranking/src python3 -m ats_ranking.consumer`
  5. `PYTHONPATH=services/api/src python3 -m ats_api`
  6. `PYTHONPATH=shared/src:services/ingestion/src python3 -m ats_ingestion.app`
  7. `curl -X POST http://localhost:8010/uploads/resumes -H "x-filename: c1.pdf" -H "Content-Type: application/pdf" --data-binary @data/raw/resumes/c1.pdf`
  8. verify downstream state in PostgreSQL and the frontend, then decide whether
     the next focused change should be MinIO-backed upload persistence or Docker
     Compose entries for `api`, `ingestion`, and `frontend`
