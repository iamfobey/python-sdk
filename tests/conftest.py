"""
Pytest configuration and fixtures.

This module provides shared fixtures for the test suite.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

import stendly
from stendly import Client, AsyncClient, PaymentIntent, PaymentIntentStatus


@pytest.fixture
def sample_intent_data():
    """Sample payment intent data for testing."""
    return {
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "orderId": "test_order_001",
        "expectedAmountCents": 5000,
        "referenceAddress": "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
        "destinationAddress": "E7g2wdh9Z7a5vZkpQmdRZaVJ5z9pK2P38a6GKxeJ2Hc8",
        "status": "pending",
        "expiresAt": "2026-05-10T11:00:00Z",
    }


@pytest.fixture
def sample_terminal_data():
    """Sample terminal data for testing."""
    return {
        "id": "222e4567-e89b-12d3-a456-426614174000",
        "name": "Test Terminal",
        "isActive": True,
        "createdAt": "2026-05-01T10:00:00Z",
    }


@pytest.fixture
def mock_http_client():
    """Mock HTTP client for unit tests."""
    with patch("stendly.client.HTTPClient") as MockHTTP:
        mock_http = Mock()
        mock_http.request.return_value = Mock(
            status_code=200,
            json=Mock(return_value={}),
            raise_for_status=Mock(),
        )
        mock_http.generate_idempotency_key = lambda: str(uuid.uuid4())
        MockHTTP.return_value = mock_http
        yield mock_http


@pytest.fixture
def client(mock_http_client):
    """Create a Client instance with mocked HTTP."""
    client = stendly.Client(api_key="st_live_test123")
    yield client
    client.close()


@pytest.fixture
def async_client():
    """Create AsyncClient with mocked HTTP."""
    with patch("stendly.client.AsyncHTTPClient") as MockHTTP:
        mock = Mock()
        mock.request = Mock(
            return_value=Mock(
                status_code=200,
                json=Mock(return_value={}),
                raise_for_status=Mock(),
            )
        )
        mock.generate_idempotency_key = lambda: str(uuid.uuid4())
        MockHTTP.return_value = mock
        
        client = AsyncClient(api_key="st_live_test123")
        yield client
        # Async close called manually in tests


@pytest.fixture
def webhook_secret():
    """Test webhook secret."""
    return "whsec_test_secret_1234567890"


@pytest.fixture
def webhook_payload():
    """Sample webhook payload."""
    return {
        "event": "payment_intent.succeeded",
        "data": {
            "paymentIntentId": "123e4567-e89b-12d3-a456-426614174000",
            "orderId": "order_001",
            "amountCents": 5000,
            "expectedAmountCents": 5000,
        }
    }


def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests (requires live API key)"
    )
    config.addinivalue_line(
        "markers", "slow: marks tests as slow"
    )


def pytest_collection_modifyitems(config, items):
    """Skip integration tests by default."""
    if config.getoption("-m", None) is None:
        skip_integration = pytest.mark.skip(reason="need -m integration option")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip_integration)
