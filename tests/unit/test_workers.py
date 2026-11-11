"""Baseline unit tests for Asante planner, researcher, verifier and media processing."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app/services/api"))

from asante_api.ai.workers import fixture_plan, run_planner, run_verifier  # noqa: E402
from asante_api.ai.workers import run_researcher  # noqa: E402
from asante_api.ai.research import collect_evidence, is_safe_url, seed_social_matches, _evidence_item  # noqa: E402
from asante_api.media_process import extract_audio_track, process_upload_file, probe_media  # noqa: E402
from asante_api.ai import jobs as processing_jobs  # noqa: E402
from asante_api.ai.provider import ask_model, ask_model_media  # noqa: E402

FIXTURES = ROOT / "tests/fixtures/media"


class WorkerBaselineTests(unittest.TestCase):
    def test_researcher_uses_all_questionnaire_answers_and_optional_sources(self):
        answers = {"knownMaterial": "Oral history and https://example.com/archive", "questions": "Who gathered?",
                   "context": "Family names in 1976", "priorities": "Dates", "uncertainties": "Unknown year"}
        brief = {"topic": "Community memories", "claim": "When?", "place": "Soweto Towers", "researchBrief": answers}
        with patch("asante_api.ai.workers.ask_model", return_value=None) as model, patch(
            "asante_api.ai.workers.collect_evidence", new=AsyncMock(return_value=([{"url": "https://example.com/archive"}], []))
        ) as collect:
            asyncio.run(run_researcher(brief))
        self.assertEqual(model.call_args.args[1]["researchBrief"], answers)
        self.assertIn("Who gathered?", collect.call_args.args[0])
        self.assertIn("Dates", collect.call_args.args[0])
        self.assertEqual(collect.call_args.args[1], ["https://example.com/archive"])

    def test_research_progress_records_real_collector_actions(self):
        from asante_api.ai.activity import progress_sink
        source = {"title": "Archive", "url": "https://example.com/history", "excerpt": "Candidate source", "retrievalState": "search_snippet"}
        events = []
        async def record(kind, message, details):
            events.append((kind, message, details))
        async def run():
            token = progress_sink.set(record)
            try:
                client = AsyncMock()
                client.get.return_value = SimpleNamespace(text="<rss></rss>", raise_for_status=lambda: None)
                with patch("asante_api.ai.research.httpx.AsyncClient") as client_type, patch(
                    "asante_api.ai.research.search_web", return_value=[source]
                ), patch("asante_api.ai.research.search_social", return_value=[]), patch(
                    "asante_api.ai.research.enrich_page", new=AsyncMock(return_value=source)
                ):
                    client_type.return_value.__aenter__.return_value = client
                    await collect_evidence("Soweto community history")
            finally:
                progress_sink.reset(token)
        asyncio.run(run())
        self.assertTrue(any("Web collector" in message for _, message, _ in events))
        self.assertTrue(any("News collector returned 0" in message for _, message, _ in events))
        self.assertTrue(any(source["url"] in details for _, _, details in events))
        self.assertEqual(events[-1][0], "comparison")

    def test_fixture_plan_preserves_place_and_human_gate(self):
        plan = fixture_plan({"topic": "River memory", "place_name": "Soweto Towers", "language": "zu", "media_format": "audio"})
        self.assertEqual(plan["place_name"], "Soweto Towers")
        self.assertIn("human", plan["human_gate"].lower())
        self.assertGreaterEqual(len(plan["worker_steps"]), 3)
        self.assertFalse(plan["aiUsed"])

    def test_planner_falls_back_when_provider_disabled(self):
        with patch.dict("os.environ", {"ASANTE_OLLAMA_BASE_URL": "", "ASANTE_OLLAMA_UPSTREAM": "", "ASANTE_AI_PROVIDER": "fake", "ASANTE_AI_API_KEY": ""}, clear=False):
            plan = run_planner({"topic": "Mapungubwe clay", "place_name": "Mapungubwe Hill", "language": "en", "media_format": "video", "audience": "listeners"})
        self.assertEqual(plan["place_name"], "Mapungubwe Hill")
        self.assertFalse(plan["aiUsed"])
        self.assertTrue(plan["questions"])

    def test_safe_url_rejects_private_hosts(self):
        self.assertFalse(is_safe_url("http://example.com"))
        self.assertFalse(is_safe_url("https://127.0.0.1/x"))
        self.assertFalse(is_safe_url("https://localhost/x"))
        self.assertTrue(is_safe_url("https://www.example.com/path"))

    def test_seed_social_matches_youtube_catalogue(self):
        matches = seed_social_matches("Ethiopia ancient churches Lalibela")
        self.assertTrue(matches)
        self.assertTrue(all(item["status"] == "retrieved" for item in matches))
        self.assertTrue(all(item["retrievalState"] == "social_catalogue_entry" for item in matches))
        self.assertTrue(any("youtube" in (item.get("platform") or "") for item in matches))

    def test_research_results_preserve_distinct_retrieval_states(self):
        search = _evidence_item(title="Result", url="https://example.com/a", excerpt="Snippet", collector="web search")
        page = _evidence_item(title="Result", url="https://example.com/a", excerpt="Page text", collector="page")
        self.assertEqual(search["retrievalState"], "search_snippet")
        self.assertEqual(page["retrievalState"], "page_excerpt")
        self.assertEqual(search["duplicateGroup"], page["duplicateGroup"])

    def test_collect_evidence_uses_seed_when_search_empty(self):
        async def empty_web(_query):
            return []

        async def empty_social(_query):
            return []

        with patch("asante_api.ai.research.search_web", side_effect=lambda query, max_results=8: []), patch(
            "asante_api.ai.research.search_social", side_effect=lambda query, max_results=6: seed_social_matches(query)
        ), patch("asante_api.ai.research.news_items", return_value=[]):
            evidence, notes = asyncio.run(collect_evidence("Ethiopia ancient"))
        self.assertTrue(evidence)
        self.assertTrue(all(item.get("status") == "retrieved" for item in evidence))
        self.assertTrue(any("usable sources" in note for note in notes))

    def test_collect_evidence_fails_loud_when_empty(self):
        with patch("asante_api.ai.research.search_web", return_value=[]), patch(
            "asante_api.ai.research.search_social", return_value=[]
        ), patch("asante_api.ai.research.news_items", return_value=[]), patch(
            "asante_api.ai.research.seed_social_matches", return_value=[]
        ):
            with self.assertRaises(RuntimeError):
                asyncio.run(collect_evidence("zzzz-no-match-asante-xyz"))

    def test_verifier_blocks_missing_media_and_shares_contract(self):
        result = run_verifier(
            {"consent_given": True, "contributor_name": "Ada", "media_verified": False, "summary": "A story"},
            {"plan": {"trace_id": "trace_1"}, "suggestion": "accepted", "research": {"sources": [{"url": "https://example.com"}]}},
            [{"workerType": "planner"}, {"workerType": "researcher"}],
        )
        self.assertEqual(result["sharedContract"], "asante.review-policy.v1")
        self.assertEqual(result["status"], "blocked")
        self.assertGreaterEqual(result["blockedCount"], 1)
        self.assertTrue(any(item["kind"] == "media" and item["severity"] == "blocking" for item in result["findings"]))

    def test_verifier_passes_complete_packet(self):
        result = run_verifier(
            {
                "consent_given": True,
                "contributor_name": "Ada",
                "media_verified": True,
                "media_format": "video",
                "summary": "Remembered at the hill",
            },
            {
                "plan": {"trace_id": "trace_1"},
                "suggestion": "accepted",
                "research": {"sources": [{"url": "https://example.com", "title": "Source"}]},
                "mediaDerivatives": {"audio_track": {"objectKey": "derivatives/x/audio.wav"}},
            },
            [{"workerType": "planner"}, {"workerType": "researcher"}],
        )
        self.assertEqual(result["blockedCount"], 0)
        self.assertIn(result["status"], {"ready", "attention"})
        self.assertTrue(any(item["kind"] == "research" and item["severity"] == "info" for item in result["findings"]))


class MediaProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (FIXTURES / "sample_video.mp4").exists() or not (FIXTURES / "sample_audio.wav").exists():
            raise unittest.SkipTest("ffmpeg fixtures are missing under tests/fixtures/media")

    def test_probe_sample_video(self):
        probe = probe_media(FIXTURES / "sample_video.mp4")
        self.assertTrue(probe["hasVideo"])
        self.assertTrue(probe["hasAudio"])
        self.assertGreater(probe["duration"], 0)

    def test_extract_audio_from_video(self):
        with tempfile.TemporaryDirectory(prefix="asante-speech-test-") as directory:
            destination = Path(directory) / "generated_speech.wav"
            result = extract_audio_track(FIXTURES / "sample_video.mp4", destination)
            self.assertEqual(result["kind"], "audio_track")
            self.assertTrue(destination.exists())
            self.assertGreater(destination.stat().st_size, 100)

    def test_process_upload_builds_derivatives(self):
        with tempfile.TemporaryDirectory(prefix="asante-media-unit-") as directory:
            processed = process_upload_file(FIXTURES / "sample_video.mp4", directory)
            kinds = {item["kind"] for item in processed["derivatives"]}
            self.assertIn("audio_track", kinds)
            self.assertIn("poster", kinds)
            frames = [item for item in processed["derivatives"] if item["kind"] == "keyframe"]
            self.assertGreaterEqual(len(frames), 1)
            self.assertLessEqual(len(frames), 4)

    def test_folktale_clip_fixture_from_testdata(self):
        clip = FIXTURES / "folktale_clip.mp4"
        if not clip.exists():
            self.skipTest("optional TestData clip not generated")
        probe = probe_media(clip)
        self.assertTrue(probe["hasVideo"])

    def test_compact_testdata_video_fixture_has_audio_and_respects_upload_limit(self):
        probe = probe_media(FIXTURES / "folktale_testdata_30s.mp4")
        self.assertTrue(probe["hasVideo"])
        self.assertTrue(probe["hasAudio"])
        self.assertLessEqual(probe["duration"], 600)


class VideoJobTests(unittest.TestCase):
    def test_expired_job_lease_rejects_late_progress_write(self):
        job = SimpleNamespace(status="running", lease_owner="old-worker", lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1), progress=10)

        async def check():
            await processing_jobs._set_progress(AsyncMock(), job, 50)

        with self.assertRaisesRegex(RuntimeError, "lease expired"):
            asyncio.run(check())

    def test_audio_and_video_submit_enqueue_timed_translation(self):
        class Rows:
            def __init__(self, rows):
                self.rows = rows

            def all(self):
                return self.rows

        class FakeSession:
            def __init__(self):
                self.added = []
                self.called = False

            async def scalars(self, _query):
                if not self.called:
                    self.called = True
                    return Rows([])
                return Rows([SimpleNamespace(id="derivative-audio", kind="audio_track", object_key="private/audio.wav", meta={"duration": 2.0})])

            async def get(self, _model, _identity):
                return SimpleNamespace(object_key="private/original.mp4", content_type="video/mp4")

            def add(self, job):
                self.added.append(job)

            async def flush(self):
                return None

        session = FakeSession()
        packet = SimpleNamespace(
            id="submission-test", project_id="project-test", contributor_id="contributor-test", upload_id="upload-test",
            packet={"media_format": "video", "title": "Video story", "media_derivatives": [{"id": "derivative-audio"}]},
        )
        created = asyncio.run(processing_jobs.enqueue_submission_jobs(session, packet))
        self.assertEqual({job.job_type for job in created}, {"assessment", "transcribe", "translate", "analyze"})
        self.assertTrue(all(job.status == "queued" for job in created))
        self.assertEqual(created[0].input_payload["object_key"], "private/original.mp4")
        self.assertEqual(created[0].input_payload["media_derivatives"]["audio_track"]["objectKey"], "private/audio.wav")
        packet.packet["media_format"] = "audio"
        audio_created = asyncio.run(processing_jobs.enqueue_submission_jobs(FakeSession(), packet))
        self.assertEqual({job.job_type for job in audio_created}, {"assessment", "transcribe", "translate"})

    def test_translation_keeps_transcript_timestamps(self):
        segments = [{"start": 0.0, "end": 2.0, "text": "Hello"}, {"start": 2.0, "end": 4.0, "text": "Friends"}]
        response = {"status": "complete", "provider": "ollama", "model": "local", "error": "", "output": {"segments": [{"id": 0, "text": "Sawubona"}, {"id": 1, "text": "Bangani"}]}}
        with patch.object(processing_jobs, "ask_model_detailed", return_value=response):
            cues, result = processing_jobs.translate_caption_segments(segments, "en", "zu")
        self.assertEqual([(cue["start"], cue["end"]) for cue in cues], [(0.0, 2.0), (2.0, 4.0)])
        self.assertEqual([cue["text"] for cue in cues], ["Sawubona", "Bangani"])
        self.assertEqual(result["provider"], "ollama")

    def test_translation_retries_individual_cues_after_batch_timeout(self):
        segments = [{"start": 0.0, "end": 2.0, "text": "Hello"}, {"start": 2.0, "end": 4.0, "text": "Friends"}]
        timed_out = {"status": "timeout", "provider": "ollama", "model": "local", "error": "timed out", "output": None}
        singles = [
            {"status": "complete", "provider": "ollama", "model": "local", "error": "", "output": {"text": "Sawubona"}},
            {"status": "complete", "provider": "ollama", "model": "local", "error": "", "output": {"text": "Bangani"}},
        ]
        with patch.object(processing_jobs, "ask_model_detailed", side_effect=[timed_out, *singles]) as model:
            cues, result = processing_jobs.translate_caption_segments(segments, "en", "zu")
        self.assertEqual(model.call_count, 3)
        self.assertEqual([(cue["start"], cue["end"], cue["text"]) for cue in cues], [(0.0, 2.0, "Sawubona"), (2.0, 4.0, "Bangani")])
        self.assertEqual(result["status"], "complete")

    def test_unavailable_whisper_never_copies_contributor_summary_as_transcript(self):
        async def no_download(_key, destination):
            destination.write_bytes(b"test wav placeholder")
            return destination

        session = AsyncMock()
        job = SimpleNamespace(input_payload={"object_key": "private/original.mp4", "language": "en"}, progress=0, status="running", lease_owner="test-worker", lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5))
        packet = SimpleNamespace(packet={"summary": "Contributor's original story words"})
        with patch.object(processing_jobs, "_download_upload", side_effect=no_download), patch.object(
            processing_jobs, "_optional_whisper_transcribe", return_value=None
        ):
            result = asyncio.run(processing_jobs._run_transcribe(session, job, packet))
        self.assertEqual(result["transcriptDraft"]["status"], "unavailable")
        self.assertEqual(result["transcriptDraft"]["text"], "")
        self.assertIn("fabricated", result["transcriptDraft"]["note"].lower())
        self.assertNotEqual(result["transcriptDraft"]["text"], packet.packet["summary"])

    def test_configured_ollama_failure_does_not_fall_through_to_cloud(self):
        with patch.dict("os.environ", {
            "ASANTE_OLLAMA_BASE_URL": "http://ollama:11434",
            "ASANTE_OLLAMA_MODEL": "llama3.2:latest",
            "ASANTE_AI_PROVIDER": "gemini",
            "ASANTE_AI_API_KEY": "test-cloud-key",
        }, clear=False), patch("asante_api.ai.provider.httpx.post", side_effect=RuntimeError("offline")) as post:
            result = ask_model("Return JSON", {"question": "test"})
        self.assertIsNone(result)
        self.assertEqual(post.call_count, 1)
        self.assertIn("ollama:11434/api/chat", post.call_args.args[0])

    def test_media_helper_is_unavailable_when_no_provider_is_configured(self):
        with tempfile.TemporaryDirectory(prefix="asante-provider-test-") as directory:
            image = Path(directory) / "frame.jpg"
            image.write_bytes(b"small image test input")
            with patch.dict("os.environ", {"ASANTE_OLLAMA_BASE_URL": "", "ASANTE_AI_PROVIDER": "fake", "ASANTE_AI_API_KEY": ""}, clear=False):
                result = ask_model_media("Analyze frames", {"frameCount": 1}, [image])
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
