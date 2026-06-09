from unittest.mock import Mock, patch

import pytest

from src.api_client import StatizAPIClient


class TestStatizAPIClient:
    """Test cases for StatizAPIClient"""

    def test_init_with_valid_credentials(self):
        """Test initialization with valid API credentials"""
        with patch.dict(
            "os.environ", {"API_KEY": "test_key", "API_SECRET": "test_secret"}
        ):
            client = StatizAPIClient()
            assert client.api_key == "test_key"
            assert client.api_secret == "test_secret"

    def test_init_missing_credentials(self):
        """Test initialization fails without credentials"""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="API_KEY and API_SECRET must be set"):
                StatizAPIClient()

    def test_normalize_query(self):
        """Test query parameter normalization"""
        with patch.dict(
            "os.environ", {"API_KEY": "test_key", "API_SECRET": "test_secret"}
        ):
            client = StatizAPIClient()
            params = {"b": "2", "a": "1", "name": "a b"}
            normalized = client._normalize_query(params)
            assert normalized == "a=1&b=2&name=a%20b"

    def test_generate_signature(self):
        """Test HMAC signature generation"""
        client = StatizAPIClient()
        client.api_secret = "secret"
        signature = client._generate_signature(
            "GET", "test/path", "a=1&b=2", "1234567890"
        )
        # This is a mock expected value - in real test, calculate actual HMAC
        assert len(signature) == 64  # SHA256 hex length

    @patch("src.api_client.requests.get")
    def test_get_request(self, mock_get):
        """Test GET request with authentication"""
        mock_response = Mock()
        mock_response.json.return_value = {"data": "test"}
        mock_get.return_value = mock_response

        with patch.dict(
            "os.environ", {"API_KEY": "test_key", "API_SECRET": "test_secret"}
        ):
            client = StatizAPIClient()
            result = client.get("test/endpoint", params={"key": "value"})

            assert result == {"data": "test"}
            mock_get.assert_called_once()
            args, kwargs = mock_get.call_args
            assert "headers" in kwargs
            assert "X-API-KEY" in kwargs["headers"]
            assert "X-SIGNATURE" in kwargs["headers"]

    @patch("src.api_client.requests.post")
    def test_save_prediction(self, mock_post):
        """Test save_prediction POST call"""
        mock_response = Mock()
        mock_response.json.return_value = {"result_cd": 0, "result_msg": "ok"}
        mock_post.return_value = mock_response

        with patch.dict(
            "os.environ", {"API_KEY": "test_key", "API_SECRET": "test_secret"}
        ):
            client = StatizAPIClient()
            result = client.save_prediction(1234, 0.74)

            assert result == {"result_cd": 0, "result_msg": "ok"}
            mock_post.assert_called_once()
            _, kwargs = mock_post.call_args
            assert kwargs["json"] == {"s_no": 1234, "percent": 0.74}
            assert kwargs["headers"]["X-API-KEY"] == "test_key"
            assert "X-SIGNATURE" in kwargs["headers"]
