# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

## Reporting a Vulnerability

We take the security of Stendly SDK seriously. If you believe you've found a security vulnerability, please follow these steps:

### 1. Do NOT open a public GitHub issue

Publicly disclosing a vulnerability could put users at risk. Instead, email us privately.

### 2. Send details to security@stendly.com

Include:
- **Description**: What the vulnerability is and how it can be exploited
- **Steps to reproduce**: Exact steps to trigger the issue
- **Version**: SDK version you're testing
- **Impact**: What an attacker could achieve (data exfiltration, privilege escalation, etc.)
- **Your info**: Name (optional), organization (if any)

We'll respond within 48 hours with an acknowledgment.

### 3. We'll investigate and respond

Our process:
1. **48h**: Acknowledge receipt
2. **7 days**: Initial assessment and triage
3. **30 days**: Patch development and coordination (if confirmed)
4. **90 days**: Public disclosure (if needed) after patch release

### 4. Keep it confidential

Until we publish a fix, please keep the vulnerability report confidential.

## Security Best Practices for SDK Users

### 1. Protect Your API Keys

- Store in environment variables or secret managers
- Never commit to version control
- Rotate keys every 90 days
- Use separate keys for dev/test/prod

```python
# GOOD
import os
client = Client(api_key=os.environ["STENDLY_API_KEY"])

# BAD
client = Client(api_key="st_live_xxxxxxxx")  # Don't hardcode!
```

### 2. Verify Every Webhook

Never trust unverified webhooks:

```python
# ALWAYS verify
try:
    event = client.webhooks.construct_event(
        payload=request.get_data(),
        signature_header=request.headers["X-Stendly-Signature"],
        webhook_secret=WEBHOOK_SECRET,
    )
except SignatureVerificationError:
    abort(400, "Invalid signature")
```

### 3. Use HTTPS in Production

Webhook URLs must be HTTPS (except localhost for development).

```python
# In production
if os.getenv("ENV") == "production":
    assert webhook_url.startswith("https://")
```

### 4. Implement Proper Error Handling

Don't leak secrets in error messages:

```python
try:
    intent = client.intents.create(...)
except StendlyError as e:
    # Log detailed error internally
    logger.error(f"API error: {e}", extra={"request_id": e.request_id})
    # Show user-friendly message
    return "Payment failed. Try again."
```

### 5. Validate Inputs

Even though the SDK validates, also validate on your end:

```python
# Don't trust client input
amount_cents = int(request.json["amount"])
if amount_cents <= 0 or amount_cents > 1000000:  # $10,000 max
    return {"error": "Invalid amount"}, 400
```

### 6. Rate Limit Your Endpoints

Protect your webhook endpoint from flooding:

```python
from flask_limiter import Limiter

limiter = Limiter(app, key_func=lambda: request.remote_addr)

@app.route("/webhooks/stendly", methods=["POST"])
@limiter.limit("10/minute")
def webhook():
    ...
```

### 7. Clock Synchronization

Webhook timestamp verification requires accurate clocks. Use NTP:

```bash
# Linux
sudo timedatectl set-ntp true

# Check
timedatectl status
```

### 8. Use Latest SDK Version

We regularly update dependencies (httpx, pydantic). Stay current:

```bash
pip install --upgrade stendly
```

---

## Security Features of the SDK

The SDK implements several security measures out of the box:

### Constant-Time Signature Comparison

Webhook signature verification uses `hmac.compare_digest` to prevent timing attacks:

```python
# Inside construct_event
if hmac.compare_digest(expected_signature, received_signature):
    # Valid
```

### Timestamp Validation

Rejects webhooks older than 5 minutes (configurable) to prevent replay attacks:

```python
if age > tolerance_seconds:
    raise SignatureVerificationError(reason="timestamp_expired")
```

### Secure Random Idempotency Keys

Uses UUID v4 (cryptographically random) for idempotency headers.

### No Plaintext Secrets in Logs

SDK never logs API keys or webhook secrets. Request IDs are logged for debugging.

---

## Known Security Considerations

### Webhook Secret Exposure

**Risk**: Webhook secret stored in environment variables could be leaked via logs or error pages.

**Mitigation**:
- Use secret management systems (AWS Secrets Manager, HashiCorp Vault)
- Don't log `WEBHOOK_SECRET`
- Rotate secrets periodically (dashboard)

### Man-in-the-Middle Attacks

**Risk**: Without HTTPS, webhook payloads could be tampered.

**Mitigation**:
- Always use HTTPS for webhook URLs
- Verify signatures (the SDK does this by default)
- Use TLS 1.3 where possible

### Replay Attacks

**Risk**: Attacker replays old valid webhook.

**Mitigation**:
- SDK checks timestamp (default 5 min window)
- Server-side deduplication by Stendly (idempotency)
- Store processed event IDs and reject duplicates

### Denial of Service

**Risk**: Flooded webhook endpoint exhausts resources.

**Mitigation**:
- Rate limit your webhook endpoint
- Use async processing (queue webhook, respond quickly)
- Validate signature before heavy processing

---

## Cryptography Details

### Webhook Signature Algorithm

```
signature = HMAC-SHA256(secret, timestamp + raw_body)
header = "t={timestamp},v1={signature}"
```

- Key: webhook secret (256-bit)
- Message: `timestamp (ASCII) + payload (raw bytes)`
- Hash: SHA-256
- Comparison: constant-time (`hmac.compare_digest`)

### Idempotency Keys

UUID v4 (122 bits of randomness) to prevent collision attacks.

---

## Reporting Security Issues

**Email**: security@stendly.com
```

---

**Thank you for helping keep Stendly and our users secure!**
