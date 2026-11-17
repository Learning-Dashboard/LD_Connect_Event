"""Tests for utils/webhook_deletion/delete_webhooks_taiga.py"""

import pytest
from unittest.mock import call, patch, MagicMock

from config.credentials_loader import TaigaContext, get_taiga_context

CTX = TaigaContext(
    api_url="https://taiga.example/api/v1",
    auth_url="https://taiga.example/api/v1/auth",
    token="app:hash",
)


def _mongo_with(collections: dict) -> MagicMock:
    """Mongo client whose database has <collections>: name -> distinct("project_id") values."""
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


class TestListTaigaHooks:
    @patch("utils.webhook_deletion.delete_webhooks_taiga.requests.get")
    def test_list_hooks(self, mock_get):
        from utils.webhook_deletion.delete_webhooks_taiga import list_taiga_hooks

        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"id": 1, "url": "http://x"}]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        hooks = list_taiga_hooks(42, CTX)
        assert len(hooks) == 1
        # The webhooks are listed on the Taiga server of the subject
        assert mock_get.call_args.args[0] == "https://taiga.example/api/v1/webhooks"
        assert mock_get.call_args.kwargs["params"] == {"project": 42}
        assert mock_get.call_args.kwargs["headers"] == {
            "Authorization": "Application app:hash"
        }


class TestDeleteTaigaHook:
    @patch("utils.webhook_deletion.delete_webhooks_taiga.requests.delete")
    def test_delete_hook(self, mock_delete):
        from utils.webhook_deletion.delete_webhooks_taiga import delete_taiga_hook

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_delete.return_value = mock_resp

        result = delete_taiga_hook(123, CTX)
        assert result == mock_resp
        assert mock_delete.call_args.args[0] == "https://taiga.example/api/v1/webhooks/123"
        assert mock_delete.call_args.kwargs["headers"] == {
            "Authorization": "Application app:hash"
        }


@pytest.mark.usefixtures("sample_credentials_config")
class TestDeleteAllTaigaWebhooks:
    @patch("utils.webhook_deletion.delete_webhooks_taiga.delete_taiga_hook")
    @patch("utils.webhook_deletion.delete_webhooks_taiga.list_taiga_hooks")
    @patch("utils.webhook_deletion.delete_webhooks_taiga.pymongo.MongoClient")
    def test_deletes_matching_webhooks(self, mock_mongo, mock_list, mock_delete):
        from utils.webhook_deletion.delete_webhooks_taiga import (
            delete_all_taiga_webhooks,
        )

        mock_mongo.return_value = _mongo_with(
            {"taiga_TeamAlpha.epics": [42], "other": [7]}
        )
        mock_list.return_value = [
            {"id": 1, "url": "https://target.url/webhook"},
            {"id": 2, "url": "https://other.url/webhook"},
        ]

        delete_all_taiga_webhooks("https://target.url/webhook")

        ctx = get_taiga_context("TeamAlpha")
        mock_list.assert_called_once_with(42, ctx)
        mock_delete.assert_called_once_with(1, ctx)

    @patch("utils.webhook_deletion.delete_webhooks_taiga.delete_taiga_hook")
    @patch("utils.webhook_deletion.delete_webhooks_taiga.list_taiga_hooks")
    @patch("utils.webhook_deletion.delete_webhooks_taiga.pymongo.MongoClient")
    def test_each_team_uses_the_taiga_server_of_its_subject(
        self, mock_mongo, mock_list, mock_delete
    ):
        from utils.webhook_deletion.delete_webhooks_taiga import (
            delete_all_taiga_webhooks,
        )

        mock_mongo.return_value = _mongo_with(
            {"taiga_TeamAlpha.epics": [42], "taiga_TeamGamma.epics": [42]}
        )
        mock_list.return_value = [{"id": 1, "url": "https://target.url"}]

        delete_all_taiga_webhooks("https://target.url")

        own_ctx = get_taiga_context("TeamAlpha")
        fallback_ctx = get_taiga_context("TeamGamma")
        assert own_ctx.api_url != fallback_ctx.api_url
        assert mock_list.call_args_list == [call(42, own_ctx), call(42, fallback_ctx)]
        assert mock_delete.call_args_list == [call(1, own_ctx), call(1, fallback_ctx)]

    @patch("utils.webhook_deletion.delete_webhooks_taiga.delete_taiga_hook")
    @patch("utils.webhook_deletion.delete_webhooks_taiga.list_taiga_hooks")
    @patch("utils.webhook_deletion.delete_webhooks_taiga.pymongo.MongoClient")
    def test_team_missing_from_credentials_is_skipped(
        self, mock_mongo, mock_list, mock_delete
    ):
        from utils.webhook_deletion.delete_webhooks_taiga import (
            delete_all_taiga_webhooks,
        )

        mock_mongo.return_value = _mongo_with(
            {"taiga_UnknownTeam.epics": [1], "taiga_TeamGamma.epics": [42]}
        )
        mock_list.return_value = [{"id": 1, "url": "https://target.url"}]

        delete_all_taiga_webhooks("https://target.url")

        ctx = get_taiga_context("TeamGamma")
        mock_list.assert_called_once_with(42, ctx)
        mock_delete.assert_called_once_with(1, ctx)

    @patch("utils.webhook_deletion.delete_webhooks_taiga.delete_taiga_hook")
    @patch("utils.webhook_deletion.delete_webhooks_taiga.list_taiga_hooks")
    @patch("utils.webhook_deletion.delete_webhooks_taiga.pymongo.MongoClient")
    def test_list_error_continues_with_next_project(
        self, mock_mongo, mock_list, mock_delete
    ):
        import requests
        from utils.webhook_deletion.delete_webhooks_taiga import (
            delete_all_taiga_webhooks,
        )

        mock_mongo.return_value = _mongo_with({"taiga_TeamAlpha.epics": [41, 42]})
        mock_list.side_effect = [
            requests.ConnectionError("unreachable"),
            [{"id": 1, "url": "https://target.url"}],
        ]

        delete_all_taiga_webhooks("https://target.url")

        mock_delete.assert_called_once_with(1, get_taiga_context("TeamAlpha"))

    @patch("utils.webhook_deletion.delete_webhooks_taiga.delete_taiga_hook")
    @patch("utils.webhook_deletion.delete_webhooks_taiga.list_taiga_hooks")
    @patch("utils.webhook_deletion.delete_webhooks_taiga.pymongo.MongoClient")
    def test_delete_error_continues(self, mock_mongo, mock_list, mock_delete):
        import requests
        from utils.webhook_deletion.delete_webhooks_taiga import (
            delete_all_taiga_webhooks,
        )

        mock_mongo.return_value = _mongo_with({"taiga_TeamAlpha.epics": [42]})
        mock_list.return_value = [{"id": 1, "url": "https://target.url"}]
        mock_delete.side_effect = requests.HTTPError("403")

        # Should not raise
        delete_all_taiga_webhooks("https://target.url")
