# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-05-17

### Added
- `invoice_url()` method to build public checkout URLs (`app.stendly.com/checkout?invoice=...`)
- `verification_status_label` property on `MerchantProfile` with human-readable status labels
- HTTP/2 support via `httpx[http2]` dependency
- `422 Unprocessable Entity` error handling mapped to `ValidationError`
- Field aliases on `CreatePaymentIntentRequest` (`amountCents`, `orderId`, `terminalId`) with `populate_by_name=True`
- Response body logging for 4xx errors
- `__str__` representation on `MerchantProfile`

### Changed
- `MerchantProfile.verification_status` type from `str` to `int` (0=unverified, 1=pending, 2=verified, 3=rejected)

## [0.1.1] - 2026-05-17

### Fixed
- Version bump and packaging fixes

## v0.1.0

### Added
- Initial release of Stendly Python SDK
- Synchronous `Client` for Django, Flask, scripts
- Asynchronous `AsyncClient` for FastAPI, Starlette, aiogram
- HTTP/2 support with connection pooling
- Automatic retry with exponential backoff (default: 2 retries)
- Webhook signature verification with constant-time comparison
- Replay attack protection (timestamp validation)
- Full type hints for IDE autocomplete
- Comprehensive error handling with specific exception types:
  - `AuthenticationError` (401/403)
  - `ValidationError` (400)
  - `RateLimitError` (429)
  - `APIConnectionError` (network failures)
  - `SignatureVerificationError` (webhook invalid)
- Namespaces:
  - `client.intents` - Create and retrieve payment intents
  - `client.terminals` - Manage POS terminals
  - `client.webhooks` - Verify signatures, update webhook URL
  - `client.merchant` - Get profile and stats
- Pydantic v3 models for all request/response DTOs
- Auto-generated Idempotency-Key for POST requests
- Detailed docstrings with examples for all methods
- Configuration via environment variables
- Thread-safe clients
- Context manager support
- Comprehensive test suite (>95% coverage)

### Security
- Constant-time signature comparison (`hmac.compare_digest`)
- Timestamp validation (reject old webhooks)
- Secure secret storage recommendations
- HTTPS enforcement in production

[0.1.0] - 2026-05-10

### Added
- First public release (alpha)
- Core API functionality
- Webhook verification
