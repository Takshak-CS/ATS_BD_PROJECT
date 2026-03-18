# Improved System Architecture

## Objectives

The system should:

- process `10,000+` resumes per job posting
- support asynchronous and distributed execution
- improve matching quality beyond keyword overlap
- expose ranked candidate results through a clean API layer
- remain practical to run locally in Ubuntu on VMware during development

## Design principles

- Keep ingestion, parsing, embeddings, ranking, and read APIs as separate services.
- Use event-driven communication for throughput-sensitive stages.
- Prefer simple local infrastructure first, then scale the same interfaces in production.
- Separate object storage, transactional data, vector data, and analytics concerns.

## Proposed service architecture

```text
                           +----------------------+
                           |   HR Dashboard/API   |
                           +----------+-----------+
                                      |
                                      v
+-----------+     +-------------+  +----------------+  +------------------+
| Candidate  | --> | Ingestion   |->| Object Storage |  | Candidate API    |
| Upload UI  |     | API         |  | Resume Files   |  | Ranked Retrieval |
+-----------+     +------+------+  +--------+-------+  +---------+--------+
                            |                  |                    ^
                            v                  |                    |
                     +------+-------+          |                    |
                     | Kafka Topic  |          |                    |
                     | resume.raw   |          |                    |
                     +------+-------+          |                    |
                            |                  |                    |
                            v                  v                    |
                     +------+----------------------------------+    |
                     | Parser Service                         |    |
                     | spaCy + PDF/DOCX text extraction       |    |
                     | optional layout-aware parsing later    |    |
                     +------+----------------------------------+    |
                            |                                       |
                            v                                       |
                     +------+----------------+                      |
                     | PostgreSQL / MongoDB |                      |
                     | structured profiles  |                      |
                     +------+----------------+                      |
                            |                                       |
              +-------------+-------------+                         |
              |                           |                         |
              v                           v                         |
      +-------+--------+          +-------+--------+                |
      | Feature Service|          | Embedding Svc  |                |
      | explicit attrs |          | sentence model |                |
      +-------+--------+          +-------+--------+                |
              |                           |                         |
              +-------------+-------------+                         |
                            v                                       |
                     +------+----------------+                      |
                     | Vector Store          |                      |
                     | FAISS dev / Milvus    |                      |
                     +------+----------------+                      |
                            |                                       |
                            v                                       |
                     +------+----------------+                      |
                     | Ranking Service       |----------------------+
                     | heuristic -> ML rank  |
                     +------+----------------+
                            |
                            v
                     +------+----------------+
                     | shortlist.created     |
                     | notifications / ATS   |
                     +-----------------------+
```

## Service responsibilities

### 1. Ingestion API

Recommended stack:

- `FastAPI`
- `Pydantic`
- object storage client for `MinIO` or `S3`

Responsibilities:

- accept PDF, DOCX, and TXT uploads
- validate file type and size
- store the raw resume in object storage
- publish a `resume.raw` event with candidate and file metadata

### 2. Parser Service

Recommended stack:

- `spaCy`
- `pdfminer.six` or `pypdf` for PDF text extraction
- `python-docx` for DOCX

Responsibilities:

- extract raw text from uploaded files
- normalize text and sections
- extract entities such as name, skills, education, roles, projects, certifications
- persist a structured candidate profile

Upgrade path:

- add `LayoutLM` or other layout-aware models when plain text extraction loses important structure

### 3. Feature Service

Responsibilities:

- derive explicit features:
  - years of experience
  - required skill coverage
  - preferred skill coverage
  - education match
  - role seniority alignment
  - domain relevance

These features stay useful even after embeddings are added. They make the ranking model more interpretable.

### 4. Embedding Service

Recommended first model:

- `sentence-transformers/all-MiniLM-L6-v2`

Responsibilities:

- generate embeddings for resumes and job descriptions
- store resume vectors in FAISS or Milvus
- support semantic retrieval of top candidate profiles for each job description

### 5. Ranking Service

Phase 1 scoring:

```text
score =
  0.35 * semantic_similarity +
  0.25 * skill_coverage +
  0.20 * experience_alignment +
  0.10 * education_match +
  0.10 * role_relevance
```

Phase 2 scoring:

- train `LightGBM`, `XGBoost`, or learning-to-rank models
- labels can come from shortlist decisions, interview pass rates, and hiring outcomes

Responsibilities:

- combine explicit features and embedding similarity
- generate a final relevance score
- produce ranked lists and shortlist thresholds

### 6. Candidate API and HR Dashboard

Responsibilities:

- return ranked candidates for a given job
- expose explanations for candidate scores
- support recruiter filtering and shortlist workflows

## Event topics

Recommended first-pass topics:

- `resume.raw`
- `resume.parsed`
- `resume.features.created`
- `resume.embedding.created`
- `candidate.ranked`
- `shortlist.created`

## Storage choices

### Object storage

- `MinIO` in local development
- `S3` or MinIO in production

### Relational data

- `PostgreSQL` for jobs, candidate profiles, ranking outputs, and audit trails

### Vector data

- `FAISS` for local single-node development
- `Milvus` for distributed vector search at scale

### Optional document store

- `MongoDB` only if you need flexible semi-structured profile snapshots

For the first version, `PostgreSQL + JSONB` is usually enough.

## Why this improves on the baseline

### Resume parsing

Baseline issue:

- regex and RAKE fail on formatting variation and hidden semantics

Improvement:

- entity extraction and section-aware NLP parsing improve robustness

### Matching quality

Baseline issue:

- TF-IDF is keyword-heavy and weak on synonyms and related concepts

Improvement:

- sentence embeddings capture semantic similarity between resumes and job descriptions

### Ranking quality

Baseline issue:

- fixed rules are hard to calibrate and do not learn from outcomes

Improvement:

- combine interpretable features now and upgrade to supervised ranking later

### Scale

Baseline issue:

- Spark on the ingestion server is not the best default for every workload

Improvement:

- use lightweight services for the early pipeline and only scale compute-heavy stages independently

## Local development architecture for Ubuntu VMware

Use this setup first:

- APIs and workers as Python services
- `Redpanda` instead of full Kafka for local development
- `PostgreSQL`
- `MinIO`
- `FAISS`

This keeps setup manageable on a VM while preserving the same system boundaries you need in production.

## Production scale path

When local validation is complete:

- replace local FAISS with Milvus
- deploy services on Kubernetes
- use Kafka or Redpanda clusters
- add Airflow for batch workflows and retraining
- add model registry and offline evaluation pipelines
