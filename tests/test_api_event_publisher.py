"""Tests for routes/API_publisher/API_event_publisher.py"""

import pytest
from unittest.mock import patch, MagicMock


class TestNotifyEvalPush:
    @patch("routes.API_publisher.API_event_publisher.requests.post")
    def test_successful_notification(self, mock_post):
        from routes.API_publisher.API_event_publisher import notify_eval_push

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "ok"}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        notify_eval_push("push", "TestPrj", "devuser", "default")
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        sent_data = call_kwargs[1]["json"]
        assert sent_data["event_type"] == "push"
        assert sent_data["prj"] == "TestPrj"
        assert sent_data["author_login"] == "devuser"
        assert sent_data["quality_model"] == "default"

    @patch("routes.API_publisher.API_event_publisher.requests.post")
    def test_network_error_does_not_raise(self, mock_post):
        import requests as req
        from routes.API_publisher.API_event_publisher import notify_eval_push

        mock_post.side_effect = req.RequestException("Connection refused")
        # Should not raise — it logs and continues
        notify_eval_push("push", "P", "u", "qm")

    @patch.dict("os.environ", {"EVAL_HOST": "custom-host", "EVAL_PORT": "9999"})
    @patch("routes.API_publisher.API_event_publisher.requests.post")
    def test_custom_host_port(self, mock_post):
        from routes.API_publisher.API_event_publisher import notify_eval_push

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {}
        mock_post.return_value = mock_resp

        notify_eval_push("issue", "P", "u", "qm")
        called_url = mock_post.call_args[0][0]
        assert "custom-host" in called_url
        assert "9999" in called_url
