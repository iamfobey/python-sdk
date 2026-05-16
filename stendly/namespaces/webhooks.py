"""
Webhooks namespace for webhook management and signature verification.

This namespace provides methods to update webhook URLs and verify
webhook signatures from Stendly. Webhook signature verification is
critical for security — always verify signatures before processing
webhook payloads.

Example:
    >>> from stendly import Client
    >>> client = Client(api_key="st_live_...")
    >>> 
    >>> # Update webhook URL
    >>> success = client.webhooks.update(
    ...     url="https://myshop.com/webhooks/stendly"
    ... )
    >>> print(f"Updated: {success}")
    >>> 
    >>> # Verify incoming webhook
    >>> from flask import request
    >>> signature = request.headers.get("X-Stendly-Signature")
    >>> payload = request.get_data()
    >>> 
    >>> try:
    ...     event = client.webhooks.construct_event(
    ...         payload=payload,
    ...         signature_header=signature,
    ...         webhook_secret="whsec_..."
    ...     )
    ...     # Process event...
    ... except Exception as e:
    ...     # Reject webhook - invalid signature
    ...     return "Invalid signature", 400
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Optional

from pydantic import ValidationError as PydanticValidationError

from .._http import HTTPClient, AsyncHTTPClient
from ..exceptions import SignatureVerificationError, ValidationError
from ..models import UpdateWebhookRequest, WebhookEvent

logger = logging.getLogger(__name__)


class WebhooksNamespace:
    """
    Webhook management and verification (synchronous).

    Provides methods to:
    1. Update the webhook URL for payment notifications
    2. Verify webhook signatures to ensure authenticity

    Webhook verification is security-critical. Always verify webhooks
    before trusting their data. Never process unverified webhooks.

    This namespace is available as `client.webhooks` on the synchronous Client.

    Attributes:
        _http_client: Synchronous HTTP client

    Example:
        Basic webhook verification (Flask):
        >>> from flask import Flask, request, abort
        >>> app = Flask(__name__)
        >>> client = Client(api_key="st_live_...")
        >>> WEBHOOK_SECRET = "whsec_abc123..."
        >>> 
        >>> @app.route("/webhooks/stendly", methods=["POST"])
        >>> def webhook_handler():
        ...     signature = request.headers.get("X-Stendly-Signature")
        ...     timestamp = request.headers.get("X-Stendly-Timestamp")
        ...     payload = request.get_data()
        ...     
        ...     try:
        ...         event = client.webhooks.construct_event(
        ...             payload=payload,
        ...             signature_header=signature,
        ...             webhook_secret=WEBHOOK_SECRET
        ...         )
        ...     except SignatureVerificationError:
        ...         abort(400, "Invalid signature")
        ...     
        ...     # Process verified event
        ...     handle_payment(event)
        ...     return "", 200

        Django:
        >>> from django.views.decorators.csrf import csrf_exempt
        >>> from django.http import HttpResponse
        >>> 
        >>> @csrf_exempt
        >>> def webhook(request):
        ...     signature = request.headers.get("X-Stendly-Signature")
        ...     payload = request.body
        ...     
        ...     try:
        ...         event = client.webhooks.construct_event(
        ...             payload=payload,
        ...             signature_header=signature,
        ...             webhook_secret=settings.STENDLY_WEBHOOK_SECRET
        ...         )
        ...     except SignatureVerificationError:
        ...         return HttpResponse("Invalid signature", status=400)
        ...     
        ...     handle_event(event)
        ...     return HttpResponse("")
    """

    def __init__(
        self,
        http_client: HTTPClient,
    ) -> None:
        """
        Initialize webhooks namespace.

        Args:
            http_client: Synchronous HTTP client
        """
        self._http_client = http_client

    def update(
        self,
        url: str,
    ) -> bool:
        """
        Update the webhook URL for payment notifications.

        Sets the endpoint where Stendly will send payment event
        notifications. After updating, all payment events will be
        sent to the new URL.

        Args:
            url: Webhook endpoint URL (must be HTTPS in production)
                Example: "https://myshop.com/webhooks/stendly"
                The URL must be publicly accessible from the internet.
                Localhost URLs are only valid for development.

        Returns:
            bool: True if webhook URL was successfully updated.

        Raises:
            AuthenticationError: Invalid API key or insufficient permissions
            ValidationError: Invalid URL format (not HTTPS in prod)
            RateLimitError: Too many update attempts
            APIConnectionError: Network failure
            StendlyError: Other API errors (e.g., not verified)

        Example:
            >>> # Update to production URL
            >>> success = client.webhooks.update(
            ...     url="https://myshop.com/webhooks/stendly"
            ... )
            >>> if success:
            ...     print("Webhook URL updated successfully")

            >>> # Update during development
            >>> client.webhooks.update(
            ...     url="http://localhost:5000/webhooks/stendly"
            ... )

            Error handling:
            >>> from stendly import ValidationError
            >>> try:
            ...     client.webhooks.update(url="not-a-url")
            ... except ValidationError as e:
            ...     print(f"Invalid URL: {e.message}")

        Note:
            - Requires merchant verification status "verified"
            - URL will be validated (must be valid HTTPS in production)
            - Previous webhook URL will be overwritten
            - Webhook secret remains the same unless regenerated
        """
        import logging
        logger = logging.getLogger(__name__)

        logger.info(f"Updating webhook URL to: {url}")

        # Validate request
        try:
            request = UpdateWebhookRequest(webhook_url=url)
        except PydanticValidationError as e:
            err = e.errors()[0]
            field = str(err["loc"][0]) if err["loc"] else None
            raise ValidationError(
                message=err["msg"],
                field=field,
                details={"errors": e.errors()},
            ) from e

        response = self._http_client.request(
            method="PATCH",
            path="/api/b2b/merchants/webhook",
            json=request.model_dump(by_alias=True),
        )

        # Successful PATCH returns 200 OK
        logger.info(f"Webhook URL updated successfully")

        return True

    def construct_event(
        self,
        payload: bytes | str,
        signature_header: str,
        webhook_secret: str,
        tolerance_seconds: int = 300,  # 5 minutes
    ) -> WebhookEvent:
        """
        Verify webhook signature and construct event object.

        This method validates the webhook signature using HMAC-SHA256
        and checks the timestamp to prevent replay attacks. It is
        security-critical — ALWAYS verify webhooks before processing.

        The webhook signature is calculated as:
            signature = HMAC-SHA256(secret, timestamp + payload)

        Args:
            payload: Raw webhook request body (bytes or string)
                Should be the exact bytes received from the webhook POST.
                Do NOT modify or re-encode the payload.
            signature_header: Value of X-Stendly-Signature header
                Format: "t={timestamp},v1={signature_hash}"
                Example: "t=1715347200,v1=abc123def456..."
            webhook_secret: Webhook secret from merchant profile
                Starts with "whsec_". Keep this secret secure!
            tolerance_seconds: Maximum age of webhook in seconds
                Default: 300 (5 minutes). Rejects older webhooks to
                prevent replay attacks.

        Returns:
            WebhookEvent: Verified webhook event with structured data.
                Contains event_type and data attributes.

        Raises:
            SignatureVerificationError: If signature verification fails
                - Invalid signature format
                - Signature mismatch
                - Timestamp expired (older than tolerance_seconds)
                - Missing required headers
                - Invalid JSON payload

        Example:
            Flask webhook endpoint:
            >>> from flask import Flask, request, abort
            >>> app = Flask(__name__)
            >>> WEBHOOK_SECRET = "whsec_abc123..."
            >>> 
            >>> @app.route("/webhooks/stendly", methods=["POST"])
            >>> def webhook_handler():
            ...     signature = request.headers.get("X-Stendly-Signature")
            ...     if not signature:
            ...         abort(400, "Missing signature")
            ...     
            ...     payload = request.get_data()
            ...     
            ...     try:
            ...         event = client.webhooks.construct_event(
            ...             payload=payload,
            ...             signature_header=signature,
            ...             webhook_secret=WEBHOOK_SECRET
            ...         )
            ...     except SignatureVerificationError as e:
            ...         logger.warning(f"Invalid webhook: {e}")
            ...         abort(400, "Invalid signature")
            ...     
            ...     # Process verified event
            ...     if event.event_type == "payment_intent.succeeded":
            ...         fulfill_order(event.data.order_id)
            ...     
            ...     return "", 200

            Django:
            >>> from django.views.decorators.csrf import csrf_exempt
            >>> from django.http import HttpResponse
            >>> 
            >>> @csrf_exempt
            >>> def webhook(request):
            ...     signature = request.headers.get("X-Stendly-Signature")
            ...     payload = request.body
            ...     
            ...     try:
            ...         event = client.webhooks.construct_event(
            ...             payload=payload,
            ...             signature_header=signature,
            ...             webhook_secret=settings.STENDLY_WEBHOOK_SECRET
            ...         )
            ...     except SignatureVerificationError:
            ...         return HttpResponse("Invalid signature", status=400)
            ...     
            ...     handle_event(event)
            ...     return HttpResponse("")

        Security Notes:
            - NEVER skip signature verification in production
            - Store webhook secret securely (environment variable)
            - Use constant-time comparison to prevent timing attacks
            - Check timestamp to prevent replay attacks (5 min default)
            - If timestamp is missing, reject the webhook
            - The payload must be raw bytes — do not parse/re-serialize

        Implementation Details:
            - Uses hmac.compare_digest for constant-time comparison
            - Timestamp is extracted from signature header (t=...)
            - Signature hash format: SHA256(secret, timestamp + payload)
            - Header format: "t={timestamp},v1={hash1}[,v2={hash2}]"
        """
        import json

        logger.debug("Verifying webhook signature")

        # Convert payload to bytes if needed
        if isinstance(payload, str):
            try:
                payload_bytes = payload.encode("utf-8")
            except UnicodeEncodeError as e:
                raise SignatureVerificationError(
                    message=f"Failed to encode payload as UTF-8: {e}",
                    reason="invalid_encoding",
                )
        else:
            payload_bytes = payload

        # Parse signature header
        # Format: "t=timestamp,v1=hash1,v2=hash2"
        timestamp_str, signatures = self._parse_signature_header(signature_header)

        if not timestamp_str:
            raise SignatureVerificationError(
                message="Invalid signature header format",
                reason="invalid_header_format",
            )

        try:
            timestamp = int(timestamp_str)
        except ValueError:
            raise SignatureVerificationError(
                message="Invalid timestamp in signature header",
                reason="invalid_timestamp",
            )

        # Verify timestamp
        current_time = int(time.time())
        age = current_time - timestamp

        if age > tolerance_seconds:
            raise SignatureVerificationError(
                message=f"Webhook is too old (age: {age}s, max: {tolerance_seconds}s)",
                reason="timestamp_expired",
            )

        if timestamp > current_time + 30:  # 30 sec clock skew tolerance
            raise SignatureVerificationError(
                message="Webhook timestamp is in the future",
                reason="future_timestamp",
            )

        # Verify signature
        expected_signature = self._compute_signature(
            secret=webhook_secret,
            timestamp=timestamp,
            payload=payload_bytes,
        )

        # Check each provided signature using constant-time compare
        for sig in signatures:
            if hmac.compare_digest(expected_signature, sig):
                logger.debug("Webhook signature verified successfully")

                # Parse and return event
                try:
                    if isinstance(payload, bytes):
                        try:
                            payload_str = payload.decode("utf-8")
                        except UnicodeDecodeError as e:
                            raise SignatureVerificationError(
                                message=f"Invalid payload encoding: {e}",
                                reason="invalid_encoding",
                            )
                    else:
                        payload_str = payload

                    payload_data = json.loads(payload_str)
                except json.JSONDecodeError as e:
                    raise SignatureVerificationError(
                        message=f"Invalid JSON payload: {e}",
                        reason="invalid_json",
                    )

                # Construct WebhookEvent
                return WebhookEvent.model_validate(payload_data)

        # No signature matched
        raise SignatureVerificationError(
            message="Signature verification failed",
            reason="signature_mismatch",
        )

    def _parse_signature_header(
        self,
        signature_header: str,
    ) -> tuple[str, list[str]]:
        """
        Parse X-Stendly-Signature header.

        Format: "t=timestamp,v1=hash1,v2=hash2"

        Args:
            signature_header: Raw header value

        Returns:
            Tuple of (timestamp_str, [signature_hashes])

        Raises:
            SignatureVerificationError: If header format is invalid
        """
        if not signature_header:
            raise SignatureVerificationError(
                message="Missing X-Stendly-Signature header",
                reason="missing_signature",
            )

        parts = signature_header.split(",")
        timestamp = None
        signatures = []

        for part in parts:
            part = part.strip()
            if "=" not in part:
                continue

            key, value = part.split("=", 1)
            if key == "t":
                timestamp = value
            elif key in ("v1", "v2"):
                signatures.append(value)

        if not timestamp or not signatures:
            raise SignatureVerificationError(
                message="Invalid signature header format",
                reason="invalid_header_format",
            )

        return timestamp, signatures

    def _compute_signature(
        self,
        secret: str,
        timestamp: int,
        payload: bytes,
    ) -> str:
        """
        Compute expected HMAC-SHA256 signature.

        Args:
            secret: Webhook secret (whsec_...)
            timestamp: Unix timestamp from header
            payload: Raw request body bytes

        Returns:
            Hex-encoded signature hash
        """
        # Convert timestamp to bytes
        timestamp_bytes = str(timestamp).encode("utf-8")

        # Compute HMAC-SHA256 of (timestamp + payload)
        message = timestamp_bytes + payload

        hmac_obj = hmac.new(
            key=secret.encode("utf-8"),
            msg=message,
            digestmod=hashlib.sha256,
        )

        return hmac_obj.hexdigest()


class AsyncWebhooksNamespace:
    """
    Webhook management and verification (asynchronous).

    Provides async methods to:
    1. Update the webhook URL for payment notifications
    2. Verify webhook signatures to ensure authenticity

    This namespace is available as `client.webhooks` on the asynchronous AsyncClient.

    Note: webhook signature verification is CPU-bound and uses the
    synchronous code path internally.

    Attributes:
        _async_http_client: Asynchronous HTTP client
    """

    def __init__(
        self,
        async_http_client: AsyncHTTPClient,
    ) -> None:
        """
        Initialize async webhooks namespace.

        Args:
            async_http_client: Asynchronous HTTP client
        """
        self._async_http_client = async_http_client

    async def update(
        self,
        url: str,
    ) -> bool:
        """
        Update the webhook URL for payment notifications (async).

        Sets the endpoint where Stendly will send payment event
        notifications. After updating, all payment events will be
        sent to the new URL.

        Args:
            url: Webhook endpoint URL (must be HTTPS in production)

        Returns:
            bool: True if webhook URL was successfully updated.

        Raises:
            AuthenticationError: Invalid API key or insufficient permissions
            ValidationError: Invalid URL format
            RateLimitError: Too many update attempts
            APIConnectionError: Network failure
            StendlyError: Other API errors

        Example:
            >>> import asyncio
            >>> from stendly import AsyncClient
            >>> 
            >>> async def update_webhook():
            ...     client = AsyncClient(api_key="st_live_...")
            ...     success = await client.webhooks.update(
            ...         url="https://myshop.com/webhooks/stendly"
            ...     )
            ...     return success
            >>> asyncio.run(update_webhook())
        """
        try:
            request = UpdateWebhookRequest(webhook_url=url)
        except PydanticValidationError as e:
            err = e.errors()[0]
            field = str(err["loc"][0]) if err["loc"] else None
            raise ValidationError(
                message=err["msg"],
                field=field,
                details={"errors": e.errors()},
            ) from e

        await self._async_http_client.request(
            method="PATCH",
            path="/api/b2b/merchants/webhook",
            json=request.model_dump(by_alias=True),
        )

        return True

    async def construct_event(
        self,
        payload: bytes | str,
        signature_header: str,
        webhook_secret: str,
        tolerance_seconds: int = 300,
    ) -> WebhookEvent:
        """
        Verify webhook signature and construct event object (async).

        This method validates the webhook signature using HMAC-SHA256
        and checks the timestamp to prevent replay attacks.

        Args:
            payload: Raw webhook request body (bytes or string)
            signature_header: Value of X-Stendly-Signature header
            webhook_secret: Webhook secret from merchant profile
            tolerance_seconds: Maximum age of webhook in seconds

        Returns:
            WebhookEvent: Verified webhook event with structured data.

        Raises:
            SignatureVerificationError: If signature verification fails

        Example:
            >>> import asyncio
            >>> async def verify():
            ...     event = await client.webhooks.construct_event(
            ...         payload=body,
            ...         signature_header=signature,
            ...         webhook_secret=secret
            ...     )
            ...     return event
        """
        # Construct a temporary sync WebhooksNamespace to reuse
        # the pure CPU verification logic (no I/O involved).
        # construct_event, _parse_signature_header, _compute_signature
        # do NOT use self._http_client - they are pure CPU functions.
        sync_webhooks = WebhooksNamespace(http_client=None)  # type: ignore[arg-type]
        return sync_webhooks.construct_event(
            payload=payload,
            signature_header=signature_header,
            webhook_secret=webhook_secret,
            tolerance_seconds=tolerance_seconds,
        )