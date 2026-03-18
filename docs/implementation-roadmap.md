# Implementation Roadmap

## Phase 1: Foundation

Goal:

- create the core project skeleton and local infrastructure

Deliverables:

- ingestion service contract
- parser service contract
- shared schemas
- Docker Compose stack
- sample job description and resume fixtures

## Phase 2: Resume Parsing MVP

Goal:

- turn raw resumes into structured profiles

Deliverables:

- PDF, DOCX, and TXT extraction
- spaCy pipeline
- profile schema with:
  - name
  - email
  - phone
  - skills
  - education
  - experience
  - certifications
  - projects

Success criteria:

- parser handles at least 20 to 50 sample resumes with acceptable consistency

## Phase 3: Semantic Matching MVP

Goal:

- rank by semantic similarity instead of raw keywords

Deliverables:

- job description embedding generation
- resume embedding generation
- FAISS index build and search
- semantic similarity score

Success criteria:

- relevant resumes consistently appear in top retrieval results

## Phase 4: Ranking Service MVP

Goal:

- combine semantic and explicit features into shortlist scores

Deliverables:

- weighted score engine
- ranking API
- candidate explanations per score

Success criteria:

- top results are interpretable and stable across repeated runs

## Phase 5: Event-Driven Pipeline

Goal:

- make the system asynchronous and scalable

Deliverables:

- publish and consume resume lifecycle events
- idempotent workers
- retry and dead-letter handling

Success criteria:

- processing works even when downstream services restart

## Phase 6: Learning-Based Ranking

Goal:

- improve ranking from historical outcomes

Deliverables:

- labeled training dataset
- offline evaluation metrics
- LightGBM or XGBoost ranking model

Success criteria:

- model beats the heuristic baseline on offline evaluation

## Phase 7: AI Pre-screening

Goal:

- add optional conversational screening and scoring

Deliverables:

- question workflow
- transcript storage
- scoring rubric
- optional interview scheduling integration

Success criteria:

- screening output is consistent, auditable, and optional
