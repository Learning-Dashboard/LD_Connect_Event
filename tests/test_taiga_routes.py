"""Tests for routes/taiga_routes.py"""

import hashlib
import hmac
import json
from unittest.mock import patch, MagicMock


class TestTaigaWebhook:
    def _post(self, client, payload, prj="TestPrj", quality_model="default"):
        body = json.dumps(payload)
        secret = b"test-taiga-secret"
        sig = hmac.new(secret, body.encode(), hashlib.sha1).hexdigest()
        return client.post(
            f"/webhook/taiga?prj={prj}&quality_model={quality_model}",
            data=body,
            content_type="application/json",
            headers={"X-TAIGA-WEBHOOK-SIGNATURE": sig},
        )

    @patch("routes.taiga_routes.notify_eval_push")
    @patch("routes.taiga_routes.get_collection")
    @patch("routes.taiga_routes.parse_taiga_event")
    @patch("routes.taiga_routes.verify_taiga_signature", return_value=True)
    def test_task_create_upserts(
        self,
        mock_verify,
        mock_parse,
        mock_coll,
        mock_notify,
        client,
        taiga_task_payload,
    ):
        mock_parse.return_value = {
            "event_type": "task",
            "task_id": 100,
            "assigned_by": "u",
            "subject": "S",
        }
        mock_collection = MagicMock()
        mock_coll.return_value = mock_collection

        resp = self._post(client, taiga_task_payload)
        assert resp.status_code == 200
        mock_collection.update_one.assert_called_once()
        mock_notify.assert_called_once()

    @patch("routes.taiga_routes.verify_taiga_signature", return_value=False)
    def test_invalid_signature_403(self, mock_verify, client, taiga_task_payload):
        resp = client.post(
            "/webhook/taiga?prj=P",
            data=json.dumps(taiga_task_payload),
            content_type="application/json",
            headers={"X-TAIGA-WEBHOOK-SIGNATURE": "bad"},
        )
        assert resp.status_code == 403

    @patch("routes.taiga_routes.verify_taiga_signature", return_value=True)
    def test_missing_json_400(self, mock_verify, client):
        resp = client.post(
            "/webhook/taiga?prj=P",
            data="",
            content_type="application/json",
            headers={"X-TAIGA-WEBHOOK-SIGNATURE": "x"},
        )
        assert resp.status_code == 400

    @patch("routes.taiga_routes.verify_taiga_signature", return_value=True)
    def test_unsupported_type_ignored(self, mock_verify, client):
        payload = {
            "type": "wiki",
            "action": "create",
            "data": {"id": 1, "project": {"name": "P"}},
        }
        resp = client.post(
            "/webhook/taiga?prj=P",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"X-TAIGA-WEBHOOK-SIGNATURE": "x"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ignored"

    @patch("routes.taiga_routes.notify_eval_push")
    @patch("routes.taiga_routes.get_collection")
    @patch("routes.taiga_routes.verify_taiga_signature", return_value=True)
    def test_delete_action(self, mock_verify, mock_coll, mock_notify, client):
        payload = {
            "type": "task",
            "action": "delete",
            "data": {"id": 99, "project": {"name": "P"}},
            "by": {"username": "u"},
        }
        mock_collection = MagicMock()
        mock_coll.return_value = mock_collection

        resp = client.post(
            "/webhook/taiga?prj=P",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"X-TAIGA-WEBHOOK-SIGNATURE": "x"},
        )
        assert resp.status_code == 200
        mock_collection.delete_one.assert_called_once_with({"task_id": 99})
        mock_notify.assert_called_once_with("task", "P", "u", None)

    @patch("routes.taiga_routes.get_collection")
    @patch("routes.taiga_routes.verify_taiga_signature", return_value=True)
    def test_delete_no_id_returns_400(self, mock_verify, mock_coll, client):
        payload = {
            "type": "task",
            "action": "delete",
            "data": {"id": "", "project": {"name": "P"}},
            "by": {"username": "u"},
        }
        mock_coll.return_value = MagicMock()

        resp = client.post(
            "/webhook/taiga?prj=P",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"X-TAIGA-WEBHOOK-SIGNATURE": "x"},
        )
        assert resp.status_code == 400

    @patch("routes.taiga_routes.notify_eval_push")
    @patch("routes.taiga_routes.get_collection")
    @patch("routes.taiga_routes.parse_taiga_event")
    @patch("routes.taiga_routes.verify_taiga_signature", return_value=True)
    def test_userstory_upsert(
        self,
        mock_verify,
        mock_parse,
        mock_coll,
        mock_notify,
        client,
        taiga_userstory_payload,
    ):
        mock_parse.return_value = {
            "event_type": "userstory",
            "userstory_id": 400,
            "assigned_by": "u",
        }
        mock_collection = MagicMock()
        mock_coll.return_value = mock_collection

        resp = self._post(client, taiga_userstory_payload)
        assert resp.status_code == 200
        mock_collection.update_one.assert_called_once()

    @patch("routes.taiga_routes.notify_eval_push")
    @patch("routes.taiga_routes.get_collection")
    @patch("routes.taiga_routes.parse_taiga_event")
    @patch("routes.taiga_routes.verify_taiga_signature", return_value=True)
    def test_epic_upsert(
        self,
        mock_verify,
        mock_parse,
        mock_coll,
        mock_notify,
        client,
        taiga_epic_payload,
    ):
        mock_parse.return_value = {
            "event_type": "epic",
            "epic_id": 300,
            "assigned_by": "u",
        }
        mock_collection = MagicMock()
        mock_coll.return_value = mock_collection

        resp = self._post(client, taiga_epic_payload)
        assert resp.status_code == 200
        mock_collection.update_one.assert_called_once()

    @patch("routes.taiga_routes.notify_eval_push")
    @patch("routes.taiga_routes.get_collection")
    @patch("routes.taiga_routes.parse_taiga_event")
    @patch("routes.taiga_routes.verify_taiga_signature", return_value=True)
    def test_issue_upsert(
        self,
        mock_verify,
        mock_parse,
        mock_coll,
        mock_notify,
        client,
        taiga_issue_payload,
    ):
        mock_parse.return_value = {
            "event_type": "issue",
            "issue_id": 200,
            "assigned_by": "u",
        }
        mock_collection = MagicMock()
        mock_coll.return_value = mock_collection

        resp = self._post(client, taiga_issue_payload)
        assert resp.status_code == 200
        mock_collection.update_one.assert_called_once()

    @patch("routes.taiga_routes.notify_eval_push", side_effect=Exception("Eval down"))
    @patch("routes.taiga_routes.get_collection")
    @patch("routes.taiga_routes.parse_taiga_event")
    @patch("routes.taiga_routes.verify_taiga_signature", return_value=True)
    def test_notify_eval_error_returns_500(
        self,
        mock_verify,
        mock_parse,
        mock_coll,
        mock_notify,
        client,
        taiga_task_payload,
    ):
        mock_parse.return_value = {
            "event_type": "task",
            "task_id": 100,
            "assigned_by": "u",
        }
        mock_coll.return_value = MagicMock()

        resp = self._post(client, taiga_task_payload)
        assert resp.status_code == 500

    @patch("routes.taiga_routes.notify_eval_push")
    @patch("routes.taiga_routes.get_collection")
    @patch("routes.taiga_routes.parse_taiga_event")
    @patch("routes.taiga_routes.verify_taiga_signature", return_value=True)
    def test_userstory_no_id_returns_400(
        self, mock_verify, mock_parse, mock_coll, mock_notify, client
    ):
        payload = {
            "type": "userstory",
            "action": "create",
            "by": {"username": "u"},
            "data": {"id": 1, "project": {"id": 1, "name": "P"}},
        }
        mock_parse.return_value = {
            "event_type": "userstory",
            "userstory_id": None,
            "assigned_by": "u",
        }
        mock_coll.return_value = MagicMock()

        resp = client.post(
            "/webhook/taiga?prj=P",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"X-TAIGA-WEBHOOK-SIGNATURE": "x"},
        )
        assert resp.status_code == 400

    @patch("routes.taiga_routes.notify_eval_push")
    @patch("routes.taiga_routes.get_collection")
    @patch("routes.taiga_routes.parse_taiga_event")
    @patch("routes.taiga_routes.verify_taiga_signature", return_value=True)
    def test_task_no_id_returns_400(
        self, mock_verify, mock_parse, mock_coll, mock_notify, client
    ):
        payload = {
            "type": "task",
            "action": "create",
            "by": {"username": "u"},
            "data": {"id": 1, "project": {"id": 1, "name": "P"}},
        }
        mock_parse.return_value = {
            "event_type": "task",
            "task_id": None,
            "assigned_by": "u",
        }
        mock_coll.return_value = MagicMock()

        resp = client.post(
            "/webhook/taiga?prj=P",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"X-TAIGA-WEBHOOK-SIGNATURE": "x"},
        )
        assert resp.status_code == 400

    @patch("routes.taiga_routes.notify_eval_push")
    @patch("routes.taiga_routes.get_collection")
    @patch("routes.taiga_routes.parse_taiga_event")
    @patch("routes.taiga_routes.verify_taiga_signature", return_value=True)
    def test_epic_no_id_returns_400(
        self, mock_verify, mock_parse, mock_coll, mock_notify, client
    ):
        payload = {
            "type": "epic",
            "action": "create",
            "by": {"username": "u"},
            "data": {"id": 1, "project": {"id": 1, "name": "P"}},
        }
        mock_parse.return_value = {
            "event_type": "epic",
            "epic_id": None,
            "assigned_by": "u",
        }
        mock_coll.return_value = MagicMock()

        resp = client.post(
            "/webhook/taiga?prj=P",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"X-TAIGA-WEBHOOK-SIGNATURE": "x"},
        )
        assert resp.status_code == 400

    @patch("routes.taiga_routes.notify_eval_push")
    @patch("routes.taiga_routes.get_collection")
    @patch("routes.taiga_routes.parse_taiga_event")
    @patch("routes.taiga_routes.verify_taiga_signature", return_value=True)
    def test_issue_no_id_returns_400(
        self, mock_verify, mock_parse, mock_coll, mock_notify, client
    ):
        payload = {
            "type": "issue",
            "action": "create",
            "by": {"username": "u"},
            "data": {"id": 1, "project": {"id": 1, "name": "P"}},
        }
        mock_parse.return_value = {
            "event_type": "issue",
            "issue_id": None,
            "assigned_by": "u",
        }
        mock_coll.return_value = MagicMock()

        resp = client.post(
            "/webhook/taiga?prj=P",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"X-TAIGA-WEBHOOK-SIGNATURE": "x"},
        )
        assert resp.status_code == 400

    @patch("routes.taiga_routes.notify_eval_push")
    @patch("routes.taiga_routes.get_collection")
    @patch("routes.taiga_routes.parse_taiga_event")
    @patch("routes.taiga_routes.verify_taiga_signature", return_value=True)
    def test_collection_name_task(
        self,
        mock_verify,
        mock_parse,
        mock_coll,
        mock_notify,
        client,
        taiga_task_payload,
    ):
        mock_parse.return_value = {
            "event_type": "task",
            "task_id": 1,
            "assigned_by": "u",
        }
        mock_coll.return_value = MagicMock()

        self._post(client, taiga_task_payload, prj="MyPrj")
        mock_coll.assert_called_with("taiga_MyPrj.tasks")

    @patch("routes.taiga_routes.notify_eval_push")
    @patch("routes.taiga_routes.get_collection")
    @patch("routes.taiga_routes.parse_taiga_event")
    @patch("routes.taiga_routes.verify_taiga_signature", return_value=True)
    def test_collection_name_userstory(
        self,
        mock_verify,
        mock_parse,
        mock_coll,
        mock_notify,
        client,
        taiga_userstory_payload,
    ):
        mock_parse.return_value = {
            "event_type": "userstory",
            "userstory_id": 1,
            "assigned_by": "u",
        }
        mock_coll.return_value = MagicMock()

        self._post(client, taiga_userstory_payload, prj="MyPrj")
        mock_coll.assert_called_with("taiga_MyPrj.userstories")
