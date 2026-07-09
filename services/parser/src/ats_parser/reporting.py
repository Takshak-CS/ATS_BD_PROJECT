from __future__ import annotations

from collections import Counter
from collections import defaultdict

from ats_parser.models import ResumeProfile


CONTACT_FIELDS = ("name", "email", "phone")
STRUCTURED_FIELDS = ("skills", "education", "experience", "projects")


class RunQualityTracker:
    def __init__(self, sample_limit: int = 10) -> None:
        self.sample_limit = sample_limit
        self.warning_counts: Counter[str] = Counter()
        self.missing_field_counts: Counter[str] = Counter()
        self.warning_examples: dict[str, list[str]] = defaultdict(list)
        self.missing_field_examples: dict[str, list[str]] = defaultdict(list)

    def record(self, profile: ResumeProfile) -> None:
        filename = profile.source_filename
        for warning in profile.metadata.warnings:
            self.warning_counts[warning] += 1
            if len(self.warning_examples[warning]) < self.sample_limit:
                self.warning_examples[warning].append(filename)

        for field in CONTACT_FIELDS:
            if not getattr(profile, field):
                self.missing_field_counts[field] += 1
                if len(self.missing_field_examples[field]) < self.sample_limit:
                    self.missing_field_examples[field].append(filename)

        for field in STRUCTURED_FIELDS:
            if not getattr(profile, field):
                self.missing_field_counts[field] += 1
                if len(self.missing_field_examples[field]) < self.sample_limit:
                    self.missing_field_examples[field].append(filename)

    def to_dict(self) -> dict[str, object]:
        return {
            "warning_counts": dict(self.warning_counts),
            "warning_examples": dict(self.warning_examples),
            "missing_field_counts": dict(self.missing_field_counts),
            "missing_field_examples": dict(self.missing_field_examples),
        }
