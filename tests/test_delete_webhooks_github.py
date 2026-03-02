"""Tests for utils/webhook_deletion/delete_webhooks_github.py"""
import pytest
from unittest.mock import patch, MagicMock


class TestListGithubHooks:
    @patch("utils.webhook_deletion.delete_webhooks_github.requests.get")
    def test_list_hooks(self, mock_get):
        from utils.webhook_deletion.delete_webhooks_github import list_github_hooks

        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"id": 1, "config": {"url": "http://x"}}]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        hooks = list_github_hooks("owner", "repo")
        assert len(hooks) == 1


class TestDeleteGithubHook:
    @patch("utils.webhook_deletion.delete_webhooks_github.requests.delete")
    def test_delete_hook(self, mock_delete):
        from utils.webhook_deletion.delete_webhooks_github import delete_github_hook

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_delete.return_value = mock_resp

        result = delete_github_hook("owner", "repo", 123)
        assert result == mock_resp


class TestDeleteAllGithubWebhooks:
    @patch("utils.webhook_deletion.delete_webhooks_github.delete_github_hook")
    @patch("utils.webhook_deletion.delete_webhooks_github.list_github_hooks")
    @patch("utils.webhook_deletion.delete_webhooks_github.pymongo.MongoClient")
    def test_deletes_matching_webhooks(self, mock_mongo, mock_list, mock_delete):
        from utils.webhook_deletion.delete_webhooks_github import delete_all_github_webhooks

        # Setup mock MongoDB
        mock_db = MagicMock()
        mock_db.list_collection_names.return_value = ["github_prj.commits", "other"]
        mock_db.__getitem__ = MagicMock()
        mock_db["github_prj.commits"].distinct.return_value = ["Org/repo"]
        mock_mongo.return_value.__getitem__ = MagicMock(return_value=mock_db)

        # Setup mock hooks
        mock_list.return_value = [
            {"id": 1, "config": {"url": "https://target.url/webhook"}},
            {"id": 2, "config": {"url": "https://other.url/webhook"}},
        ]

        delete_all_github_webhooks("https://target.url/webhook")
        mock_delete.assert_called_once_with("Org", "repo", 1)

    @patch("utils.webhook_deletion.delete_webhooks_github.list_github_hooks")
    @patch("utils.webhook_deletion.delete_webhooks_github.pymongo.MongoClient")
    def test_http_error_listing_continues(self, mock_mongo, mock_list):
        import requests
        from utils.webhook_deletion.delete_webhooks_github import delete_all_github_webhooks

        mock_db = MagicMock()
        mock_db.list_collection_names.return_value = ["github_prj.commits"]
        mock_db["github_prj.commits"].distinct.return_value = ["Org/repo"]
        mock_mongo.return_value.__getitem__ = MagicMock(return_value=mock_db)

        mock_list.side_effect = requests.HTTPError("403 Forbidden")

        # Should not raise
        delete_all_github_webhooks("https://target.url/webhook")
