from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ats_parser.config import load_env_file
from ats_parser.config import load_postgres_settings
from ats_parser.models import ExtractionMetadata
from ats_parser.models import ResumeProfile
from ats_parser.persistence import validate_identifier
from ats_parser.reporting import RunQualityTracker


class ConfigAndReportingTests(unittest.TestCase):
    def test_env_file_loading_and_postgres_settings(self) -> None:
        with TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "POSTGRES_DB=ats",
                        "POSTGRES_USER=ats_user",
                        "POSTGRES_PASSWORD=ats_password",
                        "POSTGRES_HOST=localhost",
                        "POSTGRES_PORT=5432",
                    ]
                ),
                encoding="utf-8",
            )

            values = load_env_file(env_path)
            settings = load_postgres_settings(env_path, schema="public", table="candidate_profiles")

        self.assertEqual(values["POSTGRES_DB"], "ats")
        self.assertEqual(settings.database, "ats")
        self.assertEqual(settings.port, 5432)

    def test_identifier_validation(self) -> None:
        self.assertEqual(validate_identifier("candidate_profiles"), "candidate_profiles")
        with self.assertRaises(ValueError):
            validate_identifier("candidate-profiles")

    def test_quality_tracker_counts_missing_fields(self) -> None:
        tracker = RunQualityTracker(sample_limit=2)
        profile = ResumeProfile(
            resume_id="c1",
            source_path="data/raw/resumes/c1.pdf",
            source_filename="c1.pdf",
            parsed_at="2026-03-19T00:00:00+00:00",
            name=None,
            email=None,
            phone="1234567890",
            skills=[],
            education=[],
            experience=[],
            certifications=[],
            projects=[],
            sections={},
            raw_text="sample",
            metadata=ExtractionMetadata(
                file_type="pdf",
                source_sha256="abc",
                text_length=6,
                warnings=["Name could not be extracted confidently."],
                spacy_model="blank_en_sentencizer",
            ),
        )

        tracker.record(profile)
        summary = tracker.to_dict()

        self.assertEqual(summary["warning_counts"]["Name could not be extracted confidently."], 1)
        self.assertEqual(summary["missing_field_counts"]["name"], 1)
        self.assertEqual(summary["missing_field_counts"]["email"], 1)
        self.assertEqual(summary["missing_field_counts"]["skills"], 1)


if __name__ == "__main__":
    unittest.main()
