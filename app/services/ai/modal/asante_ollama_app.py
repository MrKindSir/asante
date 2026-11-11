"""Asante live AI on Modal: Ollama + Whisper, reached only by the Asante API.

Localhost keeps host Ollama / local Whisper. This app is for production/live only.
Deploy:  python -m modal deploy app/services/ai/modal/asante_ollama_app.py
Requires Modal token env (MODAL_TOKEN_ID / MODAL_TOKEN_SECRET) or `modal token set`.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any

import modal

APP_NAME = "asante-ollama"
MODEL_DIR = "/models"
OLLAMA_HOST = "127.0.0.1:11434"
DEFAULT_TEXT_MODEL = os.environ.get("ASANTE_OLLAMA_MODEL", "llama3.2:3b")
DEFAULT_VISION_MODEL = os.environ.get("ASANTE_OLLAMA_VISION_MODEL", "") or DEFAULT_TEXT_MODEL
WHISPER_MODEL = (os.environ.get("ASANTE_MODAL_WHISPER_MODEL") or "tiny").strip() or "tiny"

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("curl", "ca-certificates", "ffmpeg", "zstd")
    .run_commands(
        "curl -fsSL https://ollama.com/install.sh | sh",
        f"mkdir -p {MODEL_DIR}",
    )
    .pip_install(
        "fastapi==0.115.6",
        "uvicorn[standard]==0.34.0",
        "httpx==0.28.1",
        "faster-whisper==1.2.1",
        "av==18.1.0",
    )
    .env(
        {
            "OLLAMA_HOST": OLLAMA_HOST,
            "OLLAMA_MODELS": MODEL_DIR,
            "OLLAMA_KEEP_ALIVE": "5m",
            "HF_HOME": f"{MODEL_DIR}/huggingface",
            "HF_HUB_CACHE": f"{MODEL_DIR}/huggingface/hub",
        }
    )
)

model_volume = modal.Volume.from_name("asante-ollama-models", create_if_missing=True)
auth_secret = modal.Secret.from_name("asante-modal-auth")

app = modal.App(APP_NAME, image=image)


def _wait_for_ollama(timeout: float = 180) -> None:
    import httpx

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            response = httpx.get(f"http://{OLLAMA_HOST}/api/tags", timeout=2)
            if response.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError("Ollama did not become ready on Modal.")


def _ensure_model(name: str) -> None:
    show = subprocess.run(["ollama", "show", name], capture_output=True)
    if show.returncode == 0:
        return
    subprocess.run(["ollama", "pull", name], check=True)
    model_volume.commit()


def _authorized(authorization: str | None) -> bool:
    expected = (os.environ.get("ASANTE_MODAL_SHARED_SECRET") or "").strip()
    if not expected:
        return False
    if not authorization:
        return False
    value = authorization.strip()
    if value.lower().startswith("bearer "):
        value = value[7:].strip()
    return value == expected and len(value) >= 16


@app.cls(
    gpu="T4",
    timeout=60 * 10,
    scaledown_window=60,
    volumes={MODEL_DIR: model_volume},
    secrets=[auth_secret],
)
class AsanteOllama:
    """Runs Ollama (and Whisper) for live Asante workers."""

    @modal.enter()
    def start(self) -> None:
        self._whisper_model = None
        self._whisper_model_name = ""
        Path(MODEL_DIR).mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["ollama", "serve"])
        _wait_for_ollama()
        _ensure_model(DEFAULT_TEXT_MODEL)
        if DEFAULT_VISION_MODEL and DEFAULT_VISION_MODEL != DEFAULT_TEXT_MODEL:
            try:
                _ensure_model(DEFAULT_VISION_MODEL)
            except Exception:
                pass

    def _get_whisper_model(self, model_name: str):
        from faster_whisper import WhisperModel

        if self._whisper_model is None or self._whisper_model_name != model_name:
            self._whisper_model = WhisperModel(model_name, device="cpu", compute_type="int8")
            self._whisper_model_name = model_name
            try:
                model_volume.commit()
            except Exception:
                pass
        return self._whisper_model

    @modal.asgi_app()
    def api(self):
        from fastapi import FastAPI, Header, HTTPException
        from fastapi.responses import JSONResponse
        import httpx

        web = FastAPI(title="Asante Modal Ollama", docs_url=None, redoc_url=None)

        def require_auth(authorization: str | None) -> None:
            if not _authorized(authorization):
                raise HTTPException(status_code=401, detail="Unauthorized")

        @web.get("/health")
        def health(authorization: str | None = Header(default=None)) -> dict[str, Any]:
            require_auth(authorization)
            tags = httpx.get(f"http://{OLLAMA_HOST}/api/tags", timeout=10).json()
            return {
                "status": "ok",
                "owner": "asante",
                "textModel": DEFAULT_TEXT_MODEL,
                "visionModel": DEFAULT_VISION_MODEL,
                "models": [item.get("name") for item in tags.get("models", [])],
            }

        @web.post("/v1/asante/chat")
        def chat(body: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
            require_auth(authorization)
            instruction = str(body.get("instruction") or "")
            payload = body.get("payload") if isinstance(body.get("payload"), dict) else {}
            model = str(body.get("model") or DEFAULT_TEXT_MODEL)
            try:
                requested_timeout = float(body.get("timeout") or 45)
            except (TypeError, ValueError):
                requested_timeout = 45.0
            timeout = max(requested_timeout, 120.0)
            try:
                response = httpx.post(
                    f"http://{OLLAMA_HOST}/api/chat",
                    json={
                        "model": model,
                        "stream": False,
                        "format": "json",
                        "messages": [
                            {"role": "system", "content": instruction},
                            {"role": "user", "content": __import__("json").dumps(payload, ensure_ascii=False)},
                        ],
                        "options": {"temperature": 0.2},
                    },
                    timeout=timeout,
                )
                response.raise_for_status()
            except httpx.TimeoutException:
                raise HTTPException(status_code=504, detail=f"Ollama chat timed out after {timeout:.0f}s") from None
            except httpx.HTTPError as error:
                raise HTTPException(status_code=502, detail=f"Ollama chat failed: {type(error).__name__}") from None
            content = response.json().get("message", {}).get("content", "")
            return JSONResponse(
                {
                    "provider": "modal-ollama",
                    "model": model,
                    "content": content,
                }
            )

        @web.post("/v1/asante/vision")
        def vision(body: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
            require_auth(authorization)
            instruction = str(body.get("instruction") or "")
            payload = body.get("payload") if isinstance(body.get("payload"), dict) else {}
            images = body.get("images") if isinstance(body.get("images"), list) else []
            images = [str(item) for item in images[:4] if isinstance(item, str) and item]
            if not images:
                raise HTTPException(status_code=400, detail="images required")
            model = str(body.get("model") or DEFAULT_VISION_MODEL)
            timeout = float(body.get("timeout") or 60)
            response = httpx.post(
                f"http://{OLLAMA_HOST}/api/chat",
                json={
                    "model": model,
                    "stream": False,
                    "format": "json",
                    "messages": [
                        {"role": "system", "content": instruction},
                        {
                            "role": "user",
                            "content": __import__("json").dumps(payload, ensure_ascii=False),
                            "images": images,
                        },
                    ],
                    "options": {"temperature": 0.2},
                },
                timeout=timeout,
            )
            response.raise_for_status()
            content = response.json().get("message", {}).get("content", "")
            return JSONResponse({"provider": "modal-ollama", "model": model, "content": content})

        @web.post("/v1/asante/transcribe")
        def transcribe(body: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
            require_auth(authorization)
            import base64
            import tempfile
            from pathlib import Path as _Path

            audio_b64 = body.get("audioBase64")
            if not isinstance(audio_b64, str) or not audio_b64.strip():
                raise HTTPException(status_code=400, detail="audioBase64 required")
            model_name = str(body.get("model") or WHISPER_MODEL)
            try:
                max_seconds = float(body.get("maxSeconds") or 45)
            except (TypeError, ValueError):
                max_seconds = 45.0
            max_seconds = max(5.0, min(max_seconds, 180.0))
            try:
                max_cues = int(body.get("maxCues") or 12)
            except (TypeError, ValueError):
                max_cues = 12
            max_cues = max(1, min(max_cues, 100))
            with tempfile.TemporaryDirectory(prefix="asante-modal-whisper-") as temporary:
                wav = _Path(temporary) / "speech.wav"
                wav.write_bytes(base64.b64decode(audio_b64))
                model = self._get_whisper_model(model_name)
                segments_iter, info = model.transcribe(str(wav), beam_size=1)
                segments: list[dict[str, Any]] = []
                parts: list[str] = []
                for item in segments_iter:
                    text = (item.text or "").strip()
                    if not text:
                        continue
                    if float(item.start) >= max_seconds:
                        break
                    parts.append(text)
                    segments.append(
                        {
                            "start": float(item.start),
                            "end": min(float(item.end), max_seconds),
                            "text": text,
                        }
                    )
                    if len(segments) >= max_cues:
                        break
            return JSONResponse(
                {
                    "text": " ".join(parts).strip(),
                    "language": getattr(info, "language", "") or "",
                    "segments": segments,
                    "model": model_name,
                    "backend": "modal-faster-whisper",
                    "coveredSeconds": max_seconds,
                    "maxCues": max_cues,
                }
            )

        return web


@app.local_entrypoint()
def main() -> None:
    print("Deploy with: python -m modal deploy app/services/ai/modal/asante_ollama_app.py")
    print("Create auth secret first:")
    print('  python -m modal secret create asante-modal-auth ASANTE_MODAL_SHARED_SECRET="..."')
