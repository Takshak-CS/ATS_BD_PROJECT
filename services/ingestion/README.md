# Ingestion Service

Purpose:

- accept candidate resume uploads
- validate file metadata
- store raw files in object storage
- publish `resume.raw` events

Suggested implementation:

- `FastAPI`
- `Pydantic`
- `boto3` or MinIO client
- Kafka-compatible producer
