"""Tests for utils/taiga_token/taiga_auth.py"""

import time, pytest
from unittest.mock import patch, MagicMock


class TestGetTaigaToken:
    def setup_method(self):
        """Clear the token cache before each test."""
        import utils.taiga_token.taiga_auth as mod

        mod._TOKENS.clear()

    @patch("utils.taiga_token.taiga_auth.requests.post")
    def test_new_token_acquired(self, mock_post):
        from utils.taiga_token.taiga_auth import get_taiga_token

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"auth_token": "new_tok"}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        token = get_taiga_token("user", "pass")
        assert token == "new_tok"
        mock_post.assert_called_once()

    @patch("utils.taiga_token.taiga_auth.requests.post")
    def test_cached_token_reused(self, mock_post):
        from utils.taiga_token.taiga_auth import get_taiga_token

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"auth_token": "cached_tok"}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        t1 = get_taiga_token("user", "pass")
        t2 = get_taiga_token("user", "pass")
        assert t1 == t2
        assert mock_post.call_count == 1  # Only one API call

    @patch("utils.taiga_token.taiga_auth.requests.post")
    def test_expired_token_refreshed(self, mock_post):
        from utils.taiga_token.taiga_auth import get_taiga_token, _TOKENS

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"auth_token": "tok1"}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        get_taiga_token("user", "pass")
        # Simulate expired token (set expiry in the past)
        _TOKENS[("user", "pass")] = ("tok1", time.time() - 100)

        mock_resp.json.return_value = {"auth_token": "tok2"}
        t2 = get_taiga_token("user", "pass")
        assert t2 == "tok2"
        assert mock_post.call_count == 2

    @patch("utils.taiga_token.taiga_auth.requests.post")
    def test_different_credentials_separate_tokens(self, mock_post):
        from utils.taiga_token.taiga_auth import get_taiga_token

        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            resp = MagicMock()
            resp.json.return_value = {"auth_token": f"tok_{call_count[0]}"}
            resp.raise_for_status = MagicMock()
            return resp

        mock_post.side_effect = side_effect

        t1 = get_taiga_token("user1", "pass1")
        t2 = get_taiga_token("user2", "pass2")
        assert t1 != t2
        assert mock_post.call_count == 2

    @patch("utils.taiga_token.taiga_auth.requests.post")
    def test_http_error_raises(self, mock_post):
        import requests
        from utils.taiga_token.taiga_auth import get_taiga_token

        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("401")
        mock_post.return_value = mock_resp

        with pytest.raises(requests.HTTPError):
            get_taiga_token("user", "wrong")
