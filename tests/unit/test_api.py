import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "app/services/api"))

try:
    from fastapi import HTTPException
    from asante_api.storage import byte_range
    from asante_api.auth import HASHER, verify_password, Credentials, Registration
    from pydantic import ValidationError
    from asante_api.catalogue import decode_catalogue_cursor, encode_catalogue_cursor, parse_bbox, published_hls_object_key
    from asante_api.main import (
        SUPPORTED_FORMATS,
        SUPPORTED_LANGUAGES,
        distance_m,
    )
    from asante_api.uploads import MAX_AUDIO_BYTES, MAX_VIDEO_BYTES, UploadInput
    from asante_api.ai.workers import fixture_plan
except ModuleNotFoundError as error:  # pragma: no cover - environment-dependent skip
    raise unittest.SkipTest(f"Asante API dependencies are not installed: {error}")


class ApiDomainTests(unittest.TestCase):
    def test_password_hashes_are_salted_and_cannot_authenticate_wrong_passwords(self):
        password = "Asante unit-test password"
        first, second = HASHER.hash(password), HASHER.hash(password)
        self.assertNotEqual(first, second)
        self.assertNotIn(password, first)
        self.assertTrue(verify_password(first, password))
        self.assertFalse(verify_password(first, "wrong password"))

    def test_registration_normalizes_email_and_rejects_privilege_fields(self):
        self.assertEqual(Credentials(email=" Nomsa@EXAMPLE.test ", password="A long unit test password").email, "nomsa@example.test")
        for extra in ({"role": "reviewer"}, {"contributor_id": "someone-else"}):
            with self.assertRaises(ValidationError):
                Registration(email="test@example.test", password="A long unit test password", name="Test", consent=True, **extra)

    def test_media_ranges_support_seek_suffix_and_open_ended_requests(self):
        self.assertIsNone(byte_range(None, 100))
        for value, expected in [("bytes=0-9", (0, 9)), ("bytes=90-", (90, 99)), ("bytes=-10", (90, 99)), ("bytes=90-999", (90, 99))]:
            self.assertEqual(byte_range(value, 100), expected)
        for value in ("bytes=100-", "bytes=9-1", "bytes=-0", "bytes=0-1,5-6", "bad"):
            with self.subTest(value=value), self.assertRaises(HTTPException) as raised:
                byte_range(value, 100)
            self.assertEqual(raised.exception.status_code, 416)
            self.assertEqual(raised.exception.headers["Content-Range"], "bytes */100")

    def test_distance_is_zero_for_same_coordinate(self):
        self.assertAlmostEqual(distance_m(-26.1883, 28.0368, -26.1883, 28.0368), 0)

    def test_story_plan_contains_worker_steps_and_human_gate(self):
        plan = fixture_plan(
            {
                "topic": "A river memory",
                "place_name": "Soweto",
                "language": "zu",
                "media_format": "audio",
                "audience": "local listeners",
            }
        )

        self.assertEqual(plan["language"], "zu")
        self.assertEqual(plan["media_format"], "audio")
        self.assertGreaterEqual(len(plan["worker_steps"]), 3)
        self.assertIn("human", plan["human_gate"].lower())

    def test_supported_input_contract_is_explicit(self):
        self.assertEqual(SUPPORTED_FORMATS, {"audio", "video"})
        self.assertEqual(SUPPORTED_LANGUAGES, {"en", "zu", "st"})

    def test_upload_limits_allow_larger_video_but_keep_audio_bounded(self):
        self.assertEqual(MAX_AUDIO_BYTES, 100 * 1024 * 1024)
        self.assertEqual(MAX_VIDEO_BYTES, 500 * 1024 * 1024)
        self.assertEqual(
            UploadInput(project_id="p", name="clip.mp4", size=MAX_VIDEO_BYTES, content_type="video/mp4", consent_given=True).size,
            MAX_VIDEO_BYTES,
        )
        with self.assertRaises(ValidationError):
            UploadInput(project_id="p", name="recording.mp3", size=MAX_AUDIO_BYTES + 1, content_type="audio/mpeg", consent_given=True)
        with self.assertRaises(ValidationError):
            UploadInput(project_id="p", name="clip.mp4", size=MAX_VIDEO_BYTES + 1, content_type="video/mp4", consent_given=True)

    def test_catalogue_cursor_round_trips_and_rejects_invalid_values(self):
        cursor = encode_catalogue_cursor("story-002")
        self.assertEqual(decode_catalogue_cursor(cursor).last_slug, "story-002")
        distance_cursor = decode_catalogue_cursor(encode_catalogue_cursor("story-003", 42.5))
        self.assertEqual(distance_cursor.distance_m, 42.5)
        self.assertIsNone(decode_catalogue_cursor(None))
        with self.assertRaises(ValueError):
            decode_catalogue_cursor("not-a-valid-cursor!")

    def test_bbox_supports_antimeridian_and_rejects_invalid_ranges(self):
        self.assertEqual(parse_bbox("170,-10,-170,10"), (170.0, -10.0, -170.0, 10.0))
        self.assertEqual(parse_bbox(None), None)
        for value in ("1,2,3", "-181,-10,10,10", "10,20,20,10", "nan,0,1,1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_bbox(value)

    def test_published_hls_object_key_allows_nested_1080p_and_rejects_traversal(self):
        master = "derivatives/upload123/hls/playlist.m3u8"
        self.assertEqual(
            published_hls_object_key(master, "1080p/playlist.m3u8"),
            "derivatives/upload123/hls/1080p/playlist.m3u8",
        )
        self.assertEqual(
            published_hls_object_key(master, "1080p/segment_001.ts"),
            "derivatives/upload123/hls/1080p/segment_001.ts",
        )
        self.assertEqual(
            published_hls_object_key("published/story-002/hls/index.m3u8", "seg_000.ts"),
            "published/story-002/hls/seg_000.ts",
        )
        self.assertIsNone(published_hls_object_key(master, "../playlist.m3u8"))
        self.assertIsNone(published_hls_object_key(master, "720p/playlist.m3u8"))
        self.assertIsNone(published_hls_object_key(master, "1080p/nested/playlist.m3u8"))


if __name__ == "__main__":
    unittest.main()
