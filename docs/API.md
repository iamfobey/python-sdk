# Stendly Python SDK Documentation

## Table of Contents

1. [Quick Start](#quick-start)
2. [Authentication](#authentication)
3. [Payment Intents](#payment-intents)
4. [Webhooks](#webhooks)
5. [Error Handling](#error-handling)
6. [Advanced Usage](#advanced-usage)
7. [Integration Examples](#integration-examples)
8. [Performance](#performance)
9. [Security](#security)

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

### Exception Hierarchy

```
StendlyError (base)
├── AuthenticationError (401/403)
├── ValidationError (400)
├── RateLimitError (429)
├── APIConnectionError (network)
└── SignatureVerificationError (webhook)
```

### Example: Comprehensive Error Handling

```python
from stendly import (
    Client,
    StendlyError,
    AuthenticationError,
    ValidationError,
    RateLimitError,
    APIConnectionError,
)

client = Client(api_key="st_live_...")

try:
    intent = client.intents.create(
        amount_cents=1000,
        order_id="order_123"
    )
except AuthenticationError as e:
    # Log and alert (API key invalid)
    logger.error(f"Auth failed: {e.message}")
    # Action: Check API key in dashboard
except ValidationError as e:
    # Log validation details
    logger.warning(f"Invalid input: {e.message} (field: {e.field})")
    # Action: Fix request parameters
except RateLimitError as e:
    # Implement backoff
    logger.info(f"Rate limited. Retry after {e.retry_after}s")
    time.sleep(e.retry_after)
except APIConnectionError as e:
    # Network issue - retry later
    logger.error(f"Network error: {e.message}")
    # Action: Check connection, retry
except StendlyError as e:
    # Catch-all for other API errors
    logger.error(f"API error {e.status_code}: {e.message}")
    # Include e.request_id in support ticket
```

---

## Advanced Usage

### Connection Pooling

The SDK uses `httpx` with connection pooling by default:

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

### Idempotency

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

---

## Integration Examples

### Django

```python
# myapp/stendly.py
import os
from stendly import Client

client = Client(api_key=os.getenv("STENDLY_API_KEY"))

# views.py
from django.http import JsonResponse
from .stendly import client

def create_intent(request):
    data = json.loads(request.body)
    intent = client.intents.create(
        amount_cents=data["amount"],
        order_id=data["order_id"]
    )
    return JsonResponse({
        "reference": intent.reference_address,
        "expires_at": intent.expires_at.isoformat(),
    })
```

### FastAPI (Async)

```python
from fastapi import FastAPI, Depends, HTTPException
from stendly import AsyncClient, StendlyError
import os

app = FastAPI()
client = AsyncClient(api_key=os.getenv("STENDLY_API_KEY"))

@app.post("/api/intents")
async def create_intent(data: dict):
    try:
        intent = await client.intents.create(
            amount_cents=data["amount"],
            order_id=data["order_id"]
        )
        return {
            "id": str(intent.id),
            "reference": intent.reference_address,
        }
    except StendlyError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.on_event("shutdown")
async def shutdown():
    await client.aclose()
```

### Celery Task

```python
from celery import Celery
from stendly import Client

celery = Celery("tasks")
client = Client(api_key=os.getenv("STENDLY_API_KEY"))

@celery.task
def check_payment_status(intent_id):
    """Poll payment status (use webhooks instead when possible)."""
    intent = client.intents.retrieve(intent_id)
    if intent.status == "paid":
        fulfill_order(intent.order_id)
    elif intent.status == "expired":
        notify_customer(intent.order_id, "expired")
```

### Telegram Bot (aiogram)

```python
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from stendly import AsyncClient
import asyncio

bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))
dp = Dispatcher()
client = AsyncClient(api_key=os.getenv("STENDLY_API_KEY"))

@dp.message_handler(commands=["pay"])
async def cmd_pay(message: Message):
    # Parse amount from command
    parts = message.text.split()
    amount_cents = int(float(parts[1]) * 100)  # $5.00 → 500
    
    intent = await client.intents.create(
        amount_cents=amount_cents,
        order_id=f"tg_{message.from_user.id}_{int(time.time())}"
    )
    
    await message.answer(
        f"💰 Send ${amount_cents/100:.2f} USDC to:\n\n"
        f"`{intent.reference_address}`\n\n"
        f"⏱ Expires: {intent.expires_at.strftime('%H:%M')}",
        parse_mode="Markdown"
    )

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Performance

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

### Async concurrency

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

## Security Best Practices

### 1. Protect API Keys

```python
# Use environment variables or secret manager
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("STENDLY_API_KEY")

# Or use cloud secret manager (AWS, GCP, Azure)
```

### 2. Verify All Webhooks

```python
# NEVER skip verification
# ❌ BAD:
event = request.get_json()  # No verification!

# ✅ GOOD:
event = client.webhooks.construct_event(
    payload=request.get_data(),
    signature_header=request.headers["X-Stendly-Signature"],
    webhook_secret=WEBHOOK_SECRET
)
```

### 3. Use HTTPS in Production

```python
# Force HTTPS
if os.getenv("ENVIRONMENT") == "production":
    assert client.base_url.startswith("https://")
```

### 4. Validate Redirects

If your webhook endpoint redirects, verify final destination.

### 5. Prevent Replay Attacks

The SDK does this automatically (timestamp check), but ensure:
- Clock is synchronized (NTP)
- Tolerance not increased beyond 5 minutes

### 6. Log Securely

```python
# ❌ BAD - logs secret
logger.info(f"API key: {api_key}")

# ✅ GOOD - redact
logger.info(f"API key: {mask_key(api_key)}")
```

### 7. Rate Limiting on Your End

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

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| `AuthenticationError` | Check API key format; regenerate if leaked |
| `ValidationError` | Validate input before API call |
| `RateLimitError` | Implement backoff; respect `Retry-After` header |
| `APIConnectionError` | Check internet; increase timeout; retry |
| Webhook verification fails | Verify webhook secret; use raw payload; check clock sync |

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

## Migration Guide

### From 0.1.x to 0.2.0 (planned)

Breaking changes:
- None (early stage, stable API)

### From future versions

Check [CHANGELOG.md](CHANGELOG.md) for upgrade notes.

---

## Additional Resources

- [API Reference](https://docs.stendly.com/api)
- [Python SDK Docs](https://docs.stendly.com/python-sdk)
- [Stendly Dashboard](https://dashboard.stendly.com)
- [Community Discord](https://discord.gg/stendly)
