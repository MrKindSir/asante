import unittest

from asante_api.plan_documents import build_field_report, report_response
from asante_api.story_packet import render_report_pdf


class PlanDocumentTests(unittest.TestCase):
    def test_builder_reuses_planner_research_and_attributed_images(self):
        document = build_field_report({
            "title": "River memories",
            "place": "Soweto Towers",
            "claim": "Which dates need confirmation?",
            "plan": {"outline": ["Gather oral histories"], "questions": ["Who remembers the first gathering?"], "human_gate": "Reviewer approval required"},
            "research": {
                "summary": "Candidate sources describe several dates.",
                "sources": [{"title": "Local archive", "url": "https://example.org/archive", "excerpt": "Compare this account."}, {"title": "Unsafe URL", "url": "javascript:alert(1)"}],
                "images": [{"url": "https://upload.wikimedia.org/example.jpg", "caption": "Archive photograph", "credit": "Wikimedia contributor"}, {"url": "http://unsafe.example/image.jpg"}],
            },
        }, "project-1")
        self.assertEqual(document["title"], "River memories")
        self.assertEqual(document["sections"][0]["bullets"], ["Gather oral histories"])
        self.assertEqual([item["title"] for item in document["sources"]], ["Local archive"])
        self.assertEqual(len(document["images"]), 1)
        self.assertEqual(document["images"][0]["credit"], "Wikimedia contributor")

    def test_text_json_and_pdf_exports_render_document_blocks(self):
        document = {
            "title": "Community history",
            "subtitle": "A field report",
            "landmark": "Constitution Hill",
            "summary": "Compare accounts before drawing conclusions.",
            "sections": [{"id": "outline", "title": "Outline", "body": "Keep the narrator central.", "bullets": ["Record the date"], "icon": "◈"}],
            "charts": [{"id": "chart", "title": "Timeline evidence", "unit": "records", "series": [{"label": "Oral account", "value": 2}]}],
            "tables": [{"id": "table", "title": "Source comparison", "columns": ["Source", "Status"], "rows": [["Archive", "Candidate"]]}],
            "images": [{"url": "https://example.org/image.jpg", "caption": "Related image", "credit": "Photographer"}],
            "sources": [{"title": "Archive", "url": "https://example.org/archive", "excerpt": "Candidate source"}],
            "humanGate": "A human reviewer approves publication.",
        }
        text = report_response(document, "text")
        json_export = report_response(document, "json")
        pdf = render_report_pdf(document)
        self.assertIn("Timeline evidence", text.body.decode())
        self.assertIn("Source comparison", text.body.decode())
        self.assertIn("Photographer", text.body.decode())
        self.assertEqual(json_export.media_type, "application/json")
        self.assertTrue(pdf.startswith(b"%PDF-"))


if __name__ == "__main__":
    unittest.main()
