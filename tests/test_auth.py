"""Tests for API key auth middleware."""
import os
os.environ.setdefault("ENVIRONMENT", "test")

import pytest
from unittest.mock import patch, MagicMock
import importlib


def _make_mock_config(auth_enabled, api_keys="test-key-1,test-key-2"):
    mock = MagicMock()
    mock.AUTH_ENABLED = auth_enabled
    mock.API_KEYS = api_keys
    return mock


def test_valid_api_key_passes():
    mock_config = _make_mock_config(auth_enabled=True)
    with patch("src.shared.auth.middleware._get_config", return_value=mock_config):
        from src.shared.auth.middleware import validate_api_key
        result = validate_api_key("test-key-1")
        assert result == "test-key-1"


def test_invalid_api_key_rejected():
    mock_config = _make_mock_config(auth_enabled=True)
    with patch("src.shared.auth.middleware._get_config", return_value=mock_config):
        from src.shared.auth.middleware import validate_api_key
        with pytest.raises(ValueError, match="Invalid API key"):
            validate_api_key("wrong-key")


def test_missing_api_key_rejected():
    mock_config = _make_mock_config(auth_enabled=True)
    with patch("src.shared.auth.middleware._get_config", return_value=mock_config):
        from src.shared.auth.middleware import validate_api_key
        with pytest.raises(ValueError, match="Missing API key"):
            validate_api_key(None)


def test_auth_disabled_allows_all():
    mock_config = _make_mock_config(auth_enabled=False)
    with patch("src.shared.auth.middleware._get_config", return_value=mock_config):
        from src.shared.auth.middleware import validate_api_key
        result = validate_api_key(None)
        assert result is None


def test_has_valid_api_key_true():
    mock_config = _make_mock_config(auth_enabled=True)
    with patch("src.shared.auth.middleware._get_config", return_value=mock_config):
        from src.shared.auth.middleware import has_valid_api_key
        assert has_valid_api_key("test-key-1") is True


def test_has_valid_api_key_false():
    mock_config = _make_mock_config(auth_enabled=True)
    with patch("src.shared.auth.middleware._get_config", return_value=mock_config):
        from src.shared.auth.middleware import has_valid_api_key
        assert has_valid_api_key("wrong") is False


def test_has_valid_api_key_disabled():
    mock_config = _make_mock_config(auth_enabled=False)
    with patch("src.shared.auth.middleware._get_config", return_value=mock_config):
        from src.shared.auth.middleware import has_valid_api_key
        assert has_valid_api_key(None) is True
