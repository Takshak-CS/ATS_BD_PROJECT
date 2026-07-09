# Frontend Service

Purpose:

- show available job descriptions
- show ranked candidates per job
- show candidate profile and score breakdown detail
- upload new resumes into the ingestion pipeline

## Current status

This frontend reads recruiter data from the FastAPI read service and can now
push a raw file upload to the ingestion API. Uploaded resumes are staged and
published to `resume.uploaded`; downstream processing still depends on the
parser, embedding, and ranking consumers running separately.

## Local usage

Install dependencies:

```bash
cd services/frontend
npm install
```

Run the development server:

```bash
npm run dev
```

Optional API base URL:

```bash
VITE_API_BASE_URL=http://localhost:8000 npm run dev
```

Optional ingestion API base URL:

```bash
VITE_INGESTION_API_BASE_URL=http://localhost:8010 npm run dev
```
