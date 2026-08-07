# Running the pipeline

The current batch pipeline runs in three stages:

```text
resume PDFs → parser → PostgreSQL candidate profiles
            → JD ingestion + embeddings + FAISS retrieval
            → heuristic ranking
```

---

## 1. Environment

Copy the example environment file and fill in credentials:

```bash
cp .env.example .env
```

`.env.example` documents every variable the services read — PostgreSQL connection details, MinIO credentials, and the Redpanda broker address. No credentials are committed to this repository.

Recommended system package for more reliable PDF text extraction:

```bash
sudo apt-get install -y poppler-utils
```

Optional spaCy model. The parser runs without it using a smaller fallback pipeline, at some cost to extraction quality:

```bash
python3 -m spacy download en_core_web_sm
```

---

## 2. Infrastructure

For the batch pipeline, PostgreSQL alone is sufficient:

```bash
docker compose -f infra/docker-compose.yml up -d postgres
```

For the full local stack, including object storage and the broker:

```bash
docker compose -f infra/docker-compose.yml up -d
```

---

## 3. Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -e services/parser -e services/embedding -e services/ranking
```

Services are installed as editable packages so that each can be developed independently.

---

## 4. Parser

Reads resumes from `data/raw/resumes/`, writes structured JSON, and persists profiles to PostgreSQL:

```bash
PYTHONPATH=services/parser/src python3 -m ats_parser \
  --input-dir data/raw/resumes \
  --output-dir data/processed/parser \
  --overwrite \
  --persist-postgres
```

**Outputs**

- `data/processed/parser/profiles/*.json`
- `data/processed/parser/manifest.json` — extraction quality summary
- PostgreSQL: `public.candidate_profiles`

---

## 5. Embeddings and retrieval

Reads job descriptions, embeds both jobs and candidates, builds the FAISS index, and writes top-k retrievals:

```bash
PYTHONPATH=services/embedding/src python3 -m ats_embedding \
  --jd-dir data/raw/job_descriptions \
  --artifacts-dir data/processed/embedding \
  --top-k 25
```

**Outputs**

- `data/processed/embedding/faiss/candidate_profiles.index`
- `data/processed/embedding/faiss/candidate_profiles.meta.json`
- `data/processed/embedding/retrievals/*.json`
- PostgreSQL: `public.job_descriptions`, `public.candidate_profile_embeddings`, `public.job_description_embeddings`, `public.job_candidate_retrievals`

---

## 6. Ranking

Combines semantic retrieval with parser-derived features:

```bash
PYTHONPATH=services/ranking/src python3 -m ats_ranking \
  --artifacts-dir data/processed/ranking \
  --top-n 10
```

**Outputs**

- `data/processed/ranking/*.json`
- PostgreSQL: `public.job_candidate_rankings`

---

## 7. Inspecting results

Extraction quality: `data/processed/parser/manifest.json`
Semantic retrieval: `data/processed/embedding/retrievals/`
Final rankings: `data/processed/ranking/`

Query the ranked output directly:

```bash
psql "$DATABASE_URL" -c "
  SELECT job_id, resume_id, ranking_rank, final_score
  FROM public.job_candidate_rankings
  ORDER BY job_id, ranking_rank
  LIMIT 15;"
```

---

## Notes on the development environment

The pipeline expects a Linux filesystem. Running it from a mounted Windows share causes problems with Docker bind mounts, Python virtual environments, and file watching — clone into the native Linux filesystem instead.
