"""Origin checks for browser mutations behind TLS-terminating edges."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from fastapi import HTTPException

from asante_api.auth import mutation


def _request(*, origin: str | None, host: str, proto: str | None = None, asante: str = "1", forwarded_host: str | None = None) -> MagicMock:
    headers = {"host": host, "x-asante-request": asante}
    if origin is not None:
        headers["origin"] = origin
    if proto is not None:
        headers["x-forwarded-proto"] = proto
    if forwarded_host is not None:
        headers["x-forwarded-host"] = forwarded_host
    request = MagicMock()
    request.headers.get.side_effect = lambda key, default=None: headers.get(key, default)
    request.url.scheme = "http"
    return request


class MutationOriginTests(unittest.TestCase):
    def test_https_origin_accepted_when_proxy_still_sees_http(self):
        mutation(_request(origin="https://asante.terminalcursor.com", host="asante.terminalcursor.com", proto="http"))

    def test_matching_https_forwarded_proto_is_accepted(self):
        mutation(_request(origin="https://asante.terminalcursor.com", host="asante.terminalcursor.com", proto="https"))

    def test_wrong_origin_is_rejected(self):
        with self.assertRaises(HTTPException) as raised:
            mutation(_request(origin="https://evil.example", host="asante.terminalcursor.com", proto="https"))
        self.assertEqual(raised.exception.status_code, 403)

    def test_missing_asante_header_is_rejected(self):
        with self.assertRaises(HTTPException) as raised:
            mutation(_request(origin="https://asante.terminalcursor.com", host="asante.terminalcursor.com", proto="https", asante="0"))
        self.assertEqual(raised.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
