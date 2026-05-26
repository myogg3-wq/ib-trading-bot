from pathlib import Path
import tempfile
import unittest

from app.web.design_audit import build_design_audit, render_markdown


class DesignAuditTests(unittest.TestCase):
    def test_build_design_audit_returns_checks(self):
        report = build_design_audit()
        self.assertGreaterEqual(report.overall_score, 1)
        self.assertGreaterEqual(report.overall_max, 10)
        self.assertGreaterEqual(len(report.checks), 5)
        self.assertTrue(report.summary)

    def test_render_markdown_contains_sections(self):
        report = build_design_audit()
        text = render_markdown(report)
        self.assertIn("Design Recursive Improvement Report", text)
        self.assertIn("Overall score", text)
        self.assertIn("Next Iteration Queue", text)


if __name__ == "__main__":
    unittest.main()
