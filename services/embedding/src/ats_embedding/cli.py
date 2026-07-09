from __future__ import annotations

import argparse
from pathlib import Path

from ats_embedding.embeddings import DEFAULT_MODEL_NAME
from ats_embedding.pipeline import run_embedding_pipeline


REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_ENV_FILE = REPO_ROOT / ".env"
DEFAULT_JD_DIR = REPO_ROOT / "data" / "raw" / "job_descriptions"
DEFAULT_ARTIFACTS_DIR = REPO_ROOT / "data" / "processed" / "embedding"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest job descriptions, generate embeddings, and run FAISS retrieval.")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--jd-dir", type=Path, default=DEFAULT_JD_DIR)
    parser.add_argument("--artifacts-dir", type=Path, default=DEFAULT_ARTIFACTS_DIR)
    parser.add_argument("--model-name", default=DEFAULT_MODEL_NAME)
    parser.add_argument("--top-k", type=int, default=25)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        result = run_embedding_pipeline(
            env_file=args.env_file,
            jd_dir=args.jd_dir.resolve(),
            artifacts_dir=args.artifacts_dir.resolve(),
            model_name=args.model_name,
            top_k=args.top_k,
        )
    except RuntimeError as exc:
        print(exc)
        return 1

    print(
        f"Ingested {result.job_count} job description(s), embedded {result.candidate_count} "
        f"candidate profile(s), and stored top-{result.top_k} retrievals per job."
    )
    return 0
