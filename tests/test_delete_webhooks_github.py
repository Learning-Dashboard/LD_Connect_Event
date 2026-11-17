"""Tests for utils/webhook_deletion/delete_webhooks_github.py"""

import pytest
from unittest.mock import call, patch, MagicMock


def _mongo_with(collections: dict) -> MagicMock:
    """Mongo client whose database has <collections>: name -> distinct("repository") values."""
    by_name = {}
    for name, values in collections.items():
        by_name[name] = MagicMock()
        by_name[name].distinct.return_value = values

    mock_db = MagicMock()
    mock_db.list_collection_names.return_value = list(collections)
    mock_db.__getitem__.side_effect = by_name.__getitem__

    mock_client = MagicMock()
    mock_client.__getitem__.return_value = mock_db
    return mock_client


class TestListGithubHooks:
    @patch("utils.webhook_deletion.delete_webhooks_github.requests.get")
    def test_list_hooks(self, mock_get):
        from utils.webhook_deletion.delete_webhooks_github import list_github_hooks

        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"id": 1, "config": {"url": "http://x"}}]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        hooks = list_github_hooks("owner", "repo", "ghp_TOKEN")
        assert len(hooks) == 1
        assert mock_get.call_args.args[0].endswith("/repos/owner/repo/hooks")
        assert mock_get.call_args.kwargs["headers"]["Authorization"] == "Bearer ghp_TOKEN"


class TestDeleteGithubHook:
    @patch("utils.webhook_deletion.delete_webhooks_github.requests.delete")
    def test_delete_hook(self, mock_delete):
        from utils.webhook_deletion.delete_webhooks_github import delete_github_hook

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_delete.return_value = mock_resp

        result = delete_github_hook("owner", "repo", 123, "ghp_TOKEN")
        assert result == mock_resp
        assert mock_delete.call_args.args[0].endswith("/repos/owner/repo/hooks/123")
        assert (
            mock_delete.call_args.kwargs["headers"]["Authorization"] == "Bearer ghp_TOKEN"
        )


@pytest.mark.usefixtures("sample_credentials_config")
class TestDeleteAllGithubWebhooks:
    @patch("utils.webhook_deletion.delete_webhooks_github.delete_github_hook")
    @patch("utils.webhook_deletion.delete_webhooks_github.list_github_hooks")
    @patch("utils.webhook_deletion.delete_webhooks_github.pymongo.MongoClient")
    def test_deletes_matching_webhooks(self, mock_mongo, mock_list, mock_delete):
        from utils.webhook_deletion.delete_webhooks_github import (
            delete_all_github_webhooks,
        )

        mock_mongo.return_value = _mongo_with(
            {"github_TeamAlpha.commits": ["Org/repo"], "other": ["Ignored/repo"]}
        )
        mock_list.return_value = [
            {"id": 1, "config": {"url": "https://target.url/webhook"}},
            {"id": 2, "config": {"url": "https://other.url/webhook"}},
        ]

        delete_all_github_webhooks("https://target.url/webhook")

        mock_list.assert_called_once_with("Org", "repo", "ghp_FAKETOKEN123")
        mock_delete.assert_called_once_with("Org", "repo", 1, "ghp_FAKETOKEN123")

    @patch("utils.webhook_deletion.delete_webhooks_github.delete_github_hook")
    @patch("utils.webhook_deletion.delete_webhooks_github.list_github_hooks")
    @patch("utils.webhook_deletion.delete_webhooks_github.pymongo.MongoClient")
    def test_each_team_uses_the_token_of_its_subject(
        self, mock_mongo, mock_list, mock_delete
    ):
        from utils.webhook_deletion.delete_webhooks_github import (
            delete_all_github_webhooks,
        )

        mock_mongo.return_value = _mongo_with(
            {
                "github_TeamAlpha.commits": ["OrgA/repo"],
                "github_TeamGamma.commits": ["OrgB/repo"],
            }
        )
        mock_list.return_value = [{"id": 1, "config": {"url": "https://target.url"}}]

        delete_all_github_webhooks("https://target.url")

        assert mock_delete.call_args_list == [
            call("OrgA", "repo", 1, "ghp_FAKETOKEN123"),
            call("OrgB", "repo", 1, "ghp_FAKETOKEN456"),
        ]

    @patch("utils.webhook_deletion.delete_webhooks_github.delete_github_hook")
    @patch("utils.webhook_deletion.delete_webhooks_github.list_github_hooks")
    @patch("utils.webhook_deletion.delete_webhooks_github.pymongo.MongoClient")
    def test_team_missing_from_credentials_is_skipped(
        self, mock_mongo, mock_list, mock_delete
    ):
        from utils.webhook_deletion.delete_webhooks_github import (
            delete_all_github_webhooks,
        )

        mock_mongo.return_value = _mongo_with(
            {
                "github_UnknownTeam.commits": ["OrgX/repo"],
                "github_TeamGamma.commits": ["OrgB/repo"],
            }
        )
        mock_list.return_value = [{"id": 1, "config": {"url": "https://target.url"}}]

        delete_all_github_webhooks("https://target.url")

        mock_list.assert_called_once_with("OrgB", "repo", "ghp_FAKETOKEN456")
        mock_delete.assert_called_once_with("OrgB", "repo", 1, "ghp_FAKETOKEN456")

    @patch("utils.webhook_deletion.delete_webhooks_github.delete_github_hook")
    @patch("utils.webhook_deletion.delete_webhooks_github.list_github_hooks")
    @patch("utils.webhook_deletion.delete_webhooks_github.pymongo.MongoClient")
    def test_http_error_listing_continues(self, mock_mongo, mock_list, mock_delete):
        import requests
        from utils.webhook_deletion.delete_webhooks_github import (
            delete_all_github_webhooks,
        )

        mock_mongo.return_value = _mongo_with({"github_TeamAlpha.commits": ["Org/repo"]})
        mock_list.side_effect = requests.HTTPError("403 Forbidden")

        # Should not raise
        delete_all_github_webhooks("https://target.url/webhook")
        mock_delete.assert_not_called()
