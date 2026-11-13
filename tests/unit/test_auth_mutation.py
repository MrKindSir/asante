"""Origin checks for browser mutations behind TLS-terminating edges."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from fastapi import HTTPException

from asante_api.auth import ACCOUNT_COOKIE, CSRF_COOKIE, CSRF_HEADER, csrf_token, mutation


def _request(*, origin: str | None, host: str, proto: str | None = None, asante: str = "1", forwarded_host: str | None = None, cookies: dict[str, str] | None = None, csrf: str | None = None) -> MagicMock:
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
    request.url.path = "/asante/api/v1/workspace/projects"
    request.cookies = cookies or {}
    if csrf is not None:
        request.headers.get.side_effect = lambda key, default=None: {**headers, CSRF_HEADER: csrf}.get(key, default)
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

    def test_cookie_session_requires_session_bound_csrf_token(self):
        request = _request(origin="https://asante.terminalcursor.com", host="asante.terminalcursor.com", proto="https", cookies={ACCOUNT_COOKIE: "session-token", CSRF_COOKIE: "wrong"})
        with self.assertRaises(HTTPException) as raised:
            mutation(request)
        self.assertEqual(raised.exception.status_code, 403)

    def test_cookie_session_accepts_matching_csrf_token(self):
        token = csrf_token("session-token")
        mutation(_request(origin="https://asante.terminalcursor.com", host="asante.terminalcursor.com", proto="https", cookies={ACCOUNT_COOKIE: "session-token", CSRF_COOKIE: token}, csrf=token))

    def test_cookie_session_is_not_exempt_when_origin_is_missing(self):
        token = csrf_token("session-token")
        request = _request(origin=None, host="asante.terminalcursor.com", proto="https", cookies={ACCOUNT_COOKIE: "session-token", CSRF_COOKIE: token})
        with self.assertRaises(HTTPException) as raised:
            mutation(request)
        self.assertEqual(raised.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
