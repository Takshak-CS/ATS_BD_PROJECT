from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ats_embedding.jd_ingestion import parse_job_description


SAMPLE_JD = """
Job Title: Data Analyst
Location: Hyderabad, India
Employment Type: Full-time
Experience Required: 1-3 years

About the Role:
We are looking for a Data Analyst.

Key Responsibilities:
- Build reports
- Clean data

Required Skills:
- SQL
- Python

Preferred Skills:
- Tableau

Education:
Bachelor's degree in Statistics.

Good Fit Indicators:
- Clear communication
""".strip()


class JobDescriptionParsingTests(unittest.TestCase):
    def test_parse_job_description(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "data_analyst_jd_01.txt"
            path.write_text(SAMPLE_JD, encoding="utf-8")
            job = parse_job_description(path)

        self.assertEqual(job.job_id, "data_analyst_jd_01")
        self.assertEqual(job.job_title, "Data Analyst")
        self.assertEqual(job.required_skills, ["SQL", "Python"])
        self.assertEqual(job.preferred_skills, ["Tableau"])
        self.assertEqual(len(job.responsibilities), 2)


if __name__ == "__main__":
    unittest.main()
