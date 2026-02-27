"""Tests for utils/webhook_deletion/delete_webhooks_taiga.py"""
import pytest
from unittest.mock import patch, MagicMock


class TestListTaigaHooks:
    @patch("utils.webhook_deletion.delete_webhooks_taiga.requests.get")
    def test_list_hooks(self, mock_get):
        from utils.webhook_deletion.delete_webhooks_taiga import list_taiga_hooks

        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"id": 1, "url": "http://x"}]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        hooks = list_taiga_hooks(42, "tok")
        assert len(hooks) == 1


class TestDeleteTaigaHook:
    @patch("utils.webhook_deletion.delete_webhooks_taiga.requests.delete")
    def test_delete_hook(self, mock_delete):
        from utils.webhook_deletion.delete_webhooks_taiga import delete_taiga_hook

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_delete.return_value = mock_resp

        result = delete_taiga_hook(123, "tok")
        assert result == mock_resp


class TestDeleteAllTaigaWebhooks:
    @patch("utils.webhook_deletion.delete_webhooks_taiga.delete_taiga_hook")
    @patch("utils.webhook_deletion.delete_webhooks_taiga.list_taiga_hooks")
    @patch("utils.webhook_deletion.delete_webhooks_taiga.pymongo.MongoClient")
    def test_deletes_matching_webhooks(self, mock_mongo, mock_list, mock_delete):
        from utils.webhook_deletion.delete_webhooks_taiga import delete_all_taiga_webhooks

        mock_db = MagicMock()
        mock_db.list_collection_names.return_value = ["taiga_prj.epics", "other"]
        mock_db["taiga_prj.epics"].distinct.return_value = [42]
        mock_mongo.return_value.__getitem__ = MagicMock(return_value=mock_db)

        mock_list.return_value = [
            {"id": 1, "url": "https://target.url/webhook"},
            {"id": 2, "url": "https://other.url/webhook"},
        ]

        delete_all_taiga_webhooks("tok", "https://target.url/webhook")
        mock_delete.assert_called_once_with(1, "tok")

    @patch("utils.webhook_deletion.delete_webhooks_taiga.delete_taiga_hook")
    @patch("utils.webhook_deletion.delete_webhooks_taiga.list_taiga_hooks")
    @patch("utils.webhook_deletion.delete_webhooks_taiga.pymongo.MongoClient")
    def test_delete_error_continues(self, mock_mongo, mock_list, mock_delete):
        import requests
        from utils.webhook_deletion.delete_webhooks_taiga import delete_all_taiga_webhooks

        mock_db = MagicMock()
        mock_db.list_collection_names.return_value = ["taiga_prj.epics"]
        mock_db["taiga_prj.epics"].distinct.return_value = [42]
        mock_mongo.return_value.__getitem__ = MagicMock(return_value=mock_db)

        mock_list.return_value = [{"id": 1, "url": "https://target.url"}]
        mock_delete.side_effect = requests.HTTPError("403")

        # Should not raise
        delete_all_taiga_webhooks("tok", "https://target.url")
