# Candidate API

Purpose:

- expose job descriptions stored in PostgreSQL
- return ranked candidates for each job description
- return full candidate profile details with score breakdowns

## MVP scope

The API service is a recruiter-facing read layer for local Ubuntu development.
It reads from PostgreSQL only. There are no writes and no Kafka consumers in
this service.

Implemented endpoints:

- `GET /jobs`
- `GET /jobs/{job_id}/rankings`
- `GET /jobs/{job_id}/rankings/{resume_id}`
- `GET /health`

## Local usage

Install the service package:

```bash
python3 -m pip install -e services/api
```

Run directly from the repository root:

```bash
PYTHONPATH=services/api/src python3 -m ats_api
```

Or use the installed entry point:

```bash
ats-api
```

Default local URL:

```text
http://localhost:8000
```

## Endpoint reference

### `GET /jobs`

Returns all rows from `public.job_descriptions`, including the structured JSON
snapshot used by the embedding and ranking pipeline.

### `GET /jobs/{job_id}/rankings`

Returns ranked candidates from `public.job_candidate_rankings` joined with
`public.candidate_profiles`, ordered by `ranking_rank`.

### `GET /jobs/{job_id}/rankings/{resume_id}`

Returns:

- the job metadata
- the complete ranking row and score breakdown
- the complete candidate profile from `public.candidate_profiles`

## Docker

Build:

```bash
docker build -f services/api/Dockerfile -t ats-api .
```

Run:

```bash
docker run --rm -p 8000:8000 --env-file .env ats-api
```
