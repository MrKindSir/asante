"""ZIP contents, portable documents, and verified recording failure behavior."""
import csv
import hashlib
import json
from io import StringIO
import unittest
from unittest.mock import Mock, patch
from zipfile import ZipFile

from fastapi import HTTPException
from asante_api.story_packet import build_packet_archive


class StoryPacketTests(unittest.TestCase):
    def test_research_only_project_has_readable_docs_full_sources_and_honest_missing_sections(self):
        packet = {
            "title": "Izinkumbulo – memories", "place": "Soweto Towers", "claim": "Whose memory is this?", "attribution": "Nomsa",
            "transcript": "Keep these original words.", "version": 4,
            "research": {"searchQuery": "Soweto memories", "focus": "Compare histories", "notes": ["Collector unavailable"],
                         "report": {"summary": "The recorded date remains unresolved.", "findings": [{"text": "The source gives useful community context.", "sourceUrls": ["https://example.com/source"]}], "openQuestions": ["Which original record confirms the date?"]},
                         "sources": [{"title": "=Untrusted spreadsheet formula", "url": "https://example.com/source", "excerpt": "A full excerpt, with commas.\nAnd another line.", "retrievedAt": "2026-11-09T00:00:00Z"}],
                         "images": [{"url": "https://example.com/image.jpg", "caption": "Historic image", "credit": "Original artist"}]},
        }
        with build_packet_archive(packet) as stream, ZipFile(stream) as archive:
            self.assertIsNone(archive.testzip())
            self.assertTrue({"README.txt", "field-report.pdf", "field-report.html", "field-report.txt", "story-brief.txt", "project.json", "transcript.txt", "research/sources.csv", "research/research.json", "research/research-notes.txt"}.issubset(archive.namelist()))
            self.assertTrue(archive.read("field-report.pdf").startswith(b"%PDF-"))
            self.assertEqual(json.loads(archive.read("project.json")), packet)
            self.assertIn("Izinkumbulo – memories", archive.read("field-report.txt").decode())
            self.assertIn("The recorded date remains unresolved.", archive.read("field-report.txt").decode())
            self.assertIn("Which original record confirms the date?", archive.read("field-report.txt").decode())
            notes = archive.read("research/research-notes.txt").decode()
            self.assertIn("And another line.", notes)
            self.assertIn("Original artist", notes)
            rows = list(csv.DictReader(StringIO(archive.read("research/sources.csv").decode("utf-8-sig"))))
            self.assertEqual(rows[0]["title"], "'=Untrusted spreadsheet formula")
            self.assertEqual(rows[0]["excerpt"], packet["research"]["sources"][0]["excerpt"])
            guide = archive.read("README.txt").decode()
            self.assertIn("Story plan: not prepared", guide)
            self.assertIn("no verified recording", guide)
            self.assertIn("third-party files are not copied", guide)

    def test_saved_report_edits_and_verification_are_preserved_and_html_is_escaped(self):
        document = {"title": "Edited report", "summary": '<p>Contributor’s summary &amp; voice</p>', "sections": [{"title": 'Findings <img src=x onerror="alert(1)">', "body": "Final evidence END-OF-REPORT"}], "sources": [{"title": "Source", "url": "https://example.com", "note": "Compare manually"}]}
        packet = {"title": "Story", "plan": {"document": document}, "verification": {"summary": "Needs attention", "findings": [{"severity": "attention", "message": "Compare the date", "references": ["source-1"]}]}}
        with build_packet_archive(packet) as stream, ZipFile(stream) as archive:
            self.assertIn("Contributor’s summary & voice", archive.read("field-report.txt").decode())
            self.assertIn("END-OF-REPORT", archive.read("field-report.html").decode())
            self.assertNotIn("<img", archive.read("field-report.html").decode())
            self.assertIn("Compare the date", archive.read("verification.txt").decode())
            self.assertIn("source-1", archive.read("verification.txt").decode())

    def test_original_recording_is_copied_byte_for_byte_without_unsafe_filename_or_storage_key(self):
        data = b"verified audio bytes"
        media = {"name": "../../unsafe.mp3", "type": "audio/mpeg", "size": len(data), "checksum": hashlib.sha256(data).hexdigest(), "objectKey": "private/original"}
        response = Mock()
        response.stream.return_value = [data[:6], data[6:]]
        client = Mock()
        client.get_object.return_value = response
        with patch("asante_api.story_packet.storage_client", return_value=client), patch("asante_api.story_packet.media_bucket", return_value="test-bucket"):
            with build_packet_archive({"title": "Story"}, media=media) as stream, ZipFile(stream) as archive:
                self.assertEqual(archive.read("media/original.mp3"), data)
                self.assertNotIn("objectKey", archive.read("media/recording.json").decode())
                self.assertTrue(all(".." not in name for name in archive.namelist()))
        response.close.assert_called_once()
        response.release_conn.assert_called_once()

    def test_unavailable_or_corrupt_original_fails_the_whole_export(self):
        media = {"name": "original.mp3", "type": "audio/mpeg", "size": 4, "checksum": hashlib.sha256(b"good").hexdigest(), "objectKey": "private/original"}
        for chunks in ([b"bad"], [b"bad!"], [b"oversized"]):
            response = Mock()
            response.stream.return_value = chunks
            client = Mock()
            client.get_object.return_value = response
            with patch("asante_api.story_packet.storage_client", return_value=client), patch("asante_api.story_packet.media_bucket", return_value="test-bucket"):
                with self.assertRaises(HTTPException) as raised:
                    build_packet_archive({"title": "Story"}, media=media)
                self.assertEqual(raised.exception.status_code, 503)
            response.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
