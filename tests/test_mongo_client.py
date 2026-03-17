"""Tests for database/mongo_client.py"""

from unittest.mock import patch, MagicMock


class TestMongoClient:
    def test_get_collection_returns_collection(self):
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch("database.mongo_client.db", mock_db):
            from database.mongo_client import get_collection

            result = get_collection("test_collection")
            mock_db.__getitem__.assert_called_once_with("test_collection")
            assert result == mock_collection

    def test_get_collection_different_names(self):
        mock_db = MagicMock()
        collections = {}

        def side_effect(name):
            if name not in collections:
                collections[name] = MagicMock(name=f"coll_{name}")
            return collections[name]

        mock_db.__getitem__ = MagicMock(side_effect=side_effect)

        with patch("database.mongo_client.db", mock_db):
            from database.mongo_client import get_collection

            c1 = get_collection("commits")
            c2 = get_collection("issues")
            assert c1 != c2
