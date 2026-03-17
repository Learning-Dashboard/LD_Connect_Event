"""Tests for utils/taiga_token/get_taiga_token.py"""

import pytest
from unittest.mock import patch, MagicMock


class TestGetToken:
    @patch("utils.taiga_token.get_taiga_token.requests.post")
    def test_successful_login(self, mock_post):
        from utils.taiga_token.get_taiga_token import get_token

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"auth_token": "tok123"}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        payload = {"username": "u", "password": "p", "type": "normal"}
        token = get_token(payload)
        assert token == "tok123"
        mock_post.assert_called_once()

    @patch("utils.taiga_token.get_taiga_token.requests.post")
    def test_token_not_in_response(self, mock_post):
        from utils.taiga_token.get_taiga_token import get_token

        mock_resp = MagicMock()
        mock_resp.json.return_value = {}  # No auth_token
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        token = get_token({"username": "u", "password": "p", "type": "normal"})
        assert token is None

    @patch("utils.taiga_token.get_taiga_token.requests.post")
    def test_http_error_raises(self, mock_post):
        import requests
        from utils.taiga_token.get_taiga_token import get_token

        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("401")
        mock_post.return_value = mock_resp

        with pytest.raises(requests.HTTPError):
            get_token({"username": "u", "password": "wrong", "type": "normal"})
