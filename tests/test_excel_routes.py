"""Tests for routes/excel_routes.py"""

import json
from unittest.mock import patch, MagicMock


class TestExcelWebhook:
    @patch("routes.excel_routes.get_collection")
    @patch("routes.excel_routes.parse_excel_event")
    def test_successful_excel_webhook(
        self, mock_parse, mock_coll, client, excel_payload
    ):
        mock_parse.return_value = {"team": "TestPrj", "activity_type": "Dev"}
        mock_collection = MagicMock()
        mock_coll.return_value = mock_collection

        resp = client.post(
            "/webhook/excel?prj=TestPrj&quality_model=default",
            data=json.dumps(excel_payload),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "OK"
        mock_collection.insert_one.assert_called_once()

    def test_missing_json_body(self, client):
        resp = client.post(
            "/webhook/excel?prj=TestPrj", data="", content_type="application/json"
        )
        assert resp.status_code == 400

    def test_missing_prj_param(self, client, excel_payload):
        resp = client.post(
            "/webhook/excel",
            data=json.dumps(excel_payload),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "prj" in data["error"].lower()

    @patch("routes.excel_routes.get_collection")
    @patch("routes.excel_routes.parse_excel_event")
    def test_parse_error_returns_400(
        self, mock_parse, mock_coll, client, excel_payload
    ):
        mock_parse.return_value = {"error": "Invalid data"}
        resp = client.post(
            "/webhook/excel?prj=TestPrj",
            data=json.dumps(excel_payload),
            content_type="application/json",
        )
        assert resp.status_code == 400

    @patch("routes.excel_routes.get_collection")
    @patch("routes.excel_routes.parse_excel_event")
    def test_collection_name_format(self, mock_parse, mock_coll, client, excel_payload):
        mock_parse.return_value = {"team": "MyPrj"}
        mock_coll.return_value = MagicMock()

        client.post(
            "/webhook/excel?prj=MyPrj",
            data=json.dumps(excel_payload),
            content_type="application/json",
        )
        mock_coll.assert_called_with("MyPrj_sheets")
