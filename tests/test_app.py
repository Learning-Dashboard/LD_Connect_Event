"""Tests for app.py"""

import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

from config.credentials_loader import (
    CredentialsConfigNotFoundError,
    ProjectCredentialsNotFoundError,
)


class TestCreateApp:
    def test_app_created(self, flask_app):
        assert flask_app is not None

    def test_blueprints_registered(self, flask_app):
        bp_names = [bp.name for bp in flask_app.iter_blueprints()]
        assert "github_bp" in bp_names
        assert "taiga_bp" in bp_names
        assert "excel_bp" in bp_names

    def test_github_webhook_route_exists(self, flask_app):
        rules = [rule.rule for rule in flask_app.url_map.iter_rules()]
        assert "/webhook/github" in rules

    def test_taiga_webhook_route_exists(self, flask_app):
        rules = [rule.rule for rule in flask_app.url_map.iter_rules()]
        assert "/webhook/taiga" in rules

    def test_excel_webhook_route_exists(self, flask_app):
        rules = [rule.rule for rule in flask_app.url_map.iter_rules()]
        assert "/webhook/excel" in rules

    def test_health_route_exists(self, flask_app):
        rules = [rule.rule for rule in flask_app.url_map.iter_rules()]
        assert "/health" in rules

    def test_testing_config(self, flask_app):
        assert flask_app.config["TESTING"] is True

    def test_health_route_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.get_json() == {"status": "ok"}

    @patch("routes.taiga_routes.get_collection")
    @patch(
        "routes.taiga_routes.parse_taiga_event",
        side_effect=CredentialsConfigNotFoundError("missing credentials config"),
    )
    @patch("routes.taiga_routes.verify_taiga_signature", return_value=True)
    def test_credentials_config_error_returns_500(
        self, mock_verify, mock_parse, mock_coll, client, taiga_task_payload
    ):
        mock_coll.return_value = MagicMock()
        body = json.dumps(taiga_task_payload)
        signature = hmac.new(
            b"test-taiga-secret", body.encode(), hashlib.sha1
        ).hexdigest()

        response = client.post(
            "/webhook/taiga?prj=TestPrj",
            data=body,
            content_type="application/json",
            headers={"X-TAIGA-WEBHOOK-SIGNATURE": signature},
        )

        assert response.status_code == 500
        assert response.get_json() == {
            "details": "missing credentials config",
            "error": "Credentials configuration error",
        }

    @patch("routes.taiga_routes.get_collection")
    @patch(
        "routes.taiga_routes.parse_taiga_event",
        side_effect=ProjectCredentialsNotFoundError("unknown project"),
    )
    @patch("routes.taiga_routes.verify_taiga_signature", return_value=True)
    def test_unknown_project_credentials_returns_400(
        self, mock_verify, mock_parse, mock_coll, client, taiga_task_payload
    ):
        mock_coll.return_value = MagicMock()
        body = json.dumps(taiga_task_payload)
        signature = hmac.new(
            b"test-taiga-secret", body.encode(), hashlib.sha1
        ).hexdigest()

        response = client.post(
            "/webhook/taiga?prj=UnknownTeam",
            data=body,
            content_type="application/json",
            headers={"X-TAIGA-WEBHOOK-SIGNATURE": signature},
        )

        assert response.status_code == 400
        assert response.get_json() == {
            "details": "'unknown project'",
            "error": "Unknown project credentials",
        }
