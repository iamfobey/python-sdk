# Advanced Usage Guide

## Custom HTTP Client Configuration

### Configuring Proxy

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

### Custom Transport

```python
# For custom TLS configuration
transport = httpx.HTTPTransport(retries=3)
client = Client(
    api_key="...",
    # Pass custom transport (requires extending _http.py)
)
```

**Currently not exposed directly** — open an issue if you need this.

---

## Custom Retry Strategies

The SDK uses exponential backoff by default. To customize:

```python
from stendly._http import HTTPClient

# Extend and override
class MyHTTPClient(HTTPClient):
    def _calculate_backoff(self, attempt: int) -> float:
        # Linear backoff
        return min(attempt * 2, 30)

# Then use with custom Client (requires modification)
```

**Alternative:** Monkey-patch for quick testing:

```python
client = Client(api_key="...")
client._http_client._calculate_backoff = lambda attempt: 1.0  # Always 1s
```

---

## Middleware / Request Hooks

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

---

## Batch Operations

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

---

## Custom Exception Handling Middleware

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

## Async Best Practices

### Connection Pool in Async

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

### Proper Cleanup

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

---

## Webhook Payload Optimization

### Validate Before Verification

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

### Cached Verification (Stateless)

Webhook verification is fast (HMAC-SHA256). No caching needed.

---

## Retry Strategies

### Custom Retry Conditions

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

## Timezone Handling

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

## Bulk Operations via API

Currently, the API does not support bulk operations. If you need:

1. Open feature request on GitHub
2. Implement concurrency with ThreadPoolExecutor
3. Consider server-side batching if >1000 requests

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

## FAQ

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

**Need more help?** Open an issue or contact support@stendly.com.
