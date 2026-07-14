# Parser Service

Purpose:

- extract resume text from PDF, DOCX, and TXT files
- run practical NLP-assisted parsing
- build structured candidate profiles
- prepare data for later `resume.parsed` events and PostgreSQL persistence

## MVP scope

The parser MVP is a local batch worker for Ubuntu development. It reads
resume files from `data/raw/resumes/`, extracts text, identifies major resume
sections, and writes one structured JSON profile per resume under
`data/processed/parser/profiles/`.

The output schema includes:

- candidate name
- email
- phone
- skills
- education
- experience
- certifications
- projects
- extracted section text
- raw resume text and parsing metadata

The manifest at `data/processed/parser/manifest.json` also records:

- warning counts
- missing-field counts
- sample filenames for common warning patterns
- how many profiles were persisted to PostgreSQL

## Local usage

Run directly from the repository root:

```bash
PYTHONPATH=services/parser/src python3 -m ats_parser \
  --input-dir data/raw/resumes \
  --output-dir data/processed/parser
```

Persist parsed profiles into PostgreSQL as JSONB:

```bash
PYTHONPATH=services/parser/src python3 -m ats_parser \
  --input-dir data/raw/resumes \
  --output-dir data/processed/parser \
  --persist-postgres
```

Optional editable install:

```bash
python3 -m pip install -e shared -e services/parser
ats-parser
```

Kafka consumer entry point:

```bash
PYTHONPATH=shared/src:services/parser/src python3 -m ats_parser.consumer
```

## Notes

- The parser tries to load `en_core_web_sm` if it is installed, then falls
  back to a blank English spaCy pipeline with sentence segmentation only.
- PDF extraction uses `pdftotext -layout` when `poppler-utils` is available,
  then falls back to `pdfminer.six`.
- DOCX extraction uses `python-docx` when available.
- Known limitation: the current heuristic skill extraction under-recognizes
  some valid resume phrasing and formatting, especially broad "computer skills"
  bullet lists such as `Ms. Office`, `XP Window`, and similar legacy tool
  labels. Some resumes with visible skill content can still end up with
  `No skills detected.` in the parser manifest.
- The current implementation is intentionally heuristic-first so it stays easy
  to run and debug inside Ubuntu before the rest of the pipeline is added.
- The Kafka consumer listens for `resume.uploaded` and publishes
  `resume.parsed` after successful PostgreSQL persistence.
