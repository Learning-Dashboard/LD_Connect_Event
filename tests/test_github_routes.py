"""Tests for routes/github_routes.py"""
import hashlib, hmac, json, pytest
from unittest.mock import patch, MagicMock


def _sign_payload(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class TestGithubWebhook:
    @patch("routes.github_routes.notify_eval_push")
    @patch("routes.github_routes.get_collection")
    @patch("routes.github_routes.parse_github_event")
    @patch("routes.github_routes.verify_github_signature", return_value=True)
    def test_push_event_inserts_commits(self, mock_verify, mock_parse, mock_coll, mock_notify, client):
        mock_parse.return_value = {
            "event": "commit",
            "team_name": "TestOrg",
            "repo_name": "TestOrg/repo",
            "sender_info": {"login": "dev"},
            "commits": [
                {"sha": "abc123", "message": "fix bug"}
            ]
        }
        mock_collection = MagicMock()
        mock_coll.return_value = mock_collection

        body = json.dumps({"test": True})
        resp = client.post(
            "/webhook/github?prj=TestPrj&quality_model=default",
            data=body,
            content_type="application/json",
            headers={
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": "sha256=fake"
            }
        )
        assert resp.status_code == 200
        mock_collection.insert_one.assert_called_once()
        mock_notify.assert_called_once()

    @patch("routes.github_routes.verify_github_signature", return_value=False)
    def test_invalid_signature_returns_403(self, mock_verify, client):
        resp = client.post(
            "/webhook/github?prj=TestPrj",
            data=json.dumps({"test": True}),
            content_type="application/json",
            headers={"X-Hub-Signature-256": "sha256=bad"}
        )
        assert resp.status_code == 403

    @patch("routes.github_routes.verify_github_signature", return_value=True)
    def test_missing_json_returns_400(self, mock_verify, client):
        resp = client.post(
            "/webhook/github?prj=TestPrj",
            data="",
            content_type="application/json",
            headers={"X-Hub-Signature-256": "sha256=x"}
        )
        assert resp.status_code == 400

    @patch("routes.github_routes.verify_github_signature", return_value=True)
    def test_missing_prj_returns_400(self, mock_verify, client):
        resp = client.post(
            "/webhook/github",
            data=json.dumps({"test": True}),
            content_type="application/json",
            headers={"X-Hub-Signature-256": "sha256=x"}
        )
        assert resp.status_code == 400

    @patch("routes.github_routes.get_collection")
    @patch("routes.github_routes.parse_github_event")
    @patch("routes.github_routes.verify_github_signature", return_value=True)
    def test_ignored_event_returns_200(self, mock_verify, mock_parse, mock_coll, client):
        mock_parse.return_value = {"event": "deployment", "ignored": True}

        resp = client.post(
            "/webhook/github?prj=TestPrj",
            data=json.dumps({"test": True}),
            content_type="application/json",
            headers={"X-GitHub-Event": "deployment", "X-Hub-Signature-256": "sha256=x"}
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ignored"

    @patch("routes.github_routes.notify_eval_push")
    @patch("routes.github_routes.get_collection")
    @patch("routes.github_routes.parse_github_event")
    @patch("routes.github_routes.verify_github_signature", return_value=True)
    def test_issue_event_inserts_doc(self, mock_verify, mock_parse, mock_coll, mock_notify, client):
        mock_parse.return_value = {
            "event": "issue",
            "team_name": "TestOrg",
            "repo_name": "TestOrg/repo",
            "sender_info": {"login": "dev"},
            "issue": {"number": 1, "title": "Bug"}
        }
        mock_collection = MagicMock()
        mock_coll.return_value = mock_collection

        resp = client.post(
            "/webhook/github?prj=TestPrj",
            data=json.dumps({"test": True}),
            content_type="application/json",
            headers={"X-GitHub-Event": "issues", "X-Hub-Signature-256": "sha256=x"}
        )
        assert resp.status_code == 200
        mock_collection.insert_one.assert_called_once()

    @patch("routes.github_routes.notify_eval_push")
    @patch("routes.github_routes.get_collection")
    @patch("routes.github_routes.parse_github_event")
    @patch("routes.github_routes.verify_github_signature", return_value=True)
    def test_pull_request_event(self, mock_verify, mock_parse, mock_coll, mock_notify, client):
        mock_parse.return_value = {
            "event": "pull_request",
            "team_name": "TestOrg",
            "repo_name": "TestOrg/repo",
            "sender_info": {"login": "dev"},
            "pull_request": {"number": 5}
        }
        mock_collection = MagicMock()
        mock_coll.return_value = mock_collection

        resp = client.post(
            "/webhook/github?prj=TestPrj",
            data=json.dumps({"test": True}),
            content_type="application/json",
            headers={"X-GitHub-Event": "pull_request", "X-Hub-Signature-256": "sha256=x"}
        )
        assert resp.status_code == 200

    @patch("routes.github_routes.parse_github_event")
    @patch("routes.github_routes.verify_github_signature", return_value=True)
    def test_error_in_parsed_data(self, mock_verify, mock_parse, client):
        mock_parse.return_value = {"error": "Something went wrong"}

        resp = client.post(
            "/webhook/github?prj=TestPrj",
            data=json.dumps({"test": True}),
            content_type="application/json",
            headers={"X-GitHub-Event": "push", "X-Hub-Signature-256": "sha256=x"}
        )
        assert resp.status_code == 400

    @patch("routes.github_routes.notify_eval_push", side_effect=Exception("Eval down"))
    @patch("routes.github_routes.get_collection")
    @patch("routes.github_routes.parse_github_event")
    @patch("routes.github_routes.verify_github_signature", return_value=True)
    def test_notify_eval_error_returns_500(self, mock_verify, mock_parse, mock_coll, mock_notify, client):
        mock_parse.return_value = {
            "event": "commit",
            "team_name": "T",
            "repo_name": "T/r",
            "sender_info": {"login": "u"},
            "commits": [{"sha": "a"}]
        }
        mock_coll.return_value = MagicMock()

        resp = client.post(
            "/webhook/github?prj=P",
            data=json.dumps({"test": True}),
            content_type="application/json",
            headers={"X-GitHub-Event": "push", "X-Hub-Signature-256": "sha256=x"}
        )
        assert resp.status_code == 500

    @patch("routes.github_routes.notify_eval_push")
    @patch("routes.github_routes.get_collection")
    @patch("routes.github_routes.parse_github_event")
    @patch("routes.github_routes.verify_github_signature", return_value=True)
    def test_collection_name_commit(self, mock_verify, mock_parse, mock_coll, mock_notify, client):
        mock_parse.return_value = {
            "event": "commit",
            "team_name": "T",
            "repo_name": "T/r",
            "sender_info": {"login": "u"},
            "commits": [{"sha": "a"}]
        }
        mock_coll.return_value = MagicMock()

        client.post(
            "/webhook/github?prj=MyPrj",
            data=json.dumps({"test": True}),
            content_type="application/json",
            headers={"X-GitHub-Event": "push", "X-Hub-Signature-256": "sha256=x"}
        )
        mock_coll.assert_called_with("github_MyPrj.commits")

    @patch("routes.github_routes.notify_eval_push")
    @patch("routes.github_routes.get_collection")
    @patch("routes.github_routes.parse_github_event")
    @patch("routes.github_routes.verify_github_signature", return_value=True)
    def test_collection_name_issue(self, mock_verify, mock_parse, mock_coll, mock_notify, client):
        mock_parse.return_value = {
            "event": "issue",
            "team_name": "T",
            "repo_name": "T/r",
            "sender_info": {"login": "u"},
            "issue": {"number": 1}
        }
        mock_coll.return_value = MagicMock()

        client.post(
            "/webhook/github?prj=MyPrj",
            data=json.dumps({"test": True}),
            content_type="application/json",
            headers={"X-GitHub-Event": "issues", "X-Hub-Signature-256": "sha256=x"}
        )
        mock_coll.assert_called_with("MyPrj_issues")
