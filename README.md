# Stendly Python SDK

Non-custodial payments on Solana — official Python SDK for [Stendly API](https://stendly.com).

[![PyPI version](https://img.shields.io/pypi/v/stendly.svg)](https://pypi.org/project/stendly/)
[![Python versions](https://img.shields.io/pypi/pyversions/stendly.svg)](https://pypi.org/project/stendly/)
[![License: MIT](https://img.shields.io/pypi/l/stendly.svg)](https://github.com/stendly/stendly-python/blob/main/LICENSE)
[![Documentation](https://img.shields.io/badge/docs-latest-blue.svg)](https://docs.stendly.com/python-sdk)

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Requirements](#requirements)
- [Quick Start](#quick-start)
- [Core Concepts](#core-concepts)
- [Authentication](#authentication)
- [Payment Intents](#payment-intents)
- [Webhooks](#webhooks)
- [Error Handling](#error-handling)
- [Retry Behavior](#retry-behavior)
- [API Reference](#api-reference)
- [Data Models](#data-models)
- [Advanced Usage](#advanced-usage)
- [Integration Examples](#integration-examples)
- [Performance & Benchmarks](#performance--benchmarks)
- [Observability](#observability)
- [Testing Strategies](#testing-strategies)
- [Production Checklist](#production-checklist)
- [Frequently Asked Questions](#frequently-asked-questions)
- [Troubleshooting](#troubleshooting)
- [CLI Tool](#cli-tool)
- [Contributing](#contributing)
- [License & Links](#license--links)

---

## Features

- **🔒 Secure**: Webhook signature verification with constant-time comparison & replay attack protection
- **⚡ Fast**: HTTP/2 support, connection pooling, automatic retries with exponential backoff
- **📱 Dual mode**: Sync (Django/Flask) and async (FastAPI/aiogram) clients
- **🎯 Type-safe**: Full type hints for PyCharm/VS Code autocomplete
- **🛡️ Robust**: Comprehensive error handling with specific exception types
- **📖 Well-documented**: Every method documented with examples
- **💪 Production-ready**: Battle-tested httpx + Pydantic stack

---

## Installation

```bash
pip install stendly
```

Or with Poetry:

```bash
poetry add stendly
```

Or with Pipenv:

```bash
pipenv install stendly
```

Or install from source:

```bash
git clone https://github.com/stendly/stendly-python.git
cd stendly-python/sdk/python
pip install -e .
```

---

## Requirements

- Python 3.9+
- httpx >= 0.27.0
- pydantic >= 2.7.0

---

## Quick Start

### 1. Get your API key

Log into your [Stendly Dashboard](https://dashboard.stendly.com) and navigate to API Keys. Copy your secret key (starts with `st_live_` for production or `st_test_` for development).

### 2. Install the SDK

```bash
pip install stendly
```

### 3. Initialize the client

**Synchronous (for Django, Flask, scripts):**

```python
from stendly import Client

# Initialize
client = Client(api_key="st_live_your_api_key_here")

# Create a payment intent
intent = client.intents.create(
    amount_cents=4999,      # $49.99
    order_id="order_001"
)

print(f"Escrow address: {intent.reference_address}")
print(f"Destination: {intent.destination_address}")
print(f"Expires at: {intent.expires_at}")

# Check payment status
retrieved = client.intents.retrieve(intent.id)
print(f"Status: {retrieved.status}")

# Close when done (or use context manager)
client.close()
```

**Asynchronous (for FastAPI, Starlette, aiogram):**

```python
import asyncio
from stendly import AsyncClient

async def main():
    async with AsyncClient(api_key="st_live_...") as client:
        # Create payment intent
        intent = await client.intents.create(
            amount_cents=4999,
            order_id="order_456"
        )
        print(f"Pay to: {intent.reference_address}")
        
        # Retrieve later
        status = await client.intents.retrieve(intent.id)
        print(f"Status: {status.status}")

asyncio.run(main())
```

---

## Core Concepts

### Payment Intents

A PaymentIntent represents a request for payment. It includes:
- `reference_address`: Escrow address where customer sends USDC
- `destination_address`: Your payout address (merchant's wallet)
- `expected_amount_cents`: Amount you expect to receive
- `status`: Current state (pending, paid, expired, cancelled)

**Workflow:**

1. **Create intent** → Get escrow address
2. **Display QR/address** → Customer scans and sends USDC
3. **Poll status** → Check if paid (or wait for webhook)
4. **Fulfill order** → Credit goods/services

```python
# Step 1: Create intent
intent = client.intents.create(
    amount_cents=999,
    order_id="premium_sub_001"
)

# Step 2: Show customer where to pay
print(f"Send {intent.expected_amount_cents/100:.2f} USDC to:")
print(intent.reference_address)

# Step 3: Check status (blocking)
import time
while True:
    intent = client.intents.retrieve(intent.id)
    if intent.status == "paid":
        print("Payment received!")
        break
    elif intent.status == "expired":
        print("Intent expired")
        break
    time.sleep(5)  # Poll every 5 seconds

# Step 4: Fulfill
grant_premium_access(intent.order_id)
```

### Idempotency

All `create` methods automatically generate an `Idempotency-Key` header (UUID v4). This prevents duplicate charges if your request times out and you retry.

```python
# Same order_id + amount → returns existing intent
intent1 = client.intents.create(amount_cents=1000, order_id="order_123")
intent2 = client.intents.create(amount_cents=1000, order_id="order_123")

assert intent1.id == intent2.id  # Same intent!
```

Custom idempotency key (optional):

```python
import uuid

custom_key = str(uuid.uuid4())
intent = client.intents.create(
    amount_cents=5000,
    order_id="order_456",
    idempotency_key=custom_key
)
```

### Webhook Verification

Always verify webhooks before processing:

```python
from flask import Flask, request, abort
from stendly import Client, SignatureVerificationError

app = Flask(__name__)
client = Client(api_key="st_live_...")  # Used for verification only
WEBHOOK_SECRET = "whsec_your_secret_here"

@app.route("/webhooks/stendly", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Stendly-Signature")
    payload = request.get_data()
    
    try:
        # Verify signature (constant-time, timestamp check)
        event = client.webhooks.construct_event(
            payload=payload,
            signature_header=signature,
            webhook_secret=WEBHOOK_SECRET
        )
    except SignatureVerificationError as e:
        app.logger.warning(f"Invalid webhook: {e}")
        abort(400, "Invalid signature")
    
    # Process verified event
    if event.event_type == "payment_intent.succeeded":
        order_id = event.data.order_id
        amount = event.data.amount_cents / 100
        fulfill_order(order_id, amount)
    
    return "", 200
```

**FastAPI example:**

```python
from fastapi import FastAPI, Request, HTTPException
import logging

logger = logging.getLogger(__name__)
app = FastAPI()
client = Client(api_key="st_live_...")

@app.post("/webhooks/stendly")
async def webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Stendly-Signature")
    
    try:
        event = client.webhooks.construct_event(
            payload=body,
            signature_header=signature,
            webhook_secret=WEBHOOK_SECRET
        )
    except SignatureVerificationError as e:
        logger.error(f"Webhook verification failed: {e}")
        raise HTTPException(400, "Invalid webhook signature")
    
    handle_event(event)
    return {"status": "ok"}
```

**Security notes:**
- Store `WEBHOOK_SECRET` in environment variable (never in code)
- Use HTTPS in production
- Reject webhooks older than 5 minutes (default)
- Constant-time comparison prevents timing attacks

---

## Authentication

### API Key Format

Stendly uses secret API keys that start with:
- `st_live_` — Production (mainnet)
- `st_test_` — Development (devnet)

**Never commit API keys to version control!**

```python
# Good: Load from environment
import os
from stendly import Client

client = Client(api_key=os.environ["STENDLY_API_KEY"])

# Bad: Hardcoded (DO NOT DO THIS)
client = Client(api_key="st_live_xxxxx")  # ❌
```

### Environment Selection

```python
# Production
client = Client(api_key="st_live_xxx", environment="mainnet")

# Development sandbox
client = Client(api_key="st_test_xxx", environment="devnet")
```

**Note:** Test keys only work with devnet. Live keys only work with mainnet.

---

## Payment Intents

### Creating a Payment Intent

```python
from stendly import Client

client = Client(api_key="st_live_...")

intent = client.intents.create(
    amount_cents=4999,           # $49.99
    order_id="PREMIUM-001"       # Your order reference
)

print(f"Escrow: {intent.reference_address}")
print(f"Payout to: {intent.destination_address}")
print(f"Expires: {intent.expires_at}")
```

### Checking Payment Status

```python
# Poll (simple)
intent = client.intents.retrieve(intent_id)
if intent.status == "paid":
    deliver_goods()

# Better: Use webhooks (recommended)
```

### Using Terminals

```python
# Create terminal for in-person payments
terminal = client.terminals.create(name="Store Counter 1")

# Create intent specific to terminal
intent = client.intents.create(
    amount_cents=1000,
    order_id="walk-in-order",
    terminal_id=terminal.id
)
```

### Payment Intent Lifecycle

```
PENDING → PAID
   ↓
EXPIRED (after 30 min)
   ↓
CANCELLED (manual)
```

**Transitions:**
- `pending` → `paid`: Payment received
- `pending` → `underpaid`: Payment received but less than expected
- `pending` → `expired`: Timeout (default 30 min)
- `pending` → `cancelled`: Manually cancelled
- Any → (terminal selected): New intent cancels other pending for same terminal

---

## Webhooks

### Verifying Signatures

**Critical:** Always verify webhook signatures before processing.

```python
from flask import Flask, request, abort
from stendly import Client, SignatureVerificationError
import os

app = Flask(__name__)
client = Client(api_key="st_live_...")  # Only for verification
WEBHOOK_SECRET = os.environ["STENDLY_WEBHOOK_SECRET"]

@app.route("/webhooks/stendly", methods=["POST"])
def webhook():
    # 1. Get headers
    signature = request.headers.get("X-Stendly-Signature")
    if not signature:
        abort(400, "Missing signature")
    
    # 2. Get raw body (NOT request.get_json())
    payload = request.get_data()
    
    # 3. Verify signature
    try:
        event = client.webhooks.construct_event(
            payload=payload,
            signature_header=signature,
            webhook_secret=WEBHOOK_SECRET
        )
    except SignatureVerificationError as e:
        app.logger.warning(f"Invalid webhook: {e}")
        abort(400, "Invalid signature")
    
    # 4. Process verified event
    handle_event(event)
    
    return "", 200

def handle_event(event):
    if event.event_type == "payment_intent.succeeded":
        order_id = event.data.order_id
        amount = event.data.amount_cents / 100
        fulfill_order(order_id, amount)
    elif event.event_type == "payment_intent.failed":
        notify_customer(event.data.order_id)
```

### Webhook Signing (How It Works)

Stendly signs webhooks using HMAC-SHA256:

```
signature = HMAC-SHA256(secret, timestamp + payload)
header = f"t={timestamp},v1={signature}"
```

**Important:**
- Use raw request body (bytes), not parsed JSON
- Do not modify payload before verification
- Check timestamp is within 5 minutes (replay attack protection)

---

## Error Handling

All SDK errors inherit from `StendlyError`. Catch specific exceptions for fine-grained control.

```python
from stendly import (
    Client,
    StendlyError,
    AuthenticationError,
    ValidationError,
    RateLimitError,
    APIConnectionError,
    SignatureVerificationError,
)

client = Client(api_key="st_live_...")

try:
    intent = client.intents.create(
        amount_cents=1000,
        order_id="test"
    )
except AuthenticationError as e:
    print(f"Auth failed: {e.message}")
    print(f"Request ID: {e.request_id}")
    # Action: Check API key, regenerate if needed
except ValidationError as e:
    print(f"Invalid input: {e.message}")
    print(f"Field: {e.field}")
    print(f"Details: {e.details}")
    # Action: Fix request parameters
except RateLimitError as e:
    print(f"Rate limited. Retry after {e.retry_after} seconds")
    # Action: Implement backoff, respect Retry-After header
except APIConnectionError as e:
    print(f"Network error: {e.message}")
    print(f"Original: {e.original_error}")
    # Action: Check internet, retry later
except StendlyError as e:
    print(f"API error {e.status_code}: {e.message}")
    print(f"Request ID: {e.request_id}")
    # Action: Contact support with request_id
```

### Exception Hierarchy

```
StendlyError (base)
├── AuthenticationError (401, 403)
├── ValidationError (400)
├── RateLimitError (429)
├── APIConnectionError (network failures)
└── SignatureVerificationError (webhook invalid)
```

---

## Retry Behavior

The SDK automatically retries transient failures:

- **Retryable status codes**: 500, 502, 503, 504
- **Retryable errors**: Timeouts, connection errors
- **Max retries**: `max_retries` (default: 2)
- **Backoff**: Exponential with jitter (1s → 2s → 4s, capped at 60s)
- **Non-retryable**: 400, 401, 403, 404 (client errors)

```python
# Disable retries
client = Client(api_key="...", max_retries=0)

# More aggressive retries
client = Client(api_key="...", max_retries=5)

# Custom timeout
client = Client(api_key="...", timeout=30.0)
```

### Custom Retry Strategies

Extend `HTTPClient` to customize retry logic:

```python
from stendly._http import HTTPClient

class SmartHTTPClient(HTTPClient):
    def request(self, method, path, **kwargs):
        # Custom logic: don't retry 500s on POST /intents (idempotency handled separately)
        if method == "POST" and "intents" in path:
            retry_on_status = (503, 504)  # Only retry on service unavailable/gateway timeout
        else:
            retry_on_status = (500, 502, 503, 504)
        
        return super().request(
            method, path,
            retry_on_status=retry_on_status,
            **kwargs
        )
```

### Exponential Backoff with Jitter

Already implemented. To adjust:

```python
client = Client(api_key="...", max_retries=5)  # More retries
# or
client._http_client._calculate_backoff = lambda attempt: 2 ** attempt  # Pure expo
```

---

## API Reference

### Client

Main entry point. Supports both sync and async.

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `api_key` | `str` | **required** | Secret API key (`st_live_*` or `st_test_*`) |
| `environment` | `str` | `"mainnet"` | API environment: `"mainnet"` or `"devnet"` |
| `timeout` | `float` | `10.0` | Request timeout in seconds |
| `max_retries` | `int` | `2` | Maximum retry attempts for transient failures |
| `http2` | `bool` | `True` | Enable HTTP/2 support |

#### Example configs

```python
# Production (mainnet)
client = Client(api_key="st_live_xxx")

# Development (devnet sandbox)
client = Client(
    api_key="st_test_xxx",
    environment="devnet"
)

# Custom timeout for slow networks
client = Client(
    api_key="st_live_xxx",
    timeout=30.0,
    max_retries=5
)
```

### Namespaces

#### `client.intents`

Payment intent operations.

**Methods:**

##### `create(amount_cents, order_id, terminal_id=None, idempotency_key=None)`

Creates a new payment intent.

- `amount_cents` (int, required): Amount in cents (e.g., 5000 = $50.00). Must be > 0.
- `order_id` (str, required): Unique order reference (max 100 chars).
- `terminal_id` (UUID | str | None, optional): Terminal UUID for POS.
- `idempotency_key` (str | None, optional): Custom idempotency key (auto-generated if omitted).

Returns: `PaymentIntent`

```python
intent = client.intents.create(
    amount_cents=4999,
    order_id="order_vip_001"
)
```

##### `retrieve(intent_id)`

Fetches a payment intent by ID.

- `intent_id` (str | UUID, required): Payment intent UUID.

Returns: `PaymentIntent`

```python
intent = client.intents.retrieve("123e4567-e89b-12d3-a456-426614174000")
print(intent.status)  # "pending", "paid", etc.
```

##### `create_async(...)` and `retrieve_async(...)`

Async versions (only available on `AsyncClient`).

---

#### `client.terminals`

POS terminal management (requires merchant verification).

**Methods:**

##### `create(name)`

Creates a new terminal.

- `name` (str, required): Display name (max 100 chars).

Returns: `Terminal`

```python
terminal = client.terminals.create(name="Main Counter")
print(terminal.id)  # Use in future intent creations
```

##### `list()`

Returns all terminals for the merchant.

Returns: `List[Terminal]`

```python
for terminal in client.terminals.list():
    print(f"{terminal.name}: {'active' if terminal.is_active else 'inactive'}")
```

##### `create_async(...)` and `list_async(...)`

Async versions.

---

#### `client.webhooks`

Webhook configuration and verification.

**Methods:**

##### `update(url)`

Updates webhook URL.

- `url` (str, required): HTTPS webhook endpoint URL.

Returns: `bool` (True on success)

```python
client.webhooks.update(
    url="https://myshop.com/webhooks/stendly"
)
```

##### `construct_event(payload, signature_header, webhook_secret, tolerance_seconds=300)`

**CRITICAL SECURITY METHOD**: Verifies webhook signature.

- `payload` (bytes | str, required): Raw request body.
- `signature_header` (str, required): Value of `X-Stendly-Signature` header.
- `webhook_secret` (str, required): Your webhook secret (starts with `whsec_`).
- `tolerance_seconds` (int, optional): Max age in seconds (default 300 = 5 minutes).

Returns: `WebhookEvent`

Raises: `SignatureVerificationError` if verification fails.

```python
# Flask/Django/FastAPI webhook handler
event = client.webhooks.construct_event(
    payload=request.get_data(),
    signature_header=request.headers["X-Stendly-Signature"],
    webhook_secret=WEBHOOK_SECRET
)

# Process verified event
if event.event_type == "payment_intent.succeeded":
    order_id = event.data.order_id
    fulfill(order_id)
```

##### `construct_event_async(...)` (async only)

Async version of signature verification.

---

#### `client.merchant`

Merchant account data.

**Methods:**

##### `get_profile()`

Retrieves merchant profile.

Returns: `MerchantProfile`

```python
profile = client.merchant.get_profile()
print(profile.name)
print(profile.payout_address)
print(profile.webhook_url)  # May be None
```

**⚠️ Important:** `raw_api_key` is ONLY returned once when first generated. Save it immediately!

##### `get_stats()`

Returns 30-day statistics.

Returns: `MerchantStats`

```python
stats = client.merchant.get_stats()
total_usd = stats.total_volume_cents / 100
success_rate = stats.success_rate

print(f"Volume: ${total_usd:,.2f}")
print(f"Transactions: {stats.total_transactions}")
print(f"Success rate: {success_rate:.1f}%")

# Daily breakdown
for day in stats.chart_data:
    print(f"{day.date}: ${day.volume_cents/100:.2f}")
```

##### Async variants: `get_profile_async()`, `get_stats_async()`

---

### Data Models

All response models are Pydantic classes with full validation.

#### `PaymentIntent`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `UUID` | Unique intent ID |
| `order_id` | `str` | Your order reference |
| `expected_amount_cents` | `int` | Expected amount (cents) |
| `reference_address` | `str` | Escrow Solana address |
| `destination_address` | `str` | Merchant payout address |
| `status` | `PaymentIntentStatus` | `"pending"`, `"paid"`, `"expired"`, `"cancelled"`, `"underpaid"` |
| `expires_at` | `datetime` | Expiration timestamp |

#### `PaymentIntentStatus` (Enum)

```python
class PaymentIntentStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    UNDERPAID = "underpaid"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
```

#### `Terminal`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `UUID` | Terminal ID |
| `name` | `str` | Display name |
| `is_active` | `bool` | Active status |
| `created_at` | `datetime` | Creation timestamp |

#### `MerchantProfile`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `UUID` | Merchant ID |
| `name` | `str` | Business name |
| `payout_address` | `str` | USDC receiving address |
| `webhook_url` | `str | None` | Configured webhook URL |
| `webhook_secret` | `str | None` | Secret for webhook verification |
| `raw_api_key` | `str | None` | Full API key (ONLY shown once) |

#### `MerchantStats`

| Field | Type | Description |
|-------|------|-------------|
| `total_volume_cents` | `int` | 30-day total volume |
| `total_transactions` | `int` | Total txn count |
| `successful_transactions` | `int` | Paid txn count |
| `chart_data` | `List[DailyStats]` | Daily breakdown |
| `success_rate` | `float` (property) | Calculated % |
| `average_transaction_cents` | `float` (property) | Avg txn amount |

#### `DailyStats`

| Field | Type | Description |
|-------|------|-------------|
| `date` | `datetime` | Date |
| `volume_cents` | `int` | Daily volume |
| `transactions` | `int` | Daily count |

#### `WebhookEvent`

| Field | Type | Description |
|-------|------|-------------|
| `event_type` | `str` | Event name (e.g., `"payment_intent.succeeded"`) |
| `data` | `WebhookData` | Event payload |

#### `WebhookData`

| Field | Type | Description |
|-------|------|-------------|
| `payment_intent_id` | `UUID` | Intent ID |
| `order_id` | `str` | Order reference |
| `amount_cents` | `int` | Actual amount |
| `expected_amount_cents` | `int` | Expected amount |
| `tx_signature` | `str | None` | Solana tx signature |

---

## Advanced Usage

### Custom HTTP Client Configuration

#### Configuring Proxy

```python
import httpx
from stendly import Client

# Create custom httpx client with proxy
http_client = httpx.Client(
    proxies="http://proxy.example.com:8080",
    verify=False,  # For self-signed certs (not recommended for prod)
)

# Use with Stendly (advanced - requires modifying client internals)
# Currently, proxy via environment variables is easier:
# export HTTP_PROXY="http://proxy:8080"
```

#### Custom Transport

```python
# For custom TLS configuration
transport = httpx.HTTPTransport(retries=3)
client = Client(
    api_key="...",
    # Pass custom transport (requires extending _http.py)
)
```

**Currently not exposed directly** — open an issue if you need this.

### Middleware / Request Hooks

Add logging, metrics, tracing:

```python
from stendly import Client

original_request = client._http_client.request

def logged_request(method, path, **kwargs):
    import time
    start = time.time()
    
    response = original_request(method, path, **kwargs)
    
    duration = time.time() - start
    logger.info(
        f"API call: {method} {path} "
        f"status={response.status_code} time={duration:.3f}s"
    )
    
    return response

client._http_client.request = logged_request
```

**For production:** Use APM integration (Datadog, New Relic).

### Batch Operations

Process multiple intents efficiently:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def create_bulk_intents(orders, client=None):
    """Create many intents concurrently."""
    own_client = False
    if client is None:
        client = Client(api_key=os.getenv("STENDLY_API_KEY"))
        own_client = True
    
    try:
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_order = {
                executor.submit(
                    client.intents.create,
                    amount_cents=order.amount,
                    order_id=order.id
                ): order
                for order in orders
            }
            
            results = {}
            for future in as_completed(future_to_order):
                order = future_to_order[future]
                try:
                    intent = future.result()
                    results[order.id] = intent
                except Exception as e:
                    logger.error(f"Failed for {order.id}: {e}")
            
            return results
    finally:
        if own_client:
            client.close()

# Usage
intents = create_bulk_intents(orders)
```

Async version:

```python
async def create_bulk_intents_async(orders):
    client = AsyncClient(api_key="...")
    try:
        tasks = [
            client.intents.create(amount_cents=o.amount, order_id=o.id)
            for o in orders
        ]
        return await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        await client.aclose()
```

### Custom Exception Handling Middleware

Global error handler for Django/FastAPI:

```python
from stendly import StendlyError

class StendlyErrorMiddleware:
    def __init__(self, app):
        self.app = app
    
    def __call__(self, environ, start_response):
        try:
            return self.app(environ, start_response)
        except StendlyError as e:
            # Log with request ID
            logger.error(f"Stendly error: {e} (request_id={e.request_id})")
            # Return JSON response
            start_response('500 INTERNAL SERVER ERROR', [
                ('Content-Type', 'application/json')
            ])
            return [json.dumps({"error": str(e)}).encode()]
```

### Connection Pooling

The SDK uses httpx with connection pooling by default:

```python
# High-throughput scenario
client = Client(
    api_key="st_live_...",
    http2=True,          # HTTP/2 multiplexing
    max_retries=5,       # Aggressive retry
    timeout=30.0,       # Longer timeout
)

# Reuse client for many requests
for order in orders:
    intent = client.intents.create(...)
```

### Idempotency (Advanced)

Avoid duplicate charges with idempotency keys:

```python
# Scenario: API call times out, should you retry?
# YES - use same order_id (client auto-generates Idempotency-Key)

# First attempt (times out)
# Second attempt (gets cached result - NO duplicate!)
intent = client.intents.create(
    amount_cents=1000,
    order_id="order_123"  # Same order_id = same intent
)

# Custom key (if you need explicit control)
import uuid
key = str(uuid.uuid4())
intent = client.intents.create(
    amount_cents=1000,
    order_id="order_123",
    idempotency_key=key
)
```

### Rate Limiting

Respect rate limits:

- Default: 2 retries on 5xx errors
- Backoff: exponential (1s → 2s → 4s, max 60s)
- For 429: SDK uses `Retry-After` header if provided

```python
# Disable retries for real-time systems
client = Client(api_key="...", max_retries=0)

# Increase retries for unreliable networks
client = Client(api_key="...", max_retries=5)
```

### Thread Safety

Client is thread-safe. Share across threads:

```python
from concurrent.futures import ThreadPoolExecutor

client = Client(api_key="...")

def process_order(order):
    intent = client.intents.create(
        amount_cents=order.amount,
        order_id=order.id
    )
    return intent.id

with ThreadPoolExecutor(max_workers=10) as pool:
    results = list(pool.map(process_order, orders))
```

### Async Best Practices

**Connection Pool in Async:**

Async client uses a shared connection pool:

```python
# Good: Single client, many concurrent requests
client = AsyncClient(api_key="...")

async def process_many():
    semaphore = asyncio.Semaphore(50)  # Limit concurrency
    
    async def limited_create(order):
        async with semaphore:
            return await client.intents.create(
                amount_cents=order.amount,
                order_id=order.id
            )
    
    tasks = [limited_create(o) for o in orders]
    results = await asyncio.gather(*tasks, return_exceptions=True)

asyncio.run(process_many())
```

**Proper Cleanup:**

```python
# Always close async client
async def main():
    client = AsyncClient(api_key="...")
    try:
        await client.intents.create(...)
    finally:
        await client.aclose()

# Or use context manager
async with AsyncClient(api_key="...") as client:
    await client.intents.create(...)
```

### Logging

SDK uses Python's standard logging. Configure to see debug logs:

```python
import logging

# Enable SDK logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("stendly")
logger.setLevel(logging.DEBUG)

# Now SDK will log request/response info
# DEBUG:stendly:Request: POST /api/merchants/intents
# DEBUG:stendly:Response: 200 OK
client = Client(api_key="...")
```

### Environment Variables

Instead of hardcoding API keys:

```python
import os
from stendly import Client

client = Client(api_key=os.environ["STENDLY_API_KEY"])
```

Or use `python-dotenv`:

```bash
# .env file
STENDLY_API_KEY=st_live_xxxxxxxxxxxxxxxx
```

```python
from dotenv import load_dotenv
load_dotenv()

from stendly import Client
client = Client(api_key=os.getenv("STENDLY_API_KEY"))
```

### Webhook Payload Optimization

For high-throughput, validate basic structure first:

```python
def webhook_handler(request):
    # Quick validation
    if not request.headers.get("X-Stendly-Signature"):
        return "Missing signature", 400
    
    # Only verify signature for high-value payments
    payload = request.get_json()
    if payload.get("data", {}).get("amountCents", 0) > 100000:  # >$1000
        event = client.webhooks.construct_event(...)
    else:
        # Trust basic validation for small amounts (your business choice)
        event = WebhookEvent.model_validate(payload)
    
    process(event)
```

### Timezone Handling

`expires_at` is always UTC:

```python
from datetime import datetime, timezone

intent = client.intents.create(...)
# Always UTC
assert intent.expires_at.tzinfo == timezone.utc

# Convert to local timezone for display
local_time = intent.expires_at.astimezone()
print(f"Expires at {local_time}")
```

---

## Integration Examples

### Flask Webhook Receiver

Basic Flask app that receives Stendly webhooks and verifies signatures.

```python
# flask_app.py
from flask import Flask, request, abort
from stendly import Client, SignatureVerificationError
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize
app = Flask(__name__)
client = Client(api_key=os.getenv("STENDLY_API_KEY"))
WEBHOOK_SECRET = os.getenv("STENDLY_WEBHOOK_SECRET")

@app.route("/webhooks/stendly", methods=["POST"])
def stendly_webhook():
    # Get headers
    signature = request.headers.get("X-Stendly-Signature")
    if not signature:
        logger.warning("Missing signature header")
        abort(400, "Missing X-Stendly-Signature header")
    
    # Get raw payload
    payload = request.get_data()
    
    # Verify signature
    try:
        event = client.webhooks.construct_event(
            payload=payload,
            signature_header=signature,
            webhook_secret=WEBHOOK_SECRET
        )
    except SignatureVerificationError as e:
        logger.error(f"Signature verification failed: {e}")
        abort(400, "Invalid webhook signature")
    
    # Process event
    logger.info(f"Received event: {event.event_type}")
    handle_webhook_event(event)
    
    return "", 200

def handle_webhook_event(event):
    """Process verified webhook event."""
    from your_app import fulfill_order, notify_customer
    
    if event.event_type == "payment_intent.succeeded":
        order_id = event.data.order_id
        amount = event.data.amount_cents / 100
        logger.info(f"Payment succeeded: order={order_id}, amount=${amount:.2f}")
        fulfill_order(order_id)
    
    elif event.event_type == "payment_intent.failed":
        order_id = event.data.order_id
        logger.warning(f"Payment failed: {order_id}")
        notify_customer(order_id, status="failed")
    
    elif event.event_type == "payment_intent.expired":
        order_id = event.data.order_id
        logger.info(f"Payment expired: {order_id}")
        notify_customer(order_id, status="expired")

if __name__ == "__main__":
    app.run(port=5000, debug=True)
```

**Run:**

```bash
export STENDLY_API_KEY=st_live_...
export STENDLY_WEBHOOK_SECRET=whsec_...
python flask_app.py
```

### FastAPI Create Intent

FastAPI endpoint for creating payment intents.

```python
# fastapi_app.py
from fastapi import FastAPI, HTTPException, Depends, status
from pydantic import BaseModel
from stendly import AsyncClient, StendlyError
import os
from typing import Optional

app = FastAPI(title="Stendly Example API")
client = AsyncClient(api_key=os.getenv("STENDLY_API_KEY"))

class CreateIntentRequest(BaseModel):
    amount_cents: int
    order_id: str
    terminal_id: Optional[str] = None

@app.post("/api/intents")
async def create_intent(request: CreateIntentRequest):
    """
    Create a new payment intent.
    
    Returns escrow address for payment.
    """
    try:
        intent = await client.intents.create(
            amount_cents=request.amount_cents,
            order_id=request.order_id,
            terminal_id=request.terminal_id,
        )
        return {
            "id": str(intent.id),
            "reference_address": intent.reference_address,
            "destination_address": intent.destination_address,
            "expires_at": intent.expires_at.isoformat(),
            "status": intent.status,
        }
    except StendlyError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "error": str(e),
                "type": type(e).__name__,
                "request_id": e.request_id,
            }
        )

@app.get("/api/intents/{intent_id}")
async def get_intent(intent_id: str):
    """Retrieve payment intent by ID."""
    try:
        intent = await client.intents.retrieve(intent_id)
        return {
            "id": str(intent.id),
            "order_id": intent.order_id,
            "expected_amount_cents": intent.expected_amount_cents,
            "reference_address": intent.reference_address,
            "status": intent.status,
            "expires_at": intent.expires_at.isoformat(),
        }
    except StendlyError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    await client.aclose()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

**Run:**

```bash
uvicorn fastapi_app:app --reload
# POST http://localhost:8000/api/intents
```

### Telegram Bot (aiogram)

Complete Telegram bot that accepts payments via Stendly.

```python
# telegram_bot.py
import os
import asyncio
import time
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from stendly import AsyncClient

# Initialize
bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))
dp = Dispatcher()
stendly_client = AsyncClient(api_key=os.getenv("STENDLY_API_KEY"))

# User session storage (use Redis in production)
user_sessions = {}

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Welcome message."""
    await message.answer(
        "Welcome to Stendly Payment Bot!\n\n"
        "Commands:\n"
        "/pay <amount> - Create payment\n"
        "/status <intent_id> - Check payment status\n"
        "/help - Show help"
    )

@dp.message(Command("pay"))
async def cmd_pay(message: types.Message):
    """
    Create payment intent.
    Usage: /pay 5.50
    """
    try:
        # Parse amount
        parts = message.text.split()
        if len(parts) < 2:
            await message.answer("Usage: /pay <amount> (e.g., /pay 5.50)")
            return
        
        amount_usd = float(parts[1])
        amount_cents = int(amount_usd * 100)
        
        if amount_cents <= 0:
            await message.answer("Amount must be positive")
            return
        
        # Create intent
        user_id = message.from_user.id
        order_id = f"tg_{user_id}_{int(time.time())}"
        
        intent = await stendly_client.intents.create(
            amount_cents=amount_cents,
            order_id=order_id
        )
        
        # Store in session
        user_sessions[user_id] = {
            "intent_id": str(intent.id),
            "order_id": order_id,
            "amount_usd": amount_usd,
        }
        
        # Send payment instructions
        await message.answer(
            f"💰 Payment Request\n\n"
            f"Amount: ${amount_usd:.2f} USDC (Solana)\n\n"
            f"Send to this address:\n"
            f"`{intent.reference_address}`\n\n"
            f"⏱ Expires: {intent.expires_at.strftime('%H:%M')} UTC\n"
            f"Order ID: {order_id}",
            parse_mode="Markdown"
        )
        
    except ValueError:
        await message.answer("Invalid amount. Example: /pay 5.50")
    except StendlyError as e:
        await message.answer(f"Error: {e}")

@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    """Check payment status."""
    parts = message.text.split()
    if len(parts) < 2:
        # Check user's current intent
        session = user_sessions.get(message.from_user.id)
        if not session:
            await message.answer("No active payment. Use /pay first.")
            return
        intent_id = session["intent_id"]
    else:
        intent_id = parts[1]
    
    try:
        intent = await stendly_client.intents.retrieve(intent_id)
        
        status_emoji = {
            "pending": "⏳",
            "paid": "✅",
            "expired": "⏰",
            "cancelled": "❌",
            "underpaid": "⚠️",
        }.get(intent.status, "❓")
        
        await message.answer(
            f"{status_emoji} Status: {intent.status.upper()}\n"
            f"Amount: ${intent.expected_amount_cents / 100:.2f}\n"
            f"Order: {intent.order_id}\n"
            f"Expires: {intent.expires_at.strftime('%Y-%m-%d %H:%M UTC')}"
        )
        
        if intent.status == "paid":
            # Clear session
            user_sessions.pop(message.from_user.id, None)
            await message.answer("✅ Payment received! Your order is being processed.")
            
    except StendlyError as e:
        await message.answer(f"Error checking status: {e}")

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    """Show help."""
    help_text = """
**Stendly Payment Bot**

Available commands:
• /pay <amount> — Create payment (e.g., /pay 9.99)
• /status [intent_id] — Check payment status
• /help — Show this help

**How to pay:**
1. Use /pay to create intent
2. Copy the Solana address
3. Send USDC (Solana) to that address
4. Wait ~30 sec for confirmation
5. /status to verify

**Need USDC?**
Buy on Bybit, OKX, or use Jupiter swap.

Questions? @stendly_support
"""
    await message.answer(help_text, parse_mode="Markdown")

async def main():
    """Start bot."""
    print("Bot starting...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped")
    finally:
        asyncio.run(stendly_client.aclose())
```

**Run:**

```bash
pip install aiogram
export TELEGRAM_BOT_TOKEN=xxx
export STENDLY_API_KEY=st_live_...
python telegram_bot.py
```

### Celery Payment Checker

Background worker that checks payment status (alternative to webhooks).

```python
# tasks.py
from celery import Celery
from stendly import Client
import os
import time

celery = Celery(
    "stendly_tasks",
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
)

# Shared client (create once, reuse)
_client = None

def get_client():
    global _client
    if _client is None:
        _client = Client(api_key=os.getenv("STENDLY_API_KEY"))
    return _client

@celery.task(bind=True, max_retries=3)
def check_payment_status(self, intent_id):
    """
    Check payment intent status.
    
    Retry with exponential backoff on errors.
    Use webhooks instead when possible (more efficient).
    """
    client = get_client()
    
    try:
        intent = client.intents.retrieve(intent_id)
        
        if intent.status == "paid":
            # Payment received
            from orders import fulfill
            fulfill(intent.order_id, intent.expected_amount_cents)
            return {"status": "paid", "order_id": intent.order_id}
        
        elif intent.status in ["expired", "cancelled"]:
            # Failed
            from orders import cancel
            cancel(intent.order_id)
            return {"status": intent.status, "order_id": intent.order_id}
        
        else:
            # Still pending - retry
            raise self.retry(
                exc=Exception("Payment still pending"),
                countdown=min(2 ** self.request.retries, 60)
            )
    
    except StendlyError as e:
        if isinstance(e, (AuthenticationError, ValidationError)):
            # Don't retry - bad request
            raise
        else:
            # Network error - retry
            raise self.retry(exc=e, countdown=10)

# Schedule periodic check for old pending intents
@celery.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # Check all pending intents older than 5 min every 5 minutes
    sender.add_periodic_task(300.0, check_old_pending_intents.s())

@celery.task
def check_old_pending_intents():
    """Find old pending intents and check them."""
    from orders import get_old_pending_intents
    
    intents = get_old_pending_intents(minutes=5)
    for intent in intents:
        check_payment_status.delay(intent.id)
```

**Run Celery:**

```bash
celery -A tasks worker --loglevel=info
```

### Django Integration

Full Django + Stendly integration.

```python
# myproject/stendly.py
import os
from stendly import Client

STENDLY_CLIENT = Client(
    api_key=os.getenv("STENDLY_API_KEY"),
    environment=os.getenv("STENDLY_ENV", "mainnet")
)
```

```python
# myapp/views.py
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from stendly import SignatureVerificationError, StendlyError
from .stendly import STENDLY_CLIENT
import json
import logging

logger = logging.getLogger(__name__)

@csrf_exempt
@require_POST
def webhook(request):
    """Stendly webhook endpoint."""
    signature = request.headers.get("X-Stendly-Signature")
    if not signature:
        return HttpResponseBadRequest("Missing signature")
    
    try:
        event = STENDLY_CLIENT.webhooks.construct_event(
            payload=request.body,
            signature_header=signature,
            webhook_secret=os.getenv("STENDLY_WEBHOOK_SECRET"),
        )
    except SignatureVerificationError as e:
        logger.warning(f"Invalid webhook: {e}")
        return HttpResponseBadRequest("Invalid signature")
    
    # Process event
    process_webhook_event(event)
    
    return JsonResponse({"status": "ok"})

def process_webhook_event(event):
    """Handle webhook event."""
    from orders.models import Order
    
    if event.event_type == "payment_intent.succeeded":
        order_id = event.data.order_id
        amount = event.data.amount_cents / 100
        
        try:
            order = Order.objects.get(id=order_id)
            order.mark_paid(amount_cents=event.data.amount_cents)
            order.send_confirmation_email()
        except Order.DoesNotExist:
            logger.error(f"Order {order_id} not found")
```

### AWS Lambda Function

Serverless function for payment processing.

```python
# lambda_function.py
import json
import os
from stendly import Client, SignatureVerificationError

# Initialize client outside handler (connection reuse!)
client = Client(api_key=os.getenv("STENDLY_API_KEY"))
WEBHOOK_SECRET = os.getenv("STENDLY_WEBHOOK_SECRET")

def lambda_handler(event, context):
    """
    AWS Lambda handler for Stendly webhook.
    
    Deploy via:
    - AWS Console
    - Serverless Framework
    - AWS SAM
    """
    # API Gateway proxy integration
    headers = event.get("headers", {})
    body = event.get("body", "")
    
    if event.get("isBase64Encoded"):
        import base64
        body = base64.b64decode(body)
    
    signature = headers.get("x-stendly-signature") or headers.get("X-Stendly-Signature")
    
    if not signature:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Missing signature"})
        }
    
    try:
        webhook_event = client.webhooks.construct_event(
            payload=body,
            signature_header=signature,
            webhook_secret=WEBHOOK_SECRET,
        )
    except SignatureVerificationError as e:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": str(e)}),
        }
    
    # Process event
    process_event(webhook_event)
    
    return {
        "statusCode": 200,
        "body": json.dumps({"status": "ok"}),
    }

def process_event(event):
    """Handle verified webhook."""
    from your_app import fulfill
    
    if event.event_type == "payment_intent.succeeded":
        fulfill(event.data.order_id)
```

**serverless.yml (Serverless Framework):**

```yaml
service: stendly-webhook

provider:
  name: aws
  runtime: python3.11
  environment:
    STENDLY_API_KEY: ${env:STENDLY_API_KEY}
    STENDLY_WEBHOOK_SECRET: ${env:STENDLY_WEBHOOK_SECRET}

functions:
  webhook:
    handler: lambda_function.lambda_handler
    events:
      - http:
          path: /webhooks/stendly
          method: post
```

---

## Performance & Benchmarks

### Benchmarks

Typical latencies (mainnet, API response time):

| Operation | P50 | P95 | P99 |
|-----------|-----|-----|-----|
| Create intent | 120ms | 250ms | 400ms |
| Retrieve intent | 80ms | 150ms | 300ms |
| Webhook verify | 5ms | 10ms | 20ms |

*Measured from US-East to api.stendly.com*

### Optimizations

1. **Reuse client instances** (connection pooling)
2. **Batch operations** where possible
3. **Use webhooks** instead of polling
4. **Enable HTTP/2** (default) for multiplexing
5. **Set appropriate timeout** (not too low)

```python
# Good: Single client reused
client = Client(api_key="...")
for order in orders:
    client.intents.create(...)  # Reuses connection
client.close()

# Bad: New client per request
for order in orders:
    temp_client = Client(api_key="...")  # New connection pool
    temp_client.intents.create(...)
    temp_client.close()
```

### Async Concurrency

```python
import asyncio

async def process_orders(orders):
    client = AsyncClient(api_key="...")
    try:
        tasks = [
            client.intents.create(amount_cents=o.amount, order_id=o.id)
            for o in orders
        ]
        intents = await asyncio.gather(*tasks, return_exceptions=True)
        return intents
    finally:
        await client.aclose()

# Process 100 orders concurrently
results = asyncio.run(process_orders(orders))
```

---

## Observability

### Adding Tracing Headers

```python
from stendly import Client

client = Client(api_key="...")

# Pass custom headers
response = client.intents._http_client.request(
    method="POST",
    path="/api/merchants/intents",
    json={"amount_cents": 1000, "order_id": "test"},
    headers={
        "X-Request-ID": str(uuid.uuid4()),
        "X-User-ID": "user_123",
    }
)
```

### Metrics Collection

```python
from prometheus_client import Counter, Histogram

REQUESTS = Counter('stendly_requests_total', 'Total requests', ['method', 'endpoint'])
LATENCY = Histogram('stendly_request_latency_seconds', 'Request latency', ['method', 'endpoint'])

# Wrap client
original_request = client.intents._http_client.request

def instrumented_request(method, path, **kwargs):
    with LATENCY.labels(method=method, endpoint=path).time():
        response = original_request(method, path, **kwargs)
        REQUESTS.labels(method=method, endpoint=path).inc()
        return response

client.intents._http_client.request = instrumented_request
```

---

## Testing Strategies

### Mocking HTTP Responses

```python
from unittest.mock import Mock, patch
import pytest

def test_create_intent():
    with patch("stendly.client.HTTPClient._http_client") as mock_http:
        # Arrange: Setup mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "orderId": "test",
            "expectedAmountCents": 1000,
            "referenceAddress": "7xKX...",
            "destinationAddress": "E7g2...",
            "status": "pending",
            "expiresAt": "2026-05-10T11:00:00Z",
        }
        mock_response.raise_for_status = Mock()
        mock_http.request.return_value = mock_response
        
        # Act
        client = Client(api_key="test")
        intent = client.intents.create(amount_cents=1000, order_id="test")
        
        # Assert
        assert intent.status == "pending"
        assert intent.order_id == "test"
        client.close()
```

### Using VCR.py for HTTP Recording

```python
import vcr

my_vcr = vcr.VCR(
    cassette_library_dir='tests/cassettes',
    filter_headers=['Authorization'],
    match_on=['method', 'uri', 'body'],
)

@my_vcr.use_cassette('create_intent.yaml')
def test_intent_with_vcr():
    client = Client(api_key="st_live_...")
    intent = client.intents.create(amount_cents=1000, order_id="test")
    assert intent.id is not None
    client.close()
```

### Unit Tests

```python
from unittest.mock import Mock, patch
from stendly import Client

def test_create_intent():
    client = Client(api_key="st_test_...")
    
    # Mock HTTP response
    mock_response = {
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "order_id": "test",
        "expected_amount_cents": 1000,
        "reference_address": "7xKX...",
        "destination_address": "E7g2...",
        "status": "pending",
        "expires_at": "2026-05-10T11:00:00Z"
    }
    
    with patch.object(client._http_client, 'request') as mock_req:
        mock_req.return_value.json.return_value = mock_response
        mock_req.return_value.status_code = 200
        mock_req.return_value.raise_for_status = Mock()
        
        intent = client.intents.create(amount_cents=1000, order_id="test")
        assert intent.id == "123e4567-e89b-12d3-a456-426614174000"
```

### Integration Tests (Devnet)

```python
import pytest
from stendly import Client

@pytest.fixture
def client():
    return Client(
        api_key=os.getenv("STENDLY_TEST_KEY"),
        environment="devnet"
    )

def test_create_and_retrieve_intent(client):
    # Create
    intent = client.intents.create(
        amount_cents=1000,
        order_id=f"test_{uuid.uuid4()}"
    )
    assert intent.id is not None
    
    # Retrieve
    retrieved = client.intents.retrieve(intent.id)
    assert retrieved.id == intent.id
    assert retrieved.status in ["pending", "paid"]
```

---

## Production Checklist

- [ ] API key stored in environment variable or secret manager
- [ ] Webhook secret stored securely
- [ ] Webhook endpoint uses HTTPS
- [ ] All webhooks verified (no exceptions)
- [ ] Client reused (not created per-request)
- [ ] Proper error handling (catch `StendlyError`)
- [ ] Retry logic configured (`max_retries` ≥ 2)
- [ ] Logging configured (structured logs)
- [ ] Monitoring/alerting for errors
- [ ] Timeout set appropriately (10-30s)
- [ ] Connection pooling enabled (HTTP/2)
- [ ] `client.close()` called on shutdown
- [ ] Tests run in CI/CD pipeline

---

## Frequently Asked Questions

**Q: Should I sync or async client?**

A: Use sync for Django/Flask/scripts. Use async for FastAPI/aiogram/asyncio apps.

**Q: What's the maximum retry count?**

A: Default is 2. Max recommended: 5. Set to 0 for no retries.

**Q: How long do intents live?**

A: 30 minutes by default. After that, they expire.

**Q: Can I cancel an intent?**

A: Not via API yet. Contact support or let it expire.

**Q: Do webhooks guarantee delivery?**

A: No — if your endpoint returns non-2xx, Stendly retries with backoff. Ensure idempotent handling.

**Q: What's the rate limit?**

A: Default varies by endpoint (see docs). Contact support for increases.

**Q: Can I use the SDK in AWS Lambda?**

A: Yes! Reuse client across invocations (global scope) for connection pooling.

**Q: Is the SDK thread-safe?**

A: Yes. Both `Client` and `AsyncClient` are thread-safe for their respective paradigms.

---

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| `AuthenticationError` | Check API key format; regenerate if leaked |
| `ValidationError` | Validate input before API call |
| `RateLimitError` | Implement backoff; respect `Retry-After` header |
| `APIConnectionError` | Check internet; increase timeout; retry |
| Webhook verification fails | Verify webhook secret; use raw payload; check clock sync |

### "Authentication failed"

- Check API key format: must start with `st_live_` (mainnet) or `st_test_` (devnet)
- Ensure no extra spaces or newlines in key
- Verify key is active in dashboard

### "Rate limit exceeded"

- Implement exponential backoff
- Respect `Retry-After` header from `RateLimitError.retry_after`
- Batch requests or reduce frequency

### "Invalid webhook signature"

- Verify webhook secret matches the one in dashboard
- Ensure payload is raw (not re-serialized)
- Check timestamp is within 5 minutes
- Use HTTPS in production

### "Connection errors"

- Check internet connection
- Verify firewall/proxy settings
- Increase timeout: `Client(timeout=30.0)`
- Reduce max_retries if too many retries

### "Invalid Solana address"

- Address must be 32-44 base58 characters
- No `0x` prefix (that's Ethereum)
- Double-check address copy-paste

### Debug Logging

Enable debug logging to see request/response details:

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("stendly")
logger.setLevel(logging.DEBUG)

# Now you'll see:
# DEBUG:stendly:Request: POST /api/merchants/intents
# DEBUG:stendly:Response: 200 OK
```

### Getting Help

1. Check this documentation
2. Search [GitHub Issues](https://github.com/stendly/stendly-python/issues)
3. Open a new issue with:
   - SDK version
   - Python version
   - Error message + stack trace
   - Code snippet

---

## Best Practices

### 1. Always close the client

```python
# Good
with Client(api_key="...") as client:
    intent = client.intents.create(...)

# Also good
client = Client(api_key="...")
try:
    intent = client.intents.create(...)
finally:
    client.close()
```

### 2. Store API keys securely

```python
# BAD - never commit API keys
client = Client(api_key="st_live_xxxxxxxxx")

# GOOD - environment variable
import os
client = Client(api_key=os.environ["STENDLY_API_KEY"])

# BEST - use a secret manager (AWS Secrets Manager, HashiCorp Vault)
```

### 3. Verify every webhook

```python
# NEVER do this in production
event = request.get_json()  # UNSAFE!

# ALWAYS verify signature
try:
    event = client.webhooks.construct_event(
        payload=request.get_data(),
        signature_header=request.headers["X-Stendly-Signature"],
        webhook_secret=WEBHOOK_SECRET
    )
except SignatureVerificationError:
    abort(400)
```

### 4. Handle idempotency

```python
# Create intent once, store ID
intent_id = create_intent_and_store_in_db()

# If retrying, use same order_id
intent = client.intents.create(
    amount_cents=1000,
    order_id="order_123"
)  # Returns same intent
```

### 5. Poll intelligently

```python
# BAD - tight loop (rate limits!)
while True:
    intent = client.intents.retrieve(id)
    if intent.status != "pending":
        break
    time.sleep(0.1)  # 10req/s → rate limited

# GOOD - exponential backoff
delay = 2
for _ in range(10):
    intent = client.intents.retrieve(id)
    if intent.status != "pending":
        break
    time.sleep(delay)
    delay = min(delay * 1.5, 30)  # Max 30s
```

### 6. Use webhooks instead of polling

```python
# Instead of polling every 5 seconds, use webhooks
# Stendly will POST to your endpoint when payment completes

# Your endpoint:
@app.route("/webhook", methods=["POST"])
def webhook():
    event = verify_and_parse()
    if event.event_type == "payment_intent.succeeded":
        fulfill_order(event.data.order_id)
    return "", 200
```

### 7. Log request IDs for debugging

```python
try:
    intent = client.intents.create(...)
except StendlyError as e:
    logger.error(
        f"API error: {e.message} "
        f"(request_id={e.request_id})"
    )
    # Include request_id in support ticket
```

### 8. Security Best Practices

#### Protect API Keys

```python
# Use environment variables or secret manager
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("STENDLY_API_KEY")

# Or use cloud secret manager (AWS, GCP, Azure)
```

#### Use HTTPS in Production

```python
# Force HTTPS
if os.getenv("ENVIRONMENT") == "production":
    assert client.base_url.startswith("https://")
```

#### Prevent Replay Attacks

The SDK does this automatically (timestamp check), but ensure:
- Clock is synchronized (NTP)
- Tolerance not increased beyond 5 minutes

#### Log Securely

```python
# ❌ BAD - logs secret
logger.info(f"API key: {api_key}")

# ✅ GOOD - redact
logger.info(f"API key: {mask_key(api_key)}")
```

#### Rate Limiting on Your End

Protect your webhook endpoint:

```python
from flask_limiter import Limiter

limiter = Limiter(app, key_func=lambda: request.remote_addr)

@app.route("/webhooks/stendly", methods=["POST"])
@limiter.limit("10/minute")
def webhook():
    ...
```

---

---

## Contributing

We welcome contributions! Please read [CONTRIBUTING.md](CONTRIBUTING.md) first.

```bash
# Setup dev environment
poetry install

# Run tests
pytest

# Lint
ruff check .

# Format
ruff format .
```

### Development Setup

```bash
git clone https://github.com/stendly/stendly-python.git
cd stendly-python

# Install dependencies
poetry install

# Run tests
pytest

# Lint
ruff check stendly/

# Format
ruff format stendly/
```

### Project structure

```
stendly-python/
├── stendly/
│   ├── __init__.py          # Public API exports
│   ├── client.py            # Client & AsyncClient
│   ├── exceptions.py        # All exception classes
│   ├── models.py            # Pydantic DTOs
│   ├── _http.py             # Internal HTTP client (retry, pooling)
│   └── namespaces/
│       ├── intents.py       # Payment intent operations
│       ├── terminals.py     # Terminal management
│       ├── webhooks.py      # Webhook verification + config
│       └── merchant.py      # Profile + stats
├── tests/
├── docs/
├── pyproject.toml
├── README.md
└── CHANGELOG.md
```

---

## License & Links

### License

MIT License. See [LICENSE](LICENSE).

### Links

- 📖 [API Documentation](https://docs.stendly.com/api)
- 🐙 [GitHub Repository](https://github.com/stendly/stendly-python)
- 📦 [PyPI Package](https://pypi.org/project/stendly/)
- 🏠 [Stendly Website](https://stendly.com)
- 💬 [Discord Community](https://discord.gg/stendly)
- 🐦 [Twitter/X](https://twitter.com/stendly)

### Support

- 📧 Email: support@stendly.com
- 🐛 Bug reports: [GitHub Issues](https://github.com/stendly/stendly-python/issues)
- 💡 Feature requests: [GitHub Discussions](https://github.com/stendly/stendly-python/discussions)

---

**Built with ❤️ for the Solana ecosystem.**