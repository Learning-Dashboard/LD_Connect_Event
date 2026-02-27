"""Tests for routes/verify_signature/verify_signature_github.py"""
import hashlib, hmac, pytest
from unittest.mock import MagicMock
from routes.verify_signature.verify_signature_github import verify_github_signature


class TestVerifyGithubSignature:
    def _make_request(self, body: bytes, secret: bytes, tamper: bool = False):
        """Helper to create a mock request with proper signature."""
        sig = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
        if tamper:
            sig = sig[:-4] + "XXXX"
        req = MagicMock()
        req.headers = {"X-Hub-Signature-256": sig}
        req.data = body
        return req

    def test_valid_signature(self):
        secret = b"my-secret"
        body = b'{"action":"push"}'
        req = self._make_request(body, secret)
        assert verify_github_signature(req, secret) is True

    def test_invalid_signature(self):
        secret = b"my-secret"
        body = b'{"action":"push"}'
        req = self._make_request(body, secret, tamper=True)
        assert verify_github_signature(req, secret) is False

    def test_missing_signature_header(self):
        secret = b"my-secret"
        req = MagicMock()
        req.headers = {"X-Hub-Signature-256": ""}
        req.data = b"body"
        assert verify_github_signature(req, secret) is False

    def test_empty_body(self):
        secret = b"my-secret"
        body = b""
        req = self._make_request(body, secret)
        assert verify_github_signature(req, secret) is True

    def test_wrong_secret(self):
        secret = b"correct-secret"
        body = b'{"test": true}'
        req = self._make_request(body, secret)
        assert verify_github_signature(req, b"wrong-secret") is False
