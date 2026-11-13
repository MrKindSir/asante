FROM python:3.12-slim
WORKDIR /workspace
COPY infrastructure/codex/requirements.txt /workspace/requirements.txt
RUN pip install --no-cache-dir -r /workspace/requirements.txt
COPY scripts /workspace/scripts
COPY tests /workspace/tests
ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "scripts.codex.project_mcp"]
