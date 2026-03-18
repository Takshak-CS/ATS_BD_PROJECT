# Parser Service

Purpose:

- extract resume text from PDF, DOCX, and TXT files
- run NLP parsing
- build structured candidate profiles
- publish `resume.parsed` events

Suggested implementation:

- `spaCy`
- `pdfminer.six` or `pypdf`
- `python-docx`
- PostgreSQL persistence
