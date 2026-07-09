# Ranking Service

Purpose:

- combine semantic retrieval with explicit parser-derived features
- compute candidate relevance scores per job description
- persist ranked candidate lists into PostgreSQL
- write local ranking artifacts for inspection
- export offline ranking datasets, evaluate metrics, and compare ML rerankers

## MVP scope

The ranking MVP reads job descriptions, candidate profiles, and semantic
retrievals from PostgreSQL. It applies a weighted heuristic score that combines
semantic similarity, skill coverage, experience alignment, education match, and
role relevance.

## Local usage

Run directly from the repository root after the embedding service:

```bash
PYTHONPATH=services/ranking/src python3 -m ats_ranking \
  --artifacts-dir data/processed/ranking \
  --top-n 10
```

Kafka consumer entry point:

```bash
PYTHONPATH=shared/src:services/ranking/src python3 -m ats_ranking.consumer
```

## Notes

- PostgreSQL table created by this service: `job_candidate_rankings`
- Ranking is intentionally heuristic-first and explainable.
- The Kafka consumer listens for `resume.embedded` and publishes
  `candidate.ranked` after refreshing the ranking outputs.

## Offline Evaluation Workflow

The live ranking path remains heuristic-first. Offline evaluation and ML
experiments are additive and use a separate CLI:

```bash
ats-ranking-offline
```

### 1. Labeling format

Use JSONL with one labeled job-resume pair per line:

```json
{"job_id":"ml_engineer_jd_01","resume_id":"c1","label":3,"split":"train","source":"manual_review","notes":"Strong fit"}
```

Fields:

- `job_id`: required
- `resume_id`: required
- `label`: required integer relevance grade
  - `0` = not relevant
  - `1` = weak / partial match
  - `2` = good match
  - `3` = strong match
- `split`: optional `train`, `validation`, or `test`
- `source`: optional provenance
- `notes`: optional reviewer notes

Example file:

- `services/ranking/examples/relevance_labels.example.jsonl`

### 2. Export offline feature dataset

This exports one row per retrieved job-resume pair with:

- heuristic ranking signals
- parser quality signals
- optional labels merged from the JSONL file

```bash
PYTHONPATH=services/ranking/src python3 -m ats_ranking.offline_cli export-dataset \
  --labels-path data/labels/resume_jd_relevance.jsonl \
  --output-path data/processed/ranking/offline/ranking_dataset.jsonl
```

Feature columns include:

- `semantic_similarity`
- `skill_coverage`
- `experience_alignment`
- `education_match`
- `role_relevance`
- `warning_count`
- `parser_quality_score`
- `education_count`
- `experience_count`
- `project_count`
- `skills_count`
- `has_name`
- `has_email`
- `has_phone`
- `required_skill_count`
- `preferred_skill_count`

The exported dataset also includes:

- `heuristic_score`
- `heuristic_adjusted_score`
- `retrieval_rank`
- `heuristic_rank`
- `label`
- `split`

### 3. Evaluate heuristic ranking

```bash
PYTHONPATH=services/ranking/src python3 -m ats_ranking.offline_cli evaluate \
  --dataset-path data/processed/ranking/offline/ranking_dataset.jsonl \
  --score-field heuristic_score \
  --score-field heuristic_adjusted_score
```

Reported metrics:

- `Precision@5`
- `Recall@10`
- `NDCG@10`

### 4. Train offline ML reranker

Install the optional dependency first:

```bash
python3 -m pip install -e "services/ranking[offline-ml]"
```

Then train and compare:

```bash
PYTHONPATH=services/ranking/src python3 -m ats_ranking.offline_cli train-reranker \
  --dataset-path data/processed/ranking/offline/ranking_dataset.jsonl
```

Artifacts written under the offline output directory include:

- exported evaluation predictions
- heuristic vs ML comparison JSON
- XGBoost model artifact
- model metadata with feature names and split usage
