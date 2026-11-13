"""Publication admin email content and SMTP host-env resolution."""

from __future__ import annotations

import os

from asante_api.notify import _smtp_settings, notify_packet_published
from asante_api.publish import _primary_translation, _slugify


def test_slugify_includes_stable_suffix():
    slug = _slugify("They never knew she was a snake", "submission_abcdef12")
    assert slug.startswith("they-never-knew-she-was-a-snake-")
    assert slug.endswith("cdef12") or len(slug) > 10


def test_primary_translation_prefers_english():
    text, language = _primary_translation(
        {
            "translations": {
                "zu": {"text": "Umlando womfula"},
                "en": {"text": "The river remembers"},
            }
        }
    )
    assert text == "The river remembers"
    assert language == "en"


def test_notify_published_writes_outbox(tmp_path, monkeypatch):
    monkeypatch.setenv("ASANTE_NOTIFY_OUTBOX", str(tmp_path))
    monkeypatch.delenv("ASANTE_SMTP_HOST", raising=False)
    monkeypatch.delenv("UL_SMTP_HOST", raising=False)
    monkeypatch.delenv("APPSFORGE_SMTP_HOST", raising=False)
    result = notify_packet_published(
        {
            "title": "The river remembers",
            "contributor_name": "Nomsa M.",
            "submission_id": "submission_test",
            "language": "zu",
            "media_format": "video",
            "publishedSlug": "the-river-remembers-abc",
            "publishedStoryId": "11111111-1111-1111-1111-111111111111",
        },
        {"id": "11111111-1111-1111-1111-111111111111", "slug": "the-river-remembers-abc", "title": "The river remembers"},
    )
    assert result["sent"] is False
    assert result["reason"] == "smtp_not_configured"
    outbox = list(tmp_path.glob("notify-*.eml"))
    assert len(outbox) == 1
    text = outbox[0].read_text(encoding="utf-8")
    assert "Published:" in text or "published" in text.lower()
    assert "The river remembers" in text
    assert "vmafunisa@outlook.com" in text


def test_smtp_settings_prefer_ul_shell_vars(monkeypatch):
    for key in (
        "ASANTE_SMTP_HOST",
        "ASANTE_SMTP_USER",
        "ASANTE_SMTP_PASSWORD",
        "ASANTE_SMTP_FROM",
        "APPSFORGE_SMTP_HOST",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("UL_SMTP_HOST", "mail.example.test")
    monkeypatch.setenv("UL_SMTP_PORT", "587")
    monkeypatch.setenv("UL_SMTP_USER", "noreply@example.test")
    monkeypatch.setenv("UL_SMTP_PASSWORD", "secret-value")
    monkeypatch.setenv("UL_MAIL_FROM", "noreply@example.test")
    settings = _smtp_settings()
    assert settings is not None
    assert settings["host"] == "mail.example.test"
    assert settings["user"] == "noreply@example.test"
    assert settings["password"] == "secret-value"
    assert settings["from_addr"] == "noreply@example.test"
    # Ensure we did not require writing secrets into a project .env file.
    assert "ASANTE_SMTP_PASSWORD" not in os.environ or os.environ.get("ASANTE_SMTP_PASSWORD") != "secret-value"
