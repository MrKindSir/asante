"""Server-side MinIO access for database-selected published media."""

from __future__ import annotations

import os
import re
from collections.abc import Iterator

from fastapi import HTTPException
from minio import Minio
from minio.error import S3Error
from starlette.background import BackgroundTask
from starlette.responses import Response, StreamingResponse
from urllib3 import PoolManager, Timeout
from urllib3.exceptions import HTTPError


def storage_client() -> Minio:
    return Minio(
        os.environ.get("ASANTE_MINIO_ENDPOINT", "minio:9000"),
        access_key=os.environ["ASANTE_MINIO_ACCESS_KEY"],
        secret_key=os.environ["ASANTE_MINIO_SECRET_KEY"],
        secure=os.environ.get("ASANTE_MINIO_SECURE", "false").lower() == "true",
        region="us-east-1",
        http_client=PoolManager(timeout=Timeout(connect=3, read=15), retries=False),
    )


def media_bucket() -> str:
    return os.environ.get("ASANTE_MINIO_BUCKET", "asante-media")


def byte_range(value: str | None, size: int) -> tuple[int, int] | None:
    """Resolve one bounded, open-ended or suffix range without buffering media."""
    if value is None:
        return None
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", value.strip())
    if match and size > 0:
        first, last = match.groups()
        if first:
            start = int(first)
            end = min(int(last), size - 1) if last else size - 1
        elif last and int(last) > 0:
            start, end = max(0, size - int(last)), size - 1
        else:
            start, end = size, -1
        if 0 <= start <= end < size:
            return start, end
    raise HTTPException(416, "Requested media range is unavailable", headers={"Content-Range": f"bytes */{size}"})


def media_bytes(object_key: str) -> bytes:
    """Read a small object (playlist/poster metadata) into memory for rewrite."""
    try:
        client = storage_client()
        bucket = media_bucket()
        response = client.get_object(bucket, object_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()
    except (S3Error, HTTPError, KeyError, ValueError) as error:
        raise HTTPException(503, "Story media is temporarily unavailable") from error


def media_response(object_key: str, range_header: str | None, head: bool = False) -> Response:
    """Called in a thread: only a key resolved by the catalogue may reach here."""
    try:
        client = storage_client()
        bucket = media_bucket()
        info = client.stat_object(bucket, object_key)
        selected = byte_range(range_header if not head else None, info.size)
        headers = {
            "Accept-Ranges": "bytes",
            "Cache-Control": "no-store",
            "Content-Length": str(info.size),
        }
        status_code = 200
        offset, length = 0, info.size
        if selected is not None:
            offset, end = selected
            length = end - offset + 1
            headers["Content-Range"] = f"bytes {offset}-{end}/{info.size}"
            headers["Content-Length"] = str(length)
            status_code = 206
        if head:
            return Response(headers=headers, media_type=info.content_type or "application/octet-stream")
        body = client.get_object(
            bucket, object_key, offset=offset, length=length,
            request_headers={"If-Match": f'"{info.etag}"'},
        )
    except (S3Error, HTTPError, KeyError, ValueError) as error:
        raise HTTPException(503, "Story media is temporarily unavailable") from error

    def close() -> None:
        body.close()
        body.release_conn()

    def chunks() -> Iterator[bytes]:
        try:
            yield from body.stream(64 * 1024)
        finally:
            close()

    return StreamingResponse(
        chunks(), status_code=status_code, headers=headers,
        media_type=info.content_type or "application/octet-stream",
        background=BackgroundTask(close),
    )
