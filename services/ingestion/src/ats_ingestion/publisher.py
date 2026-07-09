from __future__ import annotations

import argparse
from datetime import datetime
from datetime import timezone
from pathlib import Path

from ats_shared.events import EventProducer
from ats_shared.events import RESUME_UPLOADED_TOPIC
from ats_shared.events import load_kafka_settings


REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_ENV_FILE = REPO_ROOT / ".env"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish a resume.uploaded event for a local resume file.")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--resume-path", type=Path, required=True)
    parser.add_argument("--resume-id", default=None)
    parser.add_argument("--topic", default=RESUME_UPLOADED_TOPIC)
    return parser


def publish_resume_uploaded_event(
    payload: dict[str, object],
    env_file: Path = DEFAULT_ENV_FILE,
    topic: str = RESUME_UPLOADED_TOPIC,
) -> None:
    settings = load_kafka_settings(env_file)
    producer = EventProducer(settings, client_id="ats-ingestion-publisher")
    producer.publish(topic=topic, key=str(payload["resume_id"]), payload=payload)
    producer.flush()


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    path = resolve_resume_path(args.resume_path)
    resume_id = args.resume_id or path.stem
    payload = {
        "resume_id": resume_id,
        "source_filename": path.name,
        "source_path": str(path),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    publish_resume_uploaded_event(payload=payload, env_file=args.env_file, topic=args.topic)
    print(f"Published {args.topic} for {resume_id}.")
    return 0


def resolve_resume_path(path: Path) -> Path:
    resolved = path.expanduser()
    if not resolved.is_absolute():
        resolved = (REPO_ROOT / resolved).resolve()
    if not resolved.exists():
        raise RuntimeError(f"Resume file does not exist: {resolved}")
    return resolved
