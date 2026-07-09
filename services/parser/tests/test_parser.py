from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ats_parser.parser import ResumeParser
from ats_parser.parser import extract_primary_email
from ats_parser.parser import extract_primary_phone
from ats_parser.parser import split_sections


SAMPLE_RESUME = """
SHRINU KUSHAGRA
email: shrinukushagra@gmail.com
Phone: +91-9735301541

ACADEMEIC PROFILE
2007-Present B.Tech in Computer Science and Engineering Indian Institute of Technology Kharagpur CGPA : 8.16
2007 Senior Secondary Central Academy Kota 86.60%

SKILLS
Programming languages: C, Java, Python, Verilog
Web Designing Languages: HTML, PHP, JavaScript, Ajax
Operating Systems : Windows, Linux

PROJECTS
Guide: Prof. Rajib Mall
TOPIC Analysis and Testing of Object Oriented Programs
WORK DONE: Dynamic and Static Java Byte Code Instrumentation.
""".strip()


class ResumeParserTests(unittest.TestCase):
    def test_contacts_are_extracted(self) -> None:
        self.assertEqual(extract_primary_email(SAMPLE_RESUME), "shrinukushagra@gmail.com")
        self.assertEqual(extract_primary_phone(SAMPLE_RESUME), "+919735301541")

    def test_sections_are_detected(self) -> None:
        sections = split_sections(SAMPLE_RESUME).as_text()
        self.assertIn("education", sections)
        self.assertIn("skills", sections)
        self.assertIn("projects", sections)

    def test_resume_profile_contains_expected_fields(self) -> None:
        parser = ResumeParser()
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "c1.pdf"
            path.write_text("sample", encoding="utf-8")
            profile = parser.parse_file(path=path, text=SAMPLE_RESUME)

            self.assertEqual(profile.name, "Shrinu Kushagra")
            self.assertIn("Python", profile.skills)
            self.assertEqual(len(profile.education), 2)
            self.assertEqual(profile.projects[0].name, "Analysis and Testing of Object Oriented Programs")


if __name__ == "__main__":
    unittest.main()
