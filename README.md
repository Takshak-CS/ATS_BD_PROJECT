# Scalable Resume Screening and ATS Ranking System

This repository is set up for the improved version of your project: a distributed resume screening pipeline that replaces regex parsing and TF-IDF with NLP parsing, embeddings, vector retrieval, and ML-based ranking.

## Current scope

The repository now includes:

- an implementation-oriented architecture document
- a Windows-to-Ubuntu migration plan for VMware
- a monorepo scaffold for the services you described
- a local infrastructure stack for Ubuntu development

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

## Recommended development environment

Use Ubuntu inside VMware as the primary development environment. Do not keep the active repo inside a VMware shared folder long term. Clone the repository into the Ubuntu filesystem so Docker, Python virtual environments, and file watching behave normally.

Start local infrastructure from Ubuntu with:

```bash
docker compose -f infra/docker-compose.yml up -d
```

## Documents to read first

- [Improved architecture](docs/architecture.md)
- [Windows to Ubuntu migration plan](docs/windows-to-ubuntu-migration.md)
- [Implementation roadmap](docs/implementation-roadmap.md)

## Suggested build order

1. Implement `services/ingestion` and object storage.
2. Implement `services/parser` with spaCy-based extraction.
3. Implement `services/embedding` with MiniLM sentence embeddings.
4. Implement `services/ranking` with initial heuristic scoring.
5. Add Kafka events between services.
6. Replace heuristic ranking with a trained model once labeled data exists.

## Practical model choices for the first version

- Parsing: `spaCy` first, `LayoutLM` only if document layout becomes critical.
- Embeddings: `all-MiniLM-L6-v2` first for good speed/quality tradeoff.
- Vector store: `FAISS` first for local development, `Milvus` later for distributed search.
- Ranking: start with weighted features, then move to `LightGBM` ranking when you have historical outcomes.
