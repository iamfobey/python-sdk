"""
Comprehensive test suite for Stendly Python SDK.

Tests all public APIs, error handling, webhook security, and models.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from datetime import datetime
from unittest.mock import Mock, patch

import pytest
import httpx

import stendly
from stendly import (
    Client,
    AsyncClient,
    AuthenticationError,
    ValidationError,
    RateLimitError,
    APIConnectionError,
    SignatureVerificationError,
    StendlyError,
    PaymentIntent,
    PaymentIntentStatus,
    Terminal,
    MerchantProfile,
    MerchantStats,
    WebhookEvent,
    CreatePaymentIntentRequest,
    UpdateWebhookRequest,
    CreateTerminalRequest,
)
from pydantic import ValidationError as PydanticValidationError


# ==================== Fixtures ====================

@pytest.fixture
def sample_intent_dict():
    """Sample payment intent response."""
    return {
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "orderId": "order_001",
        "expectedAmountCents": 5000,
        "referenceAddress": "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
        "destinationAddress": "E7g2wdh9Z7a5vZkpQmdRZaVJ5z9pK2P38a6GKxeJ2Hc8",
        "status": "pending",
        "expiresAt": "2026-05-10T11:00:00Z",
    }


@pytest.fixture
def sample_terminal_dict():
    """Sample terminal response."""
    return {
        "id": "222e4567-e89b-12d3-a456-426614174000",
        "name": "Main Counter",
        "isActive": True,
        "createdAt": "2026-05-01T10:00:00Z",
    }


@pytest.fixture
def mock_http_client():
    """
    Mock the internal HTTPClient class.
    Returns a Mock whose .request() returns a configurable Mock response.
    """
    with patch("stendly.client.HTTPClient") as MockHTTP:
        mock_http = Mock()
        # Default empty response (override in tests)
        mock_http.request.return_value = Mock(
            status_code=200,
            headers={},
            json=Mock(return_value={}),
            raise_for_status=Mock(),
        )
        mock_http.generate_idempotency_key = lambda: str(uuid.uuid4())
        MockHTTP.return_value = mock_http
        yield mock_http


@pytest.fixture
def mock_async_http_client():
    """Mock AsyncHTTPClient."""
    with patch("stendly.client.AsyncHTTPClient") as MockHTTP:
        mock_async = Mock()
        mock_async.request = Mock(
            return_value=Mock(
                status_code=200,
                headers={},
                json=Mock(return_value={}),
                raise_for_status=Mock(),
            )
        )
        mock_async.generate_idempotency_key = lambda: str(uuid.uuid4())
        MockHTTP.return_value = mock_async
        yield mock_async


@pytest.fixture
def client(mock_http_client):
    """Synchronous client with mocked HTTP."""
    c = stendly.Client(api_key="st_live_test123")
    yield c
    c.close()


@pytest.fixture
def async_client(mock_async_http_client):
    """Asynchronous client with mocked HTTP."""
    c = AsyncClient(api_key="st_live_test123")
    yield c
    # Note: aclose must be called manually in async tests


@pytest.fixture
def webhook_secret():
    """Test webhook secret."""
    return "whsec_test_secret_1234567890"


@pytest.fixture
def webhook_payload():
    """Sample webhook payload dict."""
    return {
        "event": "payment_intent.succeeded",
        "data": {
            "paymentIntentId": "123e4567-e89b-12d3-a456-426614174000",
            "orderId": "order_001",
            "amountCents": 5000,
            "expectedAmountCents": 5000,
        }
    }


# ==================== Test: Client Initialization ====================

class TestClientInitialization:
    """Client configuration tests."""
    
    def test_defaults(self):
        """Uses correct default settings."""
        with patch("stendly.client.HTTPClient"):
            c = Client(api_key="st_live_xxx")
            assert c.api_key == "st_live_xxx"
            assert c.environment == "mainnet"
            assert c.base_url == "https://api.stendly.com"
            assert c.timeout == 10.0
            assert c.max_retries == 2
            c.close()
    
    def test_devnet(self):
        """Devnet environment uses correct URL."""
        with patch("stendly.client.HTTPClient"):
            c = Client(api_key="st_test_xxx", environment="devnet")
            assert c.base_url == "https://devnet.api.stendly.com"
            c.close()
    
    def test_invalid_environment(self):
        """Invalid environment raises."""
        with pytest.raises(ValueError, match="Invalid environment"):
            Client(api_key="st_live_...", environment="unknown")
    
    def test_invalid_api_key(self):
        """API key must have correct prefix."""
        with pytest.raises(ValueError, match="Invalid API key format"):
            Client(api_key="invalid")
    
    def test_namespaces_exist(self):
        """All namespaces are initialized."""
        with patch("stendly.client.HTTPClient"):
            c = Client(api_key="...")
            assert hasattr(c, "intents")
            assert hasattr(c, "terminals")
            assert hasattr(c, "webhooks")
            assert hasattr(c, "merchant")
            c.close()
    
    def test_context_manager(self):
        """Client works as context manager."""
        with patch("stendly.client.HTTPClient"):
            with Client(api_key="...") as c:
                assert c._http_client is not None
            assert c._http_client is None
    
    def test_async_client_init(self):
        """AsyncClient initializes."""
        with patch("stendly.client.AsyncHTTPClient"):
            c = AsyncClient(api_key="st_live_...")
            assert c.environment == "mainnet"


# ==================== Test: Intents ====================

class TestIntentsNamespace:
    """Payment intent operations."""
    
    def test_create_success(self, client, mock_http_client, sample_intent_dict):
        """Create returns PaymentIntent."""
        mock_http_client.request.return_value = Mock(
            status_code=200,
            headers={},
            json=Mock(return_value=sample_intent_dict),
            raise_for_status=Mock(),
        )
        
        intent = client.intents.create(amount_cents=5000, order_id="order_001")
        
        assert isinstance(intent, PaymentIntent)
        assert intent.id == uuid.UUID("123e4567-e89b-12d3-a456-426614174000")
        assert intent.order_id == "order_001"
        assert intent.expected_amount_cents == 5000
        assert intent.status == PaymentIntentStatus.PENDING
    
    def test_create_with_terminal(self, client, mock_http_client, sample_intent_dict):
        """Terminal ID included in request."""
        mock_http_client.request.return_value = Mock(
            status_code=200,
            headers={},
            json=Mock(return_value=sample_intent_dict),
            raise_for_status=Mock(),
        )
        
        terminal_id = uuid.uuid4()
        client.intents.create(
            amount_cents=1000,
            order_id="term_test",
            terminal_id=str(terminal_id)
        )
        
        # Verify body includes terminalId
        call_args = mock_http_client.request.call_args
        json_body = call_args[1]["json"]
        assert "terminalId" in json_body or "terminal_id" in json_body
    
    def test_create_idempotency(self, client, mock_http_client, sample_intent_dict):
        """Idempotency key auto-generated."""
        keys = []
        original_gen = client.intents._http_client.generate_idempotency_key
        client.intents._http_client.generate_idempotency_key = lambda: (keys.append(str(uuid.uuid4())) or keys[-1])
        
        mock_http_client.request.return_value = Mock(
            status_code=200,
            headers={},
            json=Mock(return_value=sample_intent_dict),
            raise_for_status=Mock(),
        )
        
        client.intents.create(amount_cents=1000, order_id="idem")
        assert len(keys) >= 1
    
    def test_retrieve_success(self, client, mock_http_client, sample_intent_dict):
        """Retrieve intent by ID."""
        mock_http_client.request.return_value = Mock(
            status_code=200,
            headers={},
            json=Mock(return_value=sample_intent_dict),
            raise_for_status=Mock(),
        )
        
        intent_id = "123e4567-e89b-12d3-a456-426614174000"
        intent = client.intents.retrieve(intent_id)
        
        assert str(intent.id) == intent_id
        # Check URL
        call_args = mock_http_client.request.call_args
        path = call_args[0][1]
        assert intent_id in path
    
    def test_create_validation_negative(self, client):
        """Negative amount raises ValidationError."""
        with pytest.raises(ValidationError) as exc:
            client.intents.create(amount_cents=-100, order_id="bad")
        assert exc.value.status_code == 400
    
    def test_create_validation_zero(self, client):
        """Zero amount raises."""
        with pytest.raises(ValidationError):
            client.intents.create(amount_cents=0, order_id="bad")
    
    def test_create_validation_empty_order(self, client):
        """Empty order_id raises."""
        with pytest.raises(ValidationError):
            client.intents.create(amount_cents=1000, order_id="")
    
    def test_create_validation_long_order(self, client):
        """Order ID too long raises."""
        with pytest.raises(ValidationError):
            client.intents.create(amount_cents=1000, order_id="x"*101)


# ==================== Test: Terminals ====================

class TestTerminalsNamespace:
    """Terminal management."""
    
    def test_create_success(self, client, mock_http_client, sample_terminal_dict):
        mock_http_client.request.return_value = Mock(
            status_code=200,
            headers={},
            json=Mock(return_value=sample_terminal_dict),
            raise_for_status=Mock(),
        )
        
        terminal = client.terminals.create(name="Main Counter")
        assert isinstance(terminal, Terminal)
        assert terminal.name == "Main Counter"
        assert terminal.is_active is True
    
    def test_list_success(self, client, mock_http_client, sample_terminal_dict):
        mock_http_client.request.return_value = Mock(
            status_code=200,
            headers={},
            json=Mock(return_value=[sample_terminal_dict, sample_terminal_dict]),
            raise_for_status=Mock(),
        )
        
        terminals = client.terminals.list()
        assert len(terminals) == 2
        assert terminals[0].name == "Main Counter"
    
    def test_create_validation_empty_name(self, client):
        """Empty terminal name raises."""
        with pytest.raises(ValidationError):
            client.terminals.create(name="")


# ==================== Test: Merchant ====================

class TestMerchantNamespace:
    """Merchant profile and stats."""
    
    def test_get_profile(self, client, mock_http_client):
        profile_dict = {
            "id": "333e4567-e89b-12d3-a456-426614174000",
            "name": "My Store",
            "payoutAddress": "E7g2wdh9Z7a5vZkpQmdRZaVJ5z9pK2P38a6GKxeJ2Hc8",
            "webhookUrl": "https://example.com/webhook",
            "webhookSecret": "whsec_abc123",
            "rawApiKey": "st_live_xyz",
        }
        mock_http_client.request.return_value = Mock(
            status_code=200,
            headers={},
            json=Mock(return_value=profile_dict),
            raise_for_status=Mock(),
        )
        
        profile = client.merchant.get_profile()
        assert isinstance(profile, MerchantProfile)
        assert profile.name == "My Store"
    
    def test_get_stats(self, client, mock_http_client):
        stats_dict = {
            "totalVolumeCents": 500000,
            "totalTransactions": 150,
            "successfulTransactions": 148,
            "chartData": [
                {
                    "date": "2026-05-10T00:00:00Z",
                    "volumeCents": 15000,
                    "transactions": 5,
                }
            ],
        }
        mock_http_client.request.return_value = Mock(
            status_code=200,
            headers={},
            json=Mock(return_value=stats_dict),
            raise_for_status=Mock(),
        )
        
        stats = client.merchant.get_stats()
        assert isinstance(stats, MerchantStats)
        assert stats.total_volume_cents == 500000
        assert stats.success_rate == (148 / 150) * 100
        assert len(stats.chart_data) == 1


# ==================== Test: Webhooks ====================

class TestWebhookVerification:
    """Webhook signature verification (security-critical)."""
    
    def test_valid_webhook(self, client, webhook_secret, webhook_payload):
        """Valid signature passes."""
        payload_bytes = json.dumps(webhook_payload).encode("utf-8")
        ts = int(time.time())
        msg = str(ts).encode("utf-8") + payload_bytes
        sig = hmac.new(webhook_secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
        
        event = client.webhooks.construct_event(
            payload=payload_bytes,
            signature_header=f"t={ts},v1={sig}",
            webhook_secret=webhook_secret,
        )
        
        assert isinstance(event, WebhookEvent)
        assert event.event_type == "payment_intent.succeeded"
    
    def test_invalid_signature(self, client, webhook_secret, webhook_payload):
        """Wrong signature fails."""
        payload = json.dumps(webhook_payload).encode("utf-8")
        with pytest.raises(SignatureVerificationError) as exc:
            client.webhooks.construct_event(
                payload=payload,
                signature_header="t=123,v1=wrong",
                webhook_secret=webhook_secret,
            )
        assert exc.value.reason == "signature_mismatch"
    
    def test_expired_timestamp(self, client, webhook_secret, webhook_payload):
        """Old timestamp rejected."""
        payload = json.dumps(webhook_payload).encode("utf-8")
        old_ts = int(time.time()) - 400  # >5 min
        with pytest.raises(SignatureVerificationError) as exc:
            client.webhooks.construct_event(
                payload=payload,
                signature_header=f"t={old_ts},v1=abc",
                webhook_secret=webhook_secret,
                tolerance_seconds=300,
            )
        assert exc.value.reason == "timestamp_expired"
    
    def test_missing_header(self, client, webhook_secret, webhook_payload):
        """Missing signature header fails."""
        payload = json.dumps(webhook_payload).encode("utf-8")
        with pytest.raises(SignatureVerificationError) as exc:
            client.webhooks.construct_event(
                payload=payload,
                signature_header="",
                webhook_secret=webhook_secret,
            )
        assert exc.value.reason == "missing_signature"
    
    def test_malformed_header(self, client, webhook_secret, webhook_payload):
        """Malformed header fails."""
        payload = json.dumps(webhook_payload).encode("utf-8")
        with pytest.raises(SignatureVerificationError):
            client.webhooks.construct_event(
                payload=payload,
                signature_header="bad-format",
                webhook_secret=webhook_secret,
            )
    
    def test_invalid_json(self, client, webhook_secret):
        """Non-JSON payload fails."""
        payload = b"not json"
        ts = int(time.time())
        sig = hmac.new(
            webhook_secret.encode("utf-8"),
            str(ts).encode("utf-8") + payload,
            hashlib.sha256,
        ).hexdigest()
        
        with pytest.raises(SignatureVerificationError) as exc:
            client.webhooks.construct_event(
                payload=payload,
                signature_header=f"t={ts},v1={sig}",
                webhook_secret=webhook_secret,
            )
        assert "invalid_json" in str(exc.value.reason)
    
    def test_future_timestamp(self, client, webhook_secret, webhook_payload):
        """Timestamp in future fails."""
        payload = json.dumps(webhook_payload).encode("utf-8")
        future_ts = int(time.time()) + 3600
        with pytest.raises(SignatureVerificationError) as exc:
            client.webhooks.construct_event(
                payload=payload,
                signature_header=f"t={future_ts},v1=abc",
                webhook_secret=webhook_secret,
            )
        assert exc.value.reason == "future_timestamp"
    
    def test_non_utf8_payload(self, client, webhook_secret):
        """Non-UTF8 payload fails gracefully."""
        payload = b"\xff\xfe\x00\x00"
        ts = int(time.time())
        with pytest.raises(SignatureVerificationError) as exc:
            client.webhooks.construct_event(
                payload=payload,
                signature_header=f"t={ts},v1=abc",
                webhook_secret=webhook_secret,
            )
        assert "utf-8" in str(exc.value.message).lower() or "encoding" in str(exc.value.reason)


# ==================== Test: Errors ====================

class TestErrorHandling:
    """Custom exceptions."""
    
    def test_auth_error(self):
        err = AuthenticationError()
        assert err.status_code in (401, 403)
    
    def test_validation_error(self):
        err = ValidationError(message="Bad field", field="amount_cents")
        assert err.field == "amount_cents"
        assert "amount_cents" in str(err)
    
    def test_rate_limit_error(self):
        err = RateLimitError(retry_after=60)
        assert err.retry_after == 60
        assert "60" in str(err)
    
    def test_connection_error(self):
        original = httpx.TimeoutException("timeout")
        err = APIConnectionError(original_error=original)
        assert "TimeoutException" in str(err)
    
    def test_signature_error(self):
        err = SignatureVerificationError(reason="timestamp_expired")
        assert err.reason == "timestamp_expired"


# ==================== Test: Models ====================

class TestModels:
    """Pydantic model validation."""
    
    def test_payment_intent(self, sample_intent_dict):
        intent = PaymentIntent.model_validate(sample_intent_dict)
        assert intent.status == PaymentIntentStatus.PENDING
        assert intent.expected_amount_cents == 5000
    
    def test_invalid_solana_address(self):
        data = {
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "orderId": "test",
            "expectedAmountCents": 1000,
            "referenceAddress": "short",
            "destinationAddress": "E7g2wdh9Z7a5vZkpQmdRZaVJ5z9pK2P38a6GKxeJ2Hc8",
            "status": "pending",
            "expiresAt": "2026-05-10T11:00:00Z",
        }
        with pytest.raises(Exception):  # ValidationError
            PaymentIntent.model_validate(data)
    
    def test_merchant_stats(self):
        stats = MerchantStats(
            total_volume_cents=10000,
            total_transactions=10,
            successful_transactions=9,
            chart_data=[],
        )
        assert stats.success_rate == 90.0
        assert stats.average_transaction_cents == 10000 / 9
    
    def test_stats_zero(self):
        stats = MerchantStats(
            total_volume_cents=0,
            total_transactions=0,
            successful_transactions=0,
            chart_data=[],
        )
        assert stats.success_rate == 0.0
        assert stats.average_transaction_cents == 0.0
    
    def test_terminal(self):
        t = Terminal(
            id=uuid.uuid4(),
            name="Test",
            is_active=True,
            created_at=datetime.now(),
        )
        assert t.name == "Test"


# ==================== Test: Async Client ====================

class TestAsyncClient:
    """Async operations."""
    
    @pytest.mark.asyncio
    async def test_create_intent(self, mock_async_http_client):
        sample = {
            "id": str(uuid.uuid4()),
            "orderId": "async_order",
            "expectedAmountCents": 1000,
            "referenceAddress": "7xKX...",
            "destinationAddress": "E7g2...",
            "status": "pending",
            "expiresAt": "2026-05-10T11:00:00Z",
        }
        mock_async_http_client.request.return_value = Mock(
            status_code=200,
            headers={},
            json=Mock(return_value=sample),
            raise_for_status=Mock(),
        )
        
        client = AsyncClient(api_key="st_live_...")
        try:
            intent = await client.intents.create(
                amount_cents=1000,
                order_id="async_order"
            )
            assert intent.order_id == "async_order"
        finally:
            await client.aclose()
    
    @pytest.mark.asyncio
    async def test_async_context_manager(self, mock_async_http_client):
        mock_async_http_client.aclose = Mock()
        async with AsyncClient(api_key="...") as client:
            assert client._async_http_client is not None
        mock_async_http_client.aclose.assert_called_once()


# ==================== Test: Integration (Live) ====================

@pytest.mark.integration
class TestIntegration:
    """Live API integration tests (requires env vars)."""
    
    @pytest.fixture(scope="class")
    def live_client(self):
        key = os.getenv("STENDLY_TEST_KEY")
        if not key:
            pytest.skip("STENDLY_TEST_KEY not set")
        c = Client(api_key=key, environment="devnet")
        yield c
        c.close()
    
    def test_create_retrieve_flow(self, live_client):
        unique = str(uuid.uuid4())
        intent = live_client.intents.create(
            amount_cents=1000,
            order_id=f"test_{unique}",
        )
        assert intent.id is not None
        
        retrieved = live_client.intents.retrieve(intent.id)
        assert retrieved.id == intent.id
    
    def test_webhook_verify_live(self):
        secret = os.getenv("STENDLY_WEBHOOK_SECRET")
        if not secret:
            pytest.skip("STENDLY_WEBHOOK_SECRET not set")
        
        payload = {
            "event": "payment_intent.succeeded",
            "data": {
                "paymentIntentId": str(uuid.uuid4()),
                "orderId": "test_order",
                "amountCents": 5000,
                "expectedAmountCents": 5000,
            }
        }
        payload_bytes = json.dumps(payload).encode("utf-8")
        ts = int(time.time())
        sig = hmac.new(
            secret.encode("utf-8"),
            str(ts).encode("utf-8") + payload_bytes,
            hashlib.sha256,
        ).hexdigest()
        
        client = Client(api_key=os.getenv("STENDLY_TEST_KEY", ""), environment="devnet")
        try:
            event = client.webhooks.construct_event(
                payload=payload_bytes,
                signature_header=f"t={ts},v1={sig}",
                webhook_secret=secret,
            )
            assert event.event_type == "payment_intent.succeeded"
        finally:
            client.close()


# ==================== Test: Type Safety ====================

def test_type_hints_valid():
    """Module can be imported and type-checked."""
    import typing
    import inspect
    sig = inspect.signature(Client.intents.fget)
    assert sig is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
