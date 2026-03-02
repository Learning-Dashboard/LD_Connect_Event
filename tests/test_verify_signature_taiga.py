"""Tests for routes/verify_signature/verify_signature_taiga.py"""
import hashlib, hmac, pytest
from unittest.mock import MagicMock
from routes.verify_signature.verify_signature_taiga import verify_taiga_signature


class TestVerifyTaigaSignature:
    def _make_request(self, body: bytes, secret: bytes, tamper: bool = False):
        """Helper to create a mock request with proper Taiga signature."""
        sig = hmac.new(secret, msg=body, digestmod=hashlib.sha1).hexdigest()
        if tamper:
            sig = sig[:-4] + "XXXX"
        req = MagicMock()
        req.headers = {"X-TAIGA-WEBHOOK-SIGNATURE": sig}
        req.data = body
        return req

    def test_valid_signature_bytes_secret(self):
        secret = b"taiga-secret"
        body = b'{"type": "task"}'
        req = self._make_request(body, secret)
        assert verify_taiga_signature(req, secret) is True

    def test_valid_signature_string_secret(self):
        secret_str = "taiga-secret"
        secret_bytes = secret_str.encode("utf-8")
        body = b'{"type": "task"}'
        req = self._make_request(body, secret_bytes)
        assert verify_taiga_signature(req, secret_str) is True

    def test_invalid_signature(self):
        secret = b"taiga-secret"
        body = b'{"type": "task"}'
        req = self._make_request(body, secret, tamper=True)
        assert verify_taiga_signature(req, secret) is False

    def test_missing_signature_header(self):
        secret = b"taiga-secret"
        req = MagicMock()
        req.headers = {"X-TAIGA-WEBHOOK-SIGNATURE": ""}
        req.data = b"body"
        assert verify_taiga_signature(req, secret) is False

    def test_empty_body(self):
        secret = b"taiga-secret"
        body = b""
        req = self._make_request(body, secret)
        assert verify_taiga_signature(req, secret) is True
