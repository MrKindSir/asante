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
from asante_api.media_process import create_hls_1080p, extract_audio_track, process_upload_file, probe_media  # noqa: E402
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
            self.assertNotIn("hls_playlist", kinds)

    def test_create_hls_1080p_builds_master_and_quality_package(self):
        with tempfile.TemporaryDirectory(prefix="asante-hls-unit-") as directory:
            package = create_hls_1080p(FIXTURES / "sample_video.mp4", Path(directory) / "hls")
            master = Path(package["path"])
            quality = master.parent / "1080p" / "playlist.m3u8"
            self.assertEqual(package["kind"], "hls_playlist")
            self.assertEqual(package["profile"], "1080p")
            self.assertTrue(master.exists())
            self.assertTrue(quality.exists())
            self.assertIn("1080p/playlist.m3u8", master.read_text(encoding="utf-8"))
            self.assertGreaterEqual(package["segmentCount"], 1)
            self.assertLessEqual(int(package["height"]), 1080)
            self.assertTrue(any((master.parent / "1080p").glob("segment_*.ts")))

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

    def test_worker_progress_checkpoints_are_saved_for_reviewer_trail(self):
        job = SimpleNamespace(
            status="running", lease_owner="worker-a", lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=2),
            progress=5, job_type="transcribe", result_payload={},
        )

        async def check():
            await processing_jobs._set_progress(AsyncMock(), job, 35)

        asyncio.run(check())
        events = job.result_payload["workerTrail"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["label"], "Preparing speech audio")
        self.assertEqual(events[0]["state"], "running")
        self.assertIn("Extracting", events[0]["detail"])
        self.assertTrue(events[0]["at"])

    def test_audio_and_video_submit_enqueue_timed_translation(self):
        class Rows:
            def __init__(self, rows):
                self.rows = rows

            def all(self):
                return self.rows

        class FakeSession:
            def __init__(self):
                self.added = []
                self.calls = 0

            async def scalars(self, _query):
                self.calls += 1
                if self.calls <= 2:
                    return Rows([])
                return Rows([SimpleNamespace(id="derivative-audio", kind="audio_track", object_key="private/audio.wav", meta={"duration": 2.0})])

            async def get(self, _model, _identity):
                return SimpleNamespace(id="upload-test", object_key="private/original.mp4", content_type="video/mp4", name="clip.mp4")

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
        self.assertEqual({job.job_type for job in created}, {"assessment", "hls", "transcribe", "translate", "analyze"})
        self.assertTrue(all(job.status == "queued" for job in created))
        self.assertEqual(created[0].input_payload["object_key"], "private/original.mp4")
        self.assertEqual(created[0].input_payload["media_derivatives"]["audio_track"]["objectKey"], "private/audio.wav")
        self.assertIn("captionLimits", created[0].input_payload)
        packet.packet["media_format"] = "audio"
        audio_created = asyncio.run(processing_jobs.enqueue_submission_jobs(FakeSession(), packet))
        self.assertEqual({job.job_type for job in audio_created}, {"assessment", "transcribe", "translate"})

    def test_verified_draft_media_enqueues_capped_jobs_without_assessment(self):
        class Rows:
            def __init__(self, rows):
                self.rows = rows

            def all(self):
                return self.rows

        class FakeSession:
            def __init__(self):
                self.added = []
                self.calls = 0

            async def scalars(self, _query):
                self.calls += 1
                if self.calls == 1:
                    return Rows([SimpleNamespace(id="derivative-audio", kind="audio_track", object_key="private/audio.wav", meta={"duration": 2.0})])
                return Rows([])

            def add(self, job):
                self.added.append(job)

            async def flush(self):
                return None

        project = SimpleNamespace(id="project-draft", contributor_id="contributor-draft", content={"title": "Draft audio", "language": "en", "format": "audio"})
        upload = SimpleNamespace(id="upload-draft", purpose="media", status="verified", content_type="audio/mpeg", name="demo.mp3", object_key="private/demo.mp3")
        with patch.dict("os.environ", {"ASANTE_AI_BACKEND": "modal", "ASANTE_LIVE_CAPTION_SECONDS": "45", "ASANTE_LIVE_TRANSLATE_MAX_CUES": "12"}, clear=False):
            created = asyncio.run(processing_jobs.enqueue_project_media_jobs(FakeSession(), project=project, upload=upload))
        self.assertEqual({job.job_type for job in created}, {"transcribe", "translate"})
        self.assertTrue(all(job.submission_id is None for job in created))
        self.assertEqual(created[0].input_payload["captionLimits"]["captionSeconds"], 45)
        self.assertEqual(created[0].input_payload["captionLimits"]["translateMaxCues"], 12)

    def test_verified_draft_video_enqueues_hls_job(self):
        class Rows:
            def __init__(self, rows):
                self.rows = rows

            def all(self):
                return self.rows

        class FakeSession:
            def __init__(self):
                self.added = []
                self.calls = 0

            async def scalars(self, _query):
                self.calls += 1
                if self.calls == 1:
                    return Rows([])
                return Rows([])

            def add(self, job):
                self.added.append(job)

            async def flush(self):
                return None

        project = SimpleNamespace(id="project-video", contributor_id="contributor-video", content={"title": "Draft video", "language": "en", "format": "video"})
        upload = SimpleNamespace(id="upload-video", purpose="media", status="verified", content_type="video/mp4", name="clip.mp4", object_key="private/clip.mp4")
        created = asyncio.run(processing_jobs.enqueue_project_media_jobs(FakeSession(), project=project, upload=upload))
        self.assertEqual({job.job_type for job in created}, {"hls", "transcribe", "translate", "analyze"})
        self.assertEqual(next(job for job in created if job.job_type == "hls").priority, 15)

    def test_submission_jobs_requeue_cancelled_work_and_refresh_inputs(self):
        cancelled = SimpleNamespace(
            id="job-cancelled", job_type="assessment", status="cancelled", progress=72, attempt=2,
            input_payload={"old": True}, result_payload={"old": True}, safe_error="stopped",
            lease_owner="worker-old", lease_expires_at=object(), started_at=object(), finished_at=object(),
        )

        class Rows:
            def __init__(self, rows):
                self.rows = rows

            def all(self):
                return self.rows

        class FakeSession:
            def __init__(self):
                self.calls = 0

            async def scalars(self, _query):
                self.calls += 1
                return Rows([cancelled] if self.calls == 1 else [])

            async def get(self, _model, _identity):
                return SimpleNamespace(id="upload-old", object_key="private/video.mp4", content_type="video/mp4", name="clip.mp4")

            def add(self, _job):
                return None

            async def flush(self):
                return None

        packet = SimpleNamespace(
            id="submission-old", project_id="project-old", contributor_id="contributor-old", upload_id="upload-old",
            packet={"media_format": "video", "title": "A story", "summary": "Updated summary"},
        )
        jobs = asyncio.run(processing_jobs.enqueue_submission_jobs(FakeSession(), packet))
        self.assertEqual(cancelled.status, "queued")
        self.assertEqual((cancelled.progress, cancelled.attempt), (0, 0))
        self.assertEqual(cancelled.result_payload, {})
        self.assertEqual(cancelled.input_payload["summary"], "Updated summary")
        self.assertEqual(cancelled.safe_error, "")
        self.assertEqual(cancelled.lease_owner, "")
        self.assertIsNone(cancelled.lease_expires_at)
        self.assertIsNone(cancelled.started_at)
        self.assertIsNone(cancelled.finished_at)
        self.assertEqual({job.job_type for job in jobs}, {"assessment", "transcribe", "translate", "analyze"})

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
            "ASANTE_AI_BACKEND": "",
            "ASANTE_OLLAMA_BASE_URL": "http://ollama:11434",
            "ASANTE_OLLAMA_MODEL": "llama3.2:latest",
            "ASANTE_AI_PROVIDER": "gemini",
            "ASANTE_AI_API_KEY": "test-cloud-key",
        }, clear=False), patch("asante_api.ai.provider.httpx.post", side_effect=RuntimeError("offline")) as post:
            result = ask_model("Return JSON", {"question": "test"})
        self.assertIsNone(result)
        self.assertEqual(post.call_count, 1)
        self.assertIn("ollama:11434/api/chat", post.call_args.args[0])

    def test_live_modal_backend_uses_separate_adapter(self):
        from asante_api.ai.provider import ask_model_detailed

        with patch.dict("os.environ", {"ASANTE_AI_BACKEND": "modal"}, clear=False), patch(
            "asante_api.ai.live_modal.ask_model_detailed_via_modal",
            return_value={"status": "complete", "output": {"ok": True}, "provider": "modal-ollama", "model": "llama3.2:3b", "error": ""},
        ) as modal_ask, patch("asante_api.ai.provider.httpx.post") as post:
            result = ask_model_detailed("Return JSON", {"question": "test"})
        self.assertEqual(result["provider"], "modal-ollama")
        self.assertEqual(result["output"], {"ok": True})
        modal_ask.assert_called_once()
        post.assert_not_called()

    def test_translation_uses_modal_backend_and_keeps_transcript_timestamps(self):
        """Translation reads timed transcript cues, then asks the live Modal adapter (not localhost Ollama)."""
        segments = [{"start": 1.5, "end": 3.0, "text": "Hello"}, {"start": 3.0, "end": 5.5, "text": "Friends"}]
        modal_response = {
            "status": "complete",
            "provider": "modal-ollama",
            "model": "llama3.2:3b",
            "error": "",
            "output": {"segments": [{"id": 0, "text": "Sawubona"}, {"id": 1, "text": "Bangani"}]},
        }
        with patch.dict("os.environ", {"ASANTE_AI_BACKEND": "modal"}, clear=False), patch(
            "asante_api.ai.live_modal.ask_model_detailed_via_modal",
            return_value=modal_response,
        ) as modal_ask, patch("asante_api.ai.provider.httpx.post") as local_post:
            cues, result = processing_jobs.translate_caption_segments(segments, "en", "zu")
        self.assertEqual([(cue["start"], cue["end"], cue["text"]) for cue in cues], [(1.5, 3.0, "Sawubona"), (3.0, 5.5, "Bangani")])
        self.assertEqual(result["provider"], "modal-ollama")
        modal_ask.assert_called()
        local_post.assert_not_called()

    def test_live_modal_chat_adapter_parses_translation_json(self):
        from asante_api.ai.live_modal import ask_model_detailed_via_modal

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "provider": "modal-ollama",
                    "model": "llama3.2:3b",
                    "content": '{"segments":[{"id":0,"text":"Sawubona"}]}',
                }

        with patch.dict(
            "os.environ",
            {
                "ASANTE_AI_BACKEND": "modal",
                "ASANTE_MODAL_BASE_URL": "https://example.modal.run",
                "ASANTE_MODAL_SHARED_SECRET": "test-secret-at-least-16",
                "ASANTE_OLLAMA_MODEL": "llama3.2:3b",
            },
            clear=False,
        ), patch("asante_api.ai.live_modal.httpx.post", return_value=FakeResponse()) as post:
            result = ask_model_detailed_via_modal(
                "Translate",
                {"source_language": "en", "target_language": "zu", "segments": [{"id": 0, "text": "Hello"}]},
                timeout=5,
            )
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["provider"], "modal-ollama")
        self.assertEqual(result["output"]["segments"][0]["text"], "Sawubona")
        self.assertIn("/v1/asante/chat", post.call_args.args[0])
        self.assertTrue(post.call_args.kwargs.get("follow_redirects"))

    def test_transcription_uses_modal_whisper_when_backend_is_modal(self):
        with tempfile.TemporaryDirectory(prefix="asante-modal-whisper-test-") as directory:
            wav = Path(directory) / "speech.wav"
            wav.write_bytes(b"RIFF....WAVEfmt ")
            modal_draft = {
                "text": "Hello friends",
                "language": "en",
                "segments": [{"start": 0.0, "end": 2.0, "text": "Hello friends"}],
                "model": "tiny",
                "backend": "modal-faster-whisper",
            }
            with patch.dict("os.environ", {"ASANTE_AI_BACKEND": "modal"}, clear=False), patch(
                "asante_api.ai.live_modal.transcribe_wav_via_modal",
                return_value=modal_draft,
            ) as modal_whisper:
                result = processing_jobs._optional_whisper_transcribe(wav)
        self.assertEqual(result["backend"], "modal-faster-whisper")
        self.assertEqual(result["segments"][0]["text"], "Hello friends")
        modal_whisper.assert_called_once()

    def test_live_modal_transcribe_follows_modal_303_redirects(self):
        from asante_api.ai.live_modal import transcribe_wav_via_modal

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "text": "Hello friends",
                    "language": "en",
                    "segments": [{"start": 0.0, "end": 1.5, "text": "Hello friends"}],
                    "model": "tiny",
                    "backend": "modal-faster-whisper",
                }

        with tempfile.TemporaryDirectory(prefix="asante-modal-redirect-") as directory:
            wav = Path(directory) / "speech.wav"
            wav.write_bytes(b"RIFF....WAVEfmt ")
            with patch.dict(
                "os.environ",
                {
                    "ASANTE_AI_BACKEND": "modal",
                    "ASANTE_MODAL_BASE_URL": "https://example.modal.run",
                    "ASANTE_MODAL_SHARED_SECRET": "test-secret-at-least-16",
                    "ASANTE_MODAL_WHISPER_MODEL": "tiny",
                },
                clear=False,
            ), patch("asante_api.ai.live_modal.httpx.post", return_value=FakeResponse()) as post:
                result = transcribe_wav_via_modal(wav)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["text"], "Hello friends")
        self.assertTrue(post.call_args.kwargs.get("follow_redirects"))
        self.assertIn("/v1/asante/transcribe", post.call_args.args[0])

    def test_live_caption_limits_default_smaller_than_localhost(self):
        from asante_api.ai.caption_limits import caption_limits_snapshot, caption_seconds, translate_max_cues

        with patch.dict("os.environ", {"ASANTE_AI_BACKEND": "", "ASANTE_LIVE_CAPTION_SECONDS": "", "ASANTE_CAPTION_SECONDS": "", "ASANTE_LIVE_TRANSLATE_MAX_CUES": "", "ASANTE_TRANSLATE_MAX_CUES": ""}, clear=False):
            self.assertEqual(caption_seconds(), 180)
            self.assertEqual(translate_max_cues(), 100)
        with patch.dict("os.environ", {"ASANTE_AI_BACKEND": "modal", "ASANTE_LIVE_CAPTION_SECONDS": "", "ASANTE_CAPTION_SECONDS": "", "ASANTE_LIVE_TRANSLATE_MAX_CUES": "", "ASANTE_TRANSLATE_MAX_CUES": ""}, clear=False):
            snapshot = caption_limits_snapshot()
        self.assertTrue(snapshot["liveModal"])
        self.assertEqual(snapshot["captionSeconds"], 45)
        self.assertEqual(snapshot["translateMaxCues"], 12)

    def test_live_like_transcribe_then_translate_respects_cost_caps(self):
        """Simulate live Modal flow: ASR cues → translation, without calling Modal or using long media."""
        long_transcript = [
            {"start": float(index), "end": float(index) + 0.8, "text": f"Cue {index}"}
            for index in range(0, 120, 5)
        ]
        # Includes speech past the live 45s window and more cues than the live max.
        self.assertGreater(len(long_transcript), 12)
        self.assertGreater(long_transcript[-1]["start"], 45)

        def fake_modal_translate(instruction, payload, timeout=30):
            segments = payload.get("segments") or []
            if "segments" in (payload or {}) and isinstance(segments, list) and segments and "id" in segments[0]:
                return {
                    "status": "complete",
                    "provider": "modal-ollama",
                    "model": "llama3.2:3b",
                    "error": "",
                    "output": {"segments": [{"id": item["id"], "text": f"ZU:{item['text']}"} for item in segments]},
                }
            return {
                "status": "complete",
                "provider": "modal-ollama",
                "model": "llama3.2:3b",
                "error": "",
                "output": {"text": f"ZU:{payload.get('text')}"},
            }

        with patch.dict(
            "os.environ",
            {
                "ASANTE_AI_BACKEND": "modal",
                "ASANTE_LIVE_CAPTION_SECONDS": "45",
                "ASANTE_LIVE_TRANSLATE_MAX_CUES": "12",
                "ASANTE_LIVE_TRANSLATE_BATCH_SIZE": "3",
            },
            clear=False,
        ), patch("asante_api.ai.live_modal.ask_model_detailed_via_modal", side_effect=fake_modal_translate) as modal_ask:
            cues, result = processing_jobs.translate_caption_segments(long_transcript, "en", "zu")
        self.assertEqual(result["provider"], "modal-ollama")
        self.assertLessEqual(len(cues), 12)
        self.assertTrue(all(cue["end"] <= 45 for cue in cues))
        self.assertTrue(all(cue["text"].startswith("ZU:") for cue in cues))
        self.assertGreaterEqual(modal_ask.call_count, 1)
        self.assertLessEqual(modal_ask.call_count, 12)  # capped cues, batched

    def test_live_transcribe_job_passes_capped_excerpt_length_to_ffmpeg(self):
        async def no_download(_key, destination):
            destination.write_bytes(b"fake-media")
            return destination

        recorded: list[list[str]] = []

        def fake_run_command(command, timeout):
            recorded.append(list(command))
            Path(command[-1]).write_bytes(b"RIFF")
            return ""

        session = AsyncMock()
        job = SimpleNamespace(
            input_payload={"object_key": "private/original.mp4", "media_derivatives": {}},
            progress=0,
            status="running",
            lease_owner="test-worker",
            lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            result_payload={},
        )
        packet = SimpleNamespace(packet={"summary": "story"})
        modal_draft = {
            "status": "draft",
            "text": "Short live draft",
            "language": "en",
            "segments": [{"start": 0.0, "end": 2.0, "text": "Short live draft"}],
            "backend": "modal-faster-whisper",
            "coveredSeconds": 45,
        }
        def fake_extract(_source, destination):
            Path(destination).write_bytes(b"RIFF")

        with patch.dict("os.environ", {"ASANTE_AI_BACKEND": "modal", "ASANTE_LIVE_CAPTION_SECONDS": "45"}, clear=False), patch.object(
            processing_jobs, "_download_upload", side_effect=no_download
        ), patch.object(processing_jobs, "extract_audio_track", side_effect=fake_extract), patch.object(
            processing_jobs, "run_command", side_effect=fake_run_command
        ), patch.object(processing_jobs, "_optional_whisper_transcribe", return_value=modal_draft):
            result = asyncio.run(processing_jobs._run_transcribe(session, job, packet))
        self.assertEqual(result["transcriptDraft"]["status"], "draft")
        self.assertEqual(result["transcriptDraft"]["coveredSeconds"], 45)
        ffmpeg = next(cmd for cmd in recorded if cmd and cmd[0] == "ffmpeg")
        self.assertIn("-t", ffmpeg)
        self.assertEqual(ffmpeg[ffmpeg.index("-t") + 1], "45")

    def test_media_helper_is_unavailable_when_no_provider_is_configured(self):
        with tempfile.TemporaryDirectory(prefix="asante-provider-test-") as directory:
            image = Path(directory) / "frame.jpg"
            image.write_bytes(b"small image test input")
            with patch.dict("os.environ", {"ASANTE_AI_BACKEND": "", "ASANTE_OLLAMA_BASE_URL": "", "ASANTE_AI_PROVIDER": "fake", "ASANTE_AI_API_KEY": ""}, clear=False):
                result = ask_model_media("Analyze frames", {"frameCount": 1}, [image])
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
