"""
Stendly Python SDK - Non-custodial payments on Solana.

Stendly is a payment gateway that enables USDC payments on Solana
with zero fees for merchants. This SDK provides a clean, type-safe
interface to the Stendly API for both synchronous and asynchronous
Python applications.

Quick Start:
    >>> from stendly import Client
    >>> 
    >>> # Initialize client
    >>> client = Client(api_key="st_live_your_api_key")
    >>> 
    >>> # Create payment intent
    >>> intent = client.intents.create(
    ...     amount_cents=4999,
    ...     order_id="order_001"
    ... )
    >>> print(f"Escrow address: {intent.reference_address}")
    >>> 
    >>> # Close when done
    >>> client.close()

Async usage:
    >>> from stendly import AsyncClient
    >>> import asyncio
    >>> 
    >>> async def main():
    ...     client = AsyncClient(api_key="st_live_...")
    ...     intent = await client.intents.create(
    ...         amount_cents=5000,
    ...         order_id="order_123"
    ...     )
    ...     await client.aclose()
    >>> asyncio.run(main())

Webhook verification:
    >>> from stendly import Client
    >>> import hashlib
    >>> import hmac
    >>> 
    >>> client = Client(api_key="st_live_...")
    >>> 
    >>> # Verify incoming webhook
    >>> signature = request.headers["X-Stendly-Signature"]
    >>> payload = request.get_data()
    >>> webhook_secret = "whsec_..."
    >>> 
    >>> try:
    ...     event = client.webhooks.construct_event(
    ...         payload=payload,
    ...         signature_header=signature,
    ...         webhook_secret=webhook_secret
    ...     )
    ...     # Process event
    ...     print(f"Event: {event.event_type}")
    ... except SignatureVerificationError:
    ...     # Invalid signature - reject
    ...     return "Invalid signature", 400

Full documentation: https://docs.stendly.com/python-sdk
"""

from __future__ import annotations

# Version
__version__ = "0.1.0"
__author__ = "Stendly Team"
__license__ = "MIT"

# Import main client classes
from .client import Client, AsyncClient

# Import exceptions
from .exceptions import (
    StendlyError,
    AuthenticationError,
    ValidationError,
    RateLimitError,
    APIConnectionError,
    SignatureVerificationError,
)

# Import models
from .models import (
    PaymentIntent,
    PaymentIntentStatus,
    Terminal,
    MerchantProfile,
    MerchantStats,
    WebhookEvent,
    WebhookData,
    DailyStats,
    CreatePaymentIntentRequest,
    UpdateWebhookRequest,
    CreateTerminalRequest,
)

# Namespace classes (for type hints and direct instantiation if needed)
from .namespaces.intents import IntentsNamespace, AsyncIntentsNamespace
from .namespaces.terminals import TerminalsNamespace, AsyncTerminalsNamespace
from .namespaces.webhooks import WebhooksNamespace, AsyncWebhooksNamespace
from .namespaces.merchant import MerchantNamespace, AsyncMerchantNamespace

# Define public API
__all__ = [
    # Version
    "__version__",
    # Clients
    "Client",
    "AsyncClient",
    # Exceptions
    "StendlyError",
    "AuthenticationError",
    "ValidationError",
    "RateLimitError",
    "APIConnectionError",
    "SignatureVerificationError",
    # Models
    "PaymentIntent",
    "PaymentIntentStatus",
    "Terminal",
    "MerchantProfile",
    "MerchantStats",
    "WebhookEvent",
    "WebhookData",
    "DailyStats",
    # Request models
    "CreatePaymentIntentRequest",
    "UpdateWebhookRequest",
    "CreateTerminalRequest",
    # Namespaces (sync)
    "IntentsNamespace",
    "TerminalsNamespace",
    "WebhooksNamespace",
    "MerchantNamespace",
    # Namespaces (async)
    "AsyncIntentsNamespace",
    "AsyncTerminalsNamespace",
    "AsyncWebhooksNamespace",
    "AsyncMerchantNamespace",
]
