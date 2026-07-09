# Scalable Resume Screening and ATS Ranking System

This repository is set up for the improved version of your project: a distributed resume screening pipeline that replaces regex parsing and TF-IDF with NLP parsing, embeddings, vector retrieval, and ML-based ranking.

## Current scope

The repository now includes:

- an implementation-oriented architecture document
- a Windows-to-Ubuntu migration plan for VMware
- a monorepo scaffold for the services you described
- a local infrastructure stack for Ubuntu development
- a working batch parser, embedding, and ranking pipeline for local runs

## Target architecture

The improved pipeline is:

```text
Candidate Upload
  -> Ingestion API
  -> Object Storage
  -> Kafka / Redpanda event
  -> Resume Parser
  -> Structured Candidate Profile
  -> Embedding Service
  -> Vector Search
  -> Ranking Service
  -> Candidate API / HR Dashboard
  -> Optional AI Pre-screening
```

The baseline Spark + regex + RAKE + TF-IDF approach is replaced with:

- `spaCy` and document parsing for structured extraction
- `sentence-transformers` for semantic matching
- `FAISS` for local development and `Milvus` for scale-out deployment
- `LightGBM` / `XGBoost` style ranking models after you collect labels
- Kafka-compatible streaming using `Redpanda` for simpler local setup

## Repository layout

```text
docs/                     Architecture and migration documents
infra/                    Docker Compose and environment configuration
services/
  ingestion/              Resume upload API
  parser/                 NLP parsing and profile extraction
  embedding/              Embedding generation and vector indexing
  ranking/                Candidate ranking and shortlist generation
  api/                    Recruiter-facing read APIs
shared/                   Shared schemas, utilities, and config contracts
```

## Current implementation status

Implemented now:

- `services/parser`
  - parses local resume files from `data/raw/resumes/`
  - extracts name, email, phone, skills, education, experience, certifications, and projects
  - writes structured JSON profiles to `data/processed/parser/profiles/`
  - persists structured candidate profiles to PostgreSQL table `public.candidate_profiles`
- `services/embedding`
  - ingests local job descriptions from `data/raw/job_descriptions/`
  - persists jobs to `public.job_descriptions`
  - generates sentence-transformer embeddings with `all-MiniLM-L6-v2`
  - stores candidate and job embeddings in PostgreSQL
  - builds a FAISS index locally and writes retrieval artifacts under `data/processed/embedding/`
- `services/ranking`
  - combines semantic similarity with parser-derived features
  - persists ranked candidates to `public.job_candidate_rankings`
  - writes ranking artifacts under `data/processed/ranking/`

Not implemented yet:

- `services/ingestion` upload API
- `services/api` recruiter-facing read API
- Kafka or Redpanda event-driven orchestration between services
- ML-based ranking beyond the current heuristic score

## Available local data

- resumes: `data/raw/resumes/` currently contains `97` PDF resumes
- job descriptions: `data/raw/job_descriptions/` currently contains:
  - `software_engineer_jd_01.txt`
  - `data_analyst_jd_01.txt`
  - `ml_engineer_jd_01.txt`

## Recommended development environment

Use Ubuntu inside VMware as the primary development environment. Do not keep the active repo inside a VMware shared folder long term. Clone the repository into the Ubuntu filesystem so Docker, Python virtual environments, and file watching behave normally.

Start local infrastructure from Ubuntu with:

```bash
docker compose -f infra/docker-compose.yml up -d
```

If you only want the currently used storage for the batch pipeline, PostgreSQL is sufficient:

```bash
docker compose -f infra/docker-compose.yml up -d postgres
```

## How To Run The Pipeline

These steps run the currently implemented local batch pipeline:

`resume files -> parser -> PostgreSQL candidate profiles -> JD ingestion + embeddings + FAISS retrieval -> heuristic ranking`

### 1. Prepare the environment

The repo already includes `.env.example`. Copy it if you do not have `.env` yet:

```bash
cp .env.example .env
```

The current `.env` shape is:

```env
POSTGRES_DB=ats
POSTGRES_USER=ats_user
POSTGRES_PASSWORD=ats_password

MINIO_ROOT_USER=minio
MINIO_ROOT_PASSWORD=minio123

REDPANDA_BROKERS=localhost:9092
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
MINIO_ENDPOINT=localhost:9000
```

### 2. Start infrastructure

For the current batch pipeline:

```bash
docker compose -f infra/docker-compose.yml up -d postgres
```

If you want the full local stack available for later phases:

```bash
docker compose -f infra/docker-compose.yml up -d
```

### 3. Create a Python environment and install service dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -e services/parser -e services/embedding -e services/ranking
```

Recommended Ubuntu package for better PDF text extraction:

```bash
sudo apt-get update
sudo apt-get install -y poppler-utils
```

Optional spaCy model:

```bash
python3 -m spacy download en_core_web_sm
```

The parser works without this model, but uses a smaller fallback pipeline if it is missing.

### 4. Run the parser

This reads resumes from `data/raw/resumes/`, writes JSON outputs to `data/processed/parser/`, and persists candidate profiles into PostgreSQL:

```bash
PYTHONPATH=services/parser/src python3 -m ats_parser \
  --input-dir data/raw/resumes \
  --output-dir data/processed/parser \
  --overwrite \
  --persist-postgres
```

Main outputs:

- `data/processed/parser/profiles/*.json`
- `data/processed/parser/manifest.json`
- PostgreSQL table `public.candidate_profiles`

### 5. Run job description ingestion, embeddings, and FAISS retrieval

This reads job descriptions from `data/raw/job_descriptions/`, embeds jobs and candidates, stores embeddings in PostgreSQL, builds a FAISS index, and writes top candidate retrievals:

```bash
PYTHONPATH=services/embedding/src python3 -m ats_embedding \
  --jd-dir data/raw/job_descriptions \
  --artifacts-dir data/processed/embedding \
  --top-k 25
```

Main outputs:

- `data/processed/embedding/faiss/candidate_profiles.index`
- `data/processed/embedding/faiss/candidate_profiles.meta.json`
- `data/processed/embedding/retrievals/*.json`
- `data/processed/embedding/manifest.json`
- PostgreSQL tables:
  - `public.job_descriptions`
  - `public.candidate_profile_embeddings`
  - `public.job_description_embeddings`
  - `public.job_candidate_retrievals`

### 6. Run ranking

This combines semantic retrieval with explicit parser-derived features:

```bash
PYTHONPATH=services/ranking/src python3 -m ats_ranking \
  --artifacts-dir data/processed/ranking \
  --top-n 10
```

Main outputs:

- `data/processed/ranking/*.json`
- `data/processed/ranking/manifest.json`
- PostgreSQL table `public.job_candidate_rankings`

### 7. Inspect results

Useful files:

- parser quality summary: `data/processed/parser/manifest.json`
- semantic retrieval results: `data/processed/embedding/retrievals/`
- final ranked candidates: `data/processed/ranking/`

Useful PostgreSQL tables:

- `candidate_profiles`
- `job_descriptions`
- `candidate_profile_embeddings`
- `job_description_embeddings`
- `job_candidate_retrievals`
- `job_candidate_rankings`

Example:

```bash
psql "host=localhost port=5432 dbname=ats user=ats_user password=ats_password" \
  -c "SELECT job_id, resume_id, ranking_rank, final_score FROM public.job_candidate_rankings ORDER BY job_id, ranking_rank LIMIT 15;"
```

## Documents to read first

- [Improved architecture](docs/architecture.md)
- [Windows to Ubuntu migration plan](docs/windows-to-ubuntu-migration.md)
- [Implementation roadmap](docs/implementation-roadmap.md)

## Suggested build order

1. Use the implemented parser, embedding, and ranking batch pipeline end to end.
2. Add `services/api` to expose ranked candidates and score breakdowns.
3. Add `services/ingestion` for file upload and object storage.
4. Add Kafka or Redpanda events between stages.
5. Replace heuristic ranking with a trained model once labeled data exists.

## Practical model choices for the first version

- Parsing: `spaCy` first, `LayoutLM` only if document layout becomes critical.
- Embeddings: `all-MiniLM-L6-v2` first for good speed/quality tradeoff.
- Vector store: `FAISS` first for local development, `Milvus` later for distributed search.
- Ranking: start with weighted features, then move to `LightGBM` ranking when you have historical outcomes.
