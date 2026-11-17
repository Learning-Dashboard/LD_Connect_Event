"""Tests for utils/taiga_token/taiga_auth.py"""

import time
import pytest
from unittest.mock import patch, MagicMock

from config.credentials_loader import TaigaContext

AUTH_URL = "https://taiga.example/api/v1/auth"
OTHER_AUTH_URL = "https://other-taiga.example/api/v1/auth"


def _login_response(token):
    resp = MagicMock()
    resp.json.return_value = {"auth_token": token}
    resp.raise_for_status = MagicMock()
    return resp


@pytest.fixture(autouse=True)
def clear_token_cache():
    """Clear the token cache before each test."""
    import utils.taiga_token.taiga_auth as mod

    mod._TOKENS.clear()
    yield
    mod._TOKENS.clear()


class TestGetTaigaToken:
    @patch("utils.taiga_token.taiga_auth.requests.post")
    def test_new_token_acquired(self, mock_post):
        from utils.taiga_token.taiga_auth import AUTH_TIMEOUT, get_taiga_token

        mock_post.return_value = _login_response("new_tok")

        token = get_taiga_token(AUTH_URL, "user", "pass")
        assert token == "new_tok"
        mock_post.assert_called_once()
        assert mock_post.call_args.args[0] == AUTH_URL
        assert mock_post.call_args.kwargs["json"] == {
            "type": "normal",
            "username": "user",
            "password": "pass",
        }
        assert mock_post.call_args.kwargs["timeout"] == AUTH_TIMEOUT

    @patch("utils.taiga_token.taiga_auth.requests.post")
    def test_cached_token_reused(self, mock_post):
        from utils.taiga_token.taiga_auth import get_taiga_token

        mock_post.return_value = _login_response("cached_tok")

        t1 = get_taiga_token(AUTH_URL, "user", "pass")
        t2 = get_taiga_token(AUTH_URL, "user", "pass")
        assert t1 == t2
        assert mock_post.call_count == 1  # Only one API call

    @patch("utils.taiga_token.taiga_auth.requests.post")
    def test_expired_token_refreshed(self, mock_post):
        from utils.taiga_token.taiga_auth import get_taiga_token, _TOKENS

        mock_post.return_value = _login_response("tok1")

        get_taiga_token(AUTH_URL, "user", "pass")
        # Simulate expired token (set expiry in the past)
        _TOKENS[(AUTH_URL, "user", "pass")] = ("tok1", time.time() - 100)

        mock_post.return_value = _login_response("tok2")
        t2 = get_taiga_token(AUTH_URL, "user", "pass")
        assert t2 == "tok2"
        assert mock_post.call_count == 2

    @patch("utils.taiga_token.taiga_auth.requests.post")
    def test_different_credentials_separate_tokens(self, mock_post):
        from utils.taiga_token.taiga_auth import get_taiga_token

        mock_post.side_effect = [_login_response("tok_1"), _login_response("tok_2")]

        t1 = get_taiga_token(AUTH_URL, "user1", "pass1")
        t2 = get_taiga_token(AUTH_URL, "user2", "pass2")
        assert t1 != t2
        assert mock_post.call_count == 2

    @patch("utils.taiga_token.taiga_auth.requests.post")
    def test_same_credentials_on_different_servers_separate_tokens(self, mock_post):
        from utils.taiga_token.taiga_auth import get_taiga_token

        mock_post.side_effect = [_login_response("tok_a"), _login_response("tok_b")]

        assert get_taiga_token(AUTH_URL, "user", "pass") == "tok_a"
        assert get_taiga_token(OTHER_AUTH_URL, "user", "pass") == "tok_b"
        assert [c.args[0] for c in mock_post.call_args_list] == [AUTH_URL, OTHER_AUTH_URL]
        # Each server keeps its own cached token
        assert get_taiga_token(AUTH_URL, "user", "pass") == "tok_a"
        assert mock_post.call_count == 2

    @patch("utils.taiga_token.taiga_auth.requests.post")
    def test_http_error_raises(self, mock_post):
        import requests
        from utils.taiga_token.taiga_auth import get_taiga_token

        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("401")
        mock_post.return_value = mock_resp

        with pytest.raises(requests.HTTPError):
            get_taiga_token(AUTH_URL, "user", "wrong")


class TestAuthHeader:
    @pytest.mark.parametrize(
        "token, expected",
        [
            ("jwt-token", "Bearer jwt-token"),
            ("app-id:hash", "Application app-id:hash"),
            ("Bearer jwt-token", "Bearer jwt-token"),
            ("Application app-id:hash", "Application app-id:hash"),
            ("  jwt-token  ", "Bearer jwt-token"),
        ],
    )
    def test_scheme(self, token, expected):
        from utils.taiga_token.taiga_auth import auth_header

        assert auth_header(token) == {"Authorization": expected}


class TestAuthHeaders:
    @patch("utils.taiga_token.taiga_auth.requests.post")
    def test_static_token_does_not_log_in(self, mock_post):
        from utils.taiga_token.taiga_auth import auth_headers

        ctx = TaigaContext(api_url="https://t/api/v1", auth_url=AUTH_URL, token="app:hash")

        assert auth_headers(ctx) == {"Authorization": "Application app:hash"}
        mock_post.assert_not_called()

    @patch("utils.taiga_token.taiga_auth.requests.post")
    def test_login_at_the_auth_url_of_the_context(self, mock_post):
        from utils.taiga_token.taiga_auth import auth_headers

        mock_post.return_value = _login_response("login:jwt")
        ctx = TaigaContext(
            api_url="https://t/api/v1", auth_url=AUTH_URL, username="user", password="pass"
        )

        # A login token is always a Bearer token, whatever its content
        assert auth_headers(ctx) == {"Authorization": "Bearer login:jwt"}
        assert mock_post.call_args.args[0] == AUTH_URL
