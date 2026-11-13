FROM python:3.12-slim

WORKDIR /workspace
ENV HF_HOME=/var/cache/huggingface

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg poppler-utils && rm -rf /var/lib/apt/lists/*
ENV ASANTE_WHISPER_MODEL=/workspace/models/whisper-tiny

COPY app/services/api/requirements.txt /workspace/requirements.txt
RUN pip install --no-cache-dir --timeout 120 --retries 8 -r /workspace/requirements.txt
COPY app/services/ai/models/whisper-tiny /workspace/models/whisper-tiny

COPY app/services/api/asante_api /workspace/asante_api
COPY app/db /workspace/app/db
COPY tests /workspace/tests
COPY documentation/project/assets/media /workspace/media

EXPOSE 8000

CMD ["uvicorn", "asante_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
