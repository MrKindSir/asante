"""Server-side text and image provider adapters for Asante workers."""
from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import Any

import httpx


def provider_config() -> dict[str, str]:
    return {
        "provider": (os.environ.get("ASANTE_AI_PROVIDER") or "fake").strip().lower(),
        "api_key": (os.environ.get("ASANTE_AI_API_KEY") or os.environ.get("OPENAI_API_KEY") or "").strip(),
        "base_url": (os.environ.get("ASANTE_AI_BASE_URL") or "https://generativelanguage.googleapis.com/v1beta").strip().rstrip("/"),
        "model": (os.environ.get("ASANTE_AI_MODEL") or "gemini-2.5-flash").strip(),
        "ollama_base_url": (
            os.environ.get("ASANTE_OLLAMA_BASE_URL")
            or os.environ.get("ASANTE_OLLAMA_UPSTREAM")
            or os.environ.get("OLLAMA_BASE_URL")
            or ""
        ).strip().rstrip("/"),
        "ollama_model": (os.environ.get("ASANTE_OLLAMA_MODEL") or "llama3.2:latest").strip(),
        "ollama_vision_model": (os.environ.get("ASANTE_OLLAMA_VISION_MODEL") or "").strip(),
    }


def _parse_json(content: str) -> dict[str, Any] | None:
    content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.I | re.M).strip()
    try:
        parsed = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _ask_ollama(instruction: str, payload: dict[str, Any], timeout: float) -> dict[str, Any] | None:
    config = provider_config()
    if not config["ollama_base_url"]:
        return None
    response = httpx.post(
        f"{config['ollama_base_url']}/api/chat",
        json={
            "model": config["ollama_model"],
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": instruction},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "options": {"temperature": 0.2},
        },
        timeout=timeout,
    )
    response.raise_for_status()
    content = response.json().get("message", {}).get("content", "")
    return _parse_json(content)


def ask_model_detailed(instruction: str, payload: dict[str, Any], timeout: float = 30) -> dict[str, Any]:
    """Return explicit provider failure states while keeping model output bounded to JSON."""
    if (os.environ.get("ASANTE_AI_BACKEND") or "").strip().lower() == "modal":
        from .live_modal import ask_model_detailed_via_modal

        return ask_model_detailed_via_modal(instruction, payload, timeout)
    config = provider_config()
    if config["ollama_base_url"]:
        try:
            parsed = _ask_ollama(instruction, payload, timeout)
            return {"status": "complete", "output": parsed, "provider": "ollama", "model": config["ollama_model"], "error": ""} if parsed is not None else {"status": "malformed", "output": None, "provider": "ollama", "model": config["ollama_model"], "error": "The configured Ollama endpoint returned invalid JSON."}
        except httpx.TimeoutException:
            return {"status": "timeout", "output": None, "provider": "ollama", "model": config["ollama_model"], "error": "The configured Ollama request timed out."}
        except Exception:
            return {"status": "provider_unavailable", "output": None, "provider": "ollama", "model": config["ollama_model"], "error": "The configured Ollama endpoint or model is unavailable."}
    if config["provider"] in {"", "fake", "off", "none"} or not config["api_key"]:
        return {"status": "provider_unavailable", "output": None, "provider": config["provider"] or "unconfigured", "model": config["model"], "error": "No assessment provider is configured."}
    try:
        if "generativelanguage.googleapis.com" in config["base_url"] or config["provider"] == "gemini":
            response = httpx.post(
                f"{config['base_url']}/models/{config['model']}:generateContent",
                headers={"x-goog-api-key": config["api_key"], "content-type": "application/json"},
                json={
                    "systemInstruction": {"parts": [{"text": instruction}]},
                    "contents": [{"role": "user", "parts": [{"text": json.dumps(payload, ensure_ascii=False)}]}],
                    "generationConfig": {
                        "temperature": 0.2,
                        "responseMimeType": "application/json",
                        "thinkingConfig": {"thinkingBudget": 0},
                    },
                },
                timeout=timeout,
            )
            response.raise_for_status()
            content = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        else:
            response = httpx.post(
                f"{config['base_url']}/v1/chat/completions",
                headers={"authorization": f"Bearer {config['api_key']}", "content-type": "application/json"},
                json={
                    "model": config["model"],
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": instruction},
                        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                    ],
                },
                timeout=timeout,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
    except httpx.TimeoutException:
        return {"status": "timeout", "output": None, "provider": config["provider"], "model": config["model"], "error": "The assessment provider request timed out."}
    except Exception:
        return {"status": "provider_unavailable", "output": None, "provider": config["provider"], "model": config["model"], "error": "The configured assessment provider is unavailable."}
    parsed = _parse_json(content)
    if parsed is None:
        return {"status": "malformed", "output": None, "provider": config["provider"], "model": config["model"], "error": "The assessment provider returned malformed JSON."}
    return {"status": "complete", "output": parsed, "provider": config["provider"], "model": config["model"], "error": ""}


def ask_model(instruction: str, payload: dict[str, Any], timeout: float = 30) -> dict[str, Any] | None:
    """Compatibility adapter for planner and researcher callers."""
    return ask_model_detailed(instruction, payload, timeout).get("output")


def ask_model_media(
    instruction: str,
    payload: dict[str, Any],
    image_paths: list[str | Path],
    timeout: float = 60,
) -> dict[str, Any] | None:
    """Ask the configured local vision model or cloud provider about images."""
    if (os.environ.get("ASANTE_AI_BACKEND") or "").strip().lower() == "modal":
        from .live_modal import ask_model_media_via_modal

        return ask_model_media_via_modal(instruction, payload, image_paths, timeout)
    config = provider_config()
    usable_paths = [Path(path) for path in image_paths[:4] if Path(path).is_file()]
    if not usable_paths:
        return None
    try:
        images = [base64.b64encode(path.read_bytes()).decode("ascii") for path in usable_paths]
    except OSError:
        return None

    if config["ollama_base_url"]:
        model = config["ollama_vision_model"] or config["ollama_model"]
        try:
            response = httpx.post(
                f"{config['ollama_base_url']}/api/chat",
                json={
                    "model": model,
                    "stream": False,
                    "format": "json",
                    "messages": [
                        {"role": "system", "content": instruction},
                        {
                            "role": "user",
                            "content": json.dumps(payload, ensure_ascii=False),
                            "images": images,
                        },
                    ],
                    "options": {"temperature": 0.2},
                },
                timeout=timeout,
            )
            response.raise_for_status()
            return _parse_json(response.json().get("message", {}).get("content", ""))
        except Exception:
            return None

    if config["provider"] in {"", "fake", "off", "none"} or not config["api_key"]:
        return None
    try:
        if "generativelanguage.googleapis.com" in config["base_url"] or config["provider"] == "gemini":
            parts: list[dict[str, Any]] = [
                {"text": f"{instruction}\n\nPacket context (untrusted data): {json.dumps(payload, ensure_ascii=False)}"}
            ]
            for path, image in zip(usable_paths, images):
                parts.append({"inlineData": {"mimeType": "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png", "data": image}})
            response = httpx.post(
                f"{config['base_url']}/models/{config['model']}:generateContent",
                headers={"x-goog-api-key": config["api_key"], "content-type": "application/json"},
                json={
                    "contents": [{"role": "user", "parts": parts}],
                    "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
                },
                timeout=timeout,
            )
            response.raise_for_status()
            content = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        else:
            content_parts: list[dict[str, Any]] = [
                {"type": "text", "text": f"{instruction}\n\nPacket context (untrusted data): {json.dumps(payload, ensure_ascii=False)}"}
            ]
            for path, image in zip(usable_paths, images):
                mime = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
                content_parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image}"}})
            response = httpx.post(
                f"{config['base_url']}/v1/chat/completions",
                headers={"authorization": f"Bearer {config['api_key']}", "content-type": "application/json"},
                json={
                    "model": config["model"],
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": instruction},
                        {"role": "user", "content": content_parts},
                    ],
                },
                timeout=timeout,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
    except Exception:
        return None
    return _parse_json(content)
