# Ingestion Service

Purpose:

- accept candidate resume uploads
- validate file metadata
- store raw files in object storage
- publish `resume.uploaded` events

Suggested implementation:

- `FastAPI`
- `Pydantic`
- `boto3` or MinIO client
- Kafka-compatible producer

## Current implementation

The service now has two local entry points:

- an HTTP upload API for recruiter or test uploads
- the existing local publisher CLI for seeding events from a file already on disk

The upload API stages files into `data/raw/uploads/` by default and publishes a
`resume.uploaded` event that the current parser consumer can process without
changes.

Run the API:

```bash
PYTHONPATH=shared/src:services/ingestion/src python3 -m ats_ingestion.app
```

Or use the installed entry point:

```bash
ats-ingestion-api
```

Upload a resume with raw request bytes:

```bash
curl -X POST http://localhost:8010/uploads/resumes \
  -H "x-filename: c1.pdf" \
  -H "Content-Type: application/pdf" \
  --data-binary @data/raw/resumes/c1.pdf
```

Optional override:

- `x-resume-id`

The local publisher CLI remains available:

```bash
PYTHONPATH=shared/src:services/ingestion/src python3 -m ats_ingestion \
  --resume-path data/raw/resumes/c1.pdf
```

Both paths publish a `resume.uploaded` event with:

- `resume_id`
- `source_filename`
- `source_path`
- `uploaded_at`
