# Embedding Service

Purpose:

- ingest job descriptions into PostgreSQL
- generate embeddings for candidate profiles and job descriptions
- build a local FAISS index for candidate retrieval
- persist top-N semantic retrieval results per job description

## MVP scope

The embedding MVP is a local batch worker for Ubuntu development. It reads job
descriptions from `data/raw/job_descriptions/`, reuses parsed candidate
profiles from PostgreSQL, creates sentence-transformer embeddings, stores them
in PostgreSQL, builds a FAISS index on disk, and writes semantic retrieval
outputs under `data/processed/embedding/`.

## Local usage

Run directly from the repository root:

```bash
PYTHONPATH=services/embedding/src python3 -m ats_embedding \
  --jd-dir data/raw/job_descriptions \
  --artifacts-dir data/processed/embedding \
  --top-k 25
```

Kafka consumer entry point:

```bash
PYTHONPATH=shared/src:services/embedding/src python3 -m ats_embedding.consumer
```

## Notes

- Default model: `all-MiniLM-L6-v2`
- FAISS uses cosine-style retrieval via normalized vectors and inner product.
- PostgreSQL tables created by this service:
  - `job_descriptions`
  - `candidate_profile_embeddings`
  - `job_description_embeddings`
  - `job_candidate_retrievals`
- The Kafka consumer listens for `resume.parsed` and publishes
  `resume.embedded` after refreshing embeddings and retrieval artifacts.
