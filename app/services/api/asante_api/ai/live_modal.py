"""Live-only Asante AI calls to Modal-hosted Ollama / Whisper.

Localhost must not set ASANTE_AI_BACKEND=modal. When that flag is off, nothing
in this module is used and the existing provider/Whisper paths stay as-is.
"""

from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import Any

import httpx


def modal_live_enabled() -> bool:
    return (os.environ.get("ASANTE_AI_BACKEND") or "").strip().lower() == "modal"


def _positive_timeout(name: str, default: float) -> str:
    try:
        value = float((os.environ.get(name) or "").strip() or default)
    except (TypeError, ValueError):
        value = default
    return str(value if value > 0 else default)


def live_modal_config() -> dict[str, str]:
    from .caption_limits import caption_seconds, translate_max_cues

    return {
        "base_url": (os.environ.get("ASANTE_MODAL_BASE_URL") or "").strip().rstrip("/"),
        "shared_secret": (os.environ.get("ASANTE_MODAL_SHARED_SECRET") or "").strip(),
        "text_model": (os.environ.get("ASANTE_OLLAMA_MODEL") or "llama3.2:3b").strip(),
        "vision_model": (
            os.environ.get("ASANTE_OLLAMA_VISION_MODEL")
            or os.environ.get("ASANTE_OLLAMA_MODEL")
            or "llama3.2:3b"
        ).strip(),
        "whisper_model": (os.environ.get("ASANTE_MODAL_WHISPER_MODEL") or "tiny").strip() or "tiny",
        "transcribe_timeout": _positive_timeout("ASANTE_MODAL_TRANSCRIBE_TIMEOUT", 240),
        "caption_seconds": str(caption_seconds()),
        "translate_max_cues": str(translate_max_cues()),
    }


def _parse_json(content: str) -> dict[str, Any] | None:
    content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.I | re.M).strip()
    try:
        parsed = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _headers(secret: str) -> dict[str, str]:
    return {"authorization": f"Bearer {secret}", "content-type": "application/json"}


def _modal_post(url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: float) -> httpx.Response:
    """POST to a Modal web endpoint with redirect following enabled."""
    return httpx.post(
        url,
        headers=headers,
        json=json,
        timeout=timeout,
        follow_redirects=True,
    )


def ask_model_detailed_via_modal(instruction: str, payload: dict[str, Any], timeout: float = 30) -> dict[str, Any]:
    """Separate live path: JSON chat against Modal Ollama."""
    config = live_modal_config()
    if not config["base_url"] or not config["shared_secret"]:
        return {
            "status": "provider_unavailable",
            "output": None,
            "provider": "modal-ollama",
            "model": config["text_model"],
            "error": "ASANTE_MODAL_BASE_URL or ASANTE_MODAL_SHARED_SECRET is not configured.",
        }
    try:
        ollama_timeout = max(float(timeout), 120.0)
        response = _modal_post(
            f"{config['base_url']}/v1/asante/chat",
            headers=_headers(config["shared_secret"]),
            json={
                "instruction": instruction,
                "payload": payload,
                "model": config["text_model"],
                "timeout": ollama_timeout,
            },
            timeout=max(ollama_timeout + 90, 240),
        )
        response.raise_for_status()
        body = response.json()
        parsed = _parse_json(str(body.get("content") or ""))
        model = str(body.get("model") or config["text_model"])
        if parsed is None:
            return {
                "status": "malformed",
                "output": None,
                "provider": "modal-ollama",
                "model": model,
                "error": "Modal Ollama returned invalid JSON.",
            }
        return {"status": "complete", "output": parsed, "provider": "modal-ollama", "model": model, "error": ""}
    except httpx.TimeoutException:
        return {
            "status": "timeout",
            "output": None,
            "provider": "modal-ollama",
            "model": config["text_model"],
            "error": "The Modal Ollama request timed out.",
        }
    except httpx.HTTPStatusError as error:
        status_code = error.response.status_code
        if status_code == 504:
            return {
                "status": "timeout",
                "output": None,
                "provider": "modal-ollama",
                "model": config["text_model"],
                "error": "Modal Ollama timed out while generating a response.",
            }
        if status_code in {401, 403}:
            return {
                "status": "auth_error",
                "output": None,
                "provider": "modal-ollama",
                "model": config["text_model"],
                "error": "Modal rejected the Asante shared secret for chat.",
            }
        return {
            "status": "provider_error",
            "output": None,
            "provider": "modal-ollama",
            "model": config["text_model"],
            "error": f"Modal Ollama returned HTTP {status_code}.",
        }
    except Exception:
        return {
            "status": "provider_unavailable",
            "output": None,
            "provider": "modal-ollama",
            "model": config["text_model"],
            "error": "The Modal Ollama endpoint is unavailable.",
        }


def ask_model_media_via_modal(
    instruction: str,
    payload: dict[str, Any],
    image_paths: list[str | Path],
    timeout: float = 60,
) -> dict[str, Any] | None:
    """Separate live path: vision chat against Modal Ollama."""
    config = live_modal_config()
    if not config["base_url"] or not config["shared_secret"]:
        return None
    usable_paths = [Path(path) for path in image_paths[:4] if Path(path).is_file()]
    if not usable_paths:
        return None
    try:
        images = [base64.b64encode(path.read_bytes()).decode("ascii") for path in usable_paths]
    except OSError:
        return None
    try:
        response = _modal_post(
            f"{config['base_url']}/v1/asante/vision",
            headers=_headers(config["shared_secret"]),
            json={
                "instruction": instruction,
                "payload": payload,
                "images": images,
                "model": config["vision_model"],
                "timeout": timeout,
            },
            timeout=timeout + 20,
        )
        response.raise_for_status()
        return _parse_json(str(response.json().get("content") or ""))
    except Exception:
        return None


def _modal_transcription_failure(config: dict[str, str], status: str, error: str) -> dict[str, Any]:
    return {
        "status": status,
        "text": "",
        "language": "",
        "segments": [],
        "model": config["whisper_model"],
        "backend": "modal-faster-whisper",
        "error": error,
        "coveredSeconds": int(config["caption_seconds"]),
    }


def transcribe_wav_via_modal(wav_path: Path) -> dict[str, Any]:
    """Run Whisper on Modal and preserve a safe reason when it cannot return text."""
    from .caption_limits import caption_seconds, clip_segments_to_caption_window

    config = live_modal_config()
    if not config["base_url"] or not config["shared_secret"]:
        return _modal_transcription_failure(
            config,
            "configuration_error",
            "Live Modal transcription is not configured (base URL or shared secret missing).",
        )
    try:
        audio_b64 = base64.b64encode(Path(wav_path).read_bytes()).decode("ascii")
    except OSError:
        return _modal_transcription_failure(
            config,
            "media_error",
            "The prepared speech audio could not be read before the Modal request.",
        )
    try:
        response = _modal_post(
            f"{config['base_url']}/v1/asante/transcribe",
            headers=_headers(config["shared_secret"]),
            json={
                "audioBase64": audio_b64,
                "model": config["whisper_model"],
                "maxSeconds": int(config["caption_seconds"]),
                "maxCues": int(config["translate_max_cues"]),
            },
            timeout=float(config["transcribe_timeout"]),
        )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            return _modal_transcription_failure(
                config,
                "malformed_response",
                "Modal Whisper returned an invalid response.",
            )
        segments = clip_segments_to_caption_window(body.get("segments") if isinstance(body.get("segments"), list) else [])
        text = " ".join(item["text"] for item in segments).strip() or str(body.get("text") or "").strip()
        if not text:
            return {
                **_modal_transcription_failure(config, "no_speech", "Modal Whisper found no speech in the capped opening audio."),
                "language": str(body.get("language") or ""),
            }
        return {
            "status": "complete",
            "text": " ".join(item["text"] for item in segments).strip() or str(body.get("text") or ""),
            "language": str(body.get("language") or ""),
            "segments": segments,
            "model": str(body.get("model") or config["whisper_model"]),
            "backend": str(body.get("backend") or "modal-faster-whisper"),
            "coveredSeconds": caption_seconds(),
        }
    except httpx.TimeoutException:
        return _modal_transcription_failure(
            config,
            "timeout",
            f"Live Modal transcription timed out after {float(config['transcribe_timeout']):.0f}s; Modal may still be warming or loading Whisper.",
        )
    except httpx.HTTPStatusError as error:
        status_code = error.response.status_code
        if status_code in {401, 403}:
            status = "auth_error"
            detail = "Modal rejected the Asante shared secret for transcription."
        else:
            status = "provider_error"
            body_preview = (error.response.text or "").strip().replace("\n", " ")[:180]
            detail = f"Modal transcription returned HTTP {status_code}."
            if body_preview:
                detail = f"{detail} {body_preview}"
        return _modal_transcription_failure(config, status, detail)
    except httpx.RequestError:
        return _modal_transcription_failure(
            config,
            "provider_unavailable",
            "The live Modal transcription endpoint could not be reached.",
        )
    except (TypeError, ValueError, KeyError):
        return _modal_transcription_failure(
            config,
            "malformed_response",
            "Modal Whisper returned an unusable transcription response.",
        )
    except Exception:
        return _modal_transcription_failure(
            config,
            "provider_error",
            "Live Modal transcription failed before a transcript was returned.",
        )
