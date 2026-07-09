from __future__ import annotations

import argparse
from pathlib import Path

from ats_parser.cli import DEFAULT_ENV_FILE
from ats_parser.cli import DEFAULT_OUTPUT_DIR
from ats_parser.config import load_postgres_settings
from ats_parser.parser import ResumeParser
from ats_parser.persistence import PostgresProfileRepository
from ats_parser.pipeline import process_resume_file
from ats_shared.events import EventConsumer
from ats_shared.events import EventProducer
from ats_shared.events import RESUME_PARSED_TOPIC
from ats_shared.events import RESUME_UPLOADED_TOPIC
from ats_shared.events import load_kafka_settings


REPO_ROOT = Path(__file__).resolve().parents[4]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Consume resume.uploaded events and parse resumes.")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--group-id", default="ats-parser-consumer")
    parser.add_argument("--input-topic", default=RESUME_UPLOADED_TOPIC)
    parser.add_argument("--output-topic", default=RESUME_PARSED_TOPIC)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    output_dir = args.output_dir.resolve()
    kafka_settings = load_kafka_settings(args.env_file, group_id=args.group_id)
    consumer = EventConsumer(kafka_settings, [args.input_topic], client_id="ats-parser-consumer")
    producer = EventProducer(kafka_settings, client_id="ats-parser-producer")
    parser = ResumeParser()
    repository = PostgresProfileRepository(load_postgres_settings(args.env_file))

    print(
        f"Parser consumer is listening on {args.input_topic} and will publish to {args.output_topic}."
    )
    try:
        while True:
            event = consumer.poll(timeout_seconds=1.0)
            if event is None:
                continue

            try:
                path = resolve_resume_path(event.payload)
                with repository.connect() as connection:
                    repository.ensure_schema(connection)
                    result = process_resume_file(
                        path=path,
                        output_dir=output_dir,
                        parser=parser,
                        overwrite=True,
                        repository=repository,
                        connection=connection,
                    )

                profile = result.profile
                producer.publish(
                    topic=args.output_topic,
                    key=profile.resume_id,
                    payload={
                        "resume_id": profile.resume_id,
                        "source_filename": profile.source_filename,
                        "source_path": profile.source_path,
                        "profile_path": str(result.profile_path),
                        "parsed_at": profile.parsed_at,
                        "warning_count": len(profile.metadata.warnings),
                    },
                )
                producer.flush()
                consumer.commit(event)
                print(f"Parsed event for {profile.resume_id} and published {args.output_topic}.")
            except Exception as exc:  # noqa: BLE001
                print(f"Failed to process parser event at offset {event.offset}: {exc}")
    except KeyboardInterrupt:
        print("Stopping parser consumer.")
    finally:
        producer.flush()
        consumer.close()

    return 0


def resolve_resume_path(payload: dict) -> Path:
    source_path = payload.get("source_path")
    if not source_path:
        raise RuntimeError("resume.uploaded event is missing source_path.")

    path = Path(source_path).expanduser()
    if not path.is_absolute():
        path = (REPO_ROOT / path).resolve()
    if not path.exists():
        raise RuntimeError(f"Resume file does not exist: {path}")
    return path


if __name__ == "__main__":
    raise SystemExit(main())
