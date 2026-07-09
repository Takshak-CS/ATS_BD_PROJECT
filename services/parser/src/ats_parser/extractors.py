from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from pdfminer.high_level import extract_text as extract_pdf_text


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}


def extract_text(path: Path) -> tuple[str, list[str]]:
    """Extract text from a supported resume file."""
    suffix = path.suffix.lower()
    warnings: list[str] = []

    if suffix == ".pdf":
        text, used_fallback = _extract_pdf_text(path)
        if used_fallback:
            warnings.append("pdftotext was not available, so PDF extraction fell back to pdfminer.six.")
    elif suffix == ".docx":
        text = _extract_docx_text(path)
    elif suffix == ".txt":
        text = path.read_text(encoding="utf-8", errors="ignore")
    else:
        raise ValueError(f"Unsupported resume format: {path.suffix}")

    normalized = normalize_extracted_text(text)
    if not normalized.strip():
        warnings.append("No text could be extracted from the source file.")

    return normalized, warnings


def _extract_pdf_text(path: Path) -> tuple[str, bool]:
    pdftotext_path = shutil.which("pdftotext")
    if pdftotext_path:
        result = subprocess.run(
            [pdftotext_path, "-layout", str(path), "-"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout, False

    return extract_pdf_text(str(path)), True


def _extract_docx_text(path: Path) -> str:
    try:
        import docx
    except ImportError as exc:
        raise RuntimeError(
            "DOCX parsing requires python-docx. Install the parser service "
            "dependencies before processing .docx files."
        ) from exc

    document = docx.Document(str(path))
    parts = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
    return "\n".join(parts)


def normalize_extracted_text(text: str) -> str:
    text = text.replace("\uf0b7", "•")
    text = text.replace("\u2022", "•")
    text = text.replace("\u2023", "•")
    text = text.replace("\u25aa", "•")
    text = text.replace("\uf0a7", "•")
    text = text.replace("\u00a0", " ")
    text = text.replace("\x0c", "\n")
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    lines = [line.rstrip() for line in text.split("\n")]
    compacted: list[str] = []
    blank_streak = 0

    for line in lines:
        if not line.strip():
            blank_streak += 1
            if blank_streak <= 1:
                compacted.append("")
            continue

        blank_streak = 0
        compacted.append(line.replace("\t", "    ").strip())

    return "\n".join(compacted).strip()
