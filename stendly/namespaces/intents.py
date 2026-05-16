"""
Intents namespace for managing payment intentions.

This namespace provides methods to create and retrieve payment intents.
Payment intents represent a request for payment from a merchant to a
customer, including escrow address and destination addresses for the
USDC transfer on Solana.

Example:
    >>> from stendly import Client
    >>> client = Client(api_key="st_live_...")
    >>>
    >>> # Create a new payment intent
    >>> intent = client.intents.create(
    ...     amount_cents=4999,
    ...     order_id="order_001"
    ... )
    >>> print(f"Intent ID: {intent.id}")
    >>> print(f"Escrow address: {intent.reference_address}")
    >>>
    >>> # Retrieve existing intent
    >>> retrieved = client.intents.retrieve(intent.id)
    >>> print(f"Status: {retrieved.status}")
"""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from pydantic import ValidationError as PydanticValidationError

from .._http import HTTPClient, AsyncHTTPClient
from ..exceptions import ValidationError
from ..models import (
    CreatePaymentIntentRequest,
    PaymentIntent,
)

logger = logging.getLogger(__name__)


class IntentsNamespace:
    """
    Payment intents management (synchronous).

    Provides methods to create and retrieve payment intents. Payment
    intents are the core resource for requesting payments from customers.
    Each intent generates a unique escrow address (reference_address)
    where the customer sends USDC.

    This namespace is available as `client.intents` on the synchronous Client.

    Attributes:
        _http_client: Synchronous HTTP client

    Example:
        >>> client = Client(api_key="st_live_...")
        >>>
        >>> # Create intent with automatic idempotency key
        >>> intent = client.intents.create(
        ...     amount_cents=4999,
        ...     order_id="order_001"
        ... )
        >>>
        >>> # Retrieve by ID
        >>> same_intent = client.intents.retrieve(intent.id)
    """

    def __init__(
        self,
        http_client: HTTPClient,
    ) -> None:
        """
        Initialize intents namespace.

        Args:
            http_client: Synchronous HTTP client
        """
        self._http_client = http_client

    def create(
        self,
        amount_cents: int,
        order_id: str,
        terminal_id: Optional[str | UUID] = None,
        idempotency_key: Optional[str] = None,
    ) -> PaymentIntent:
        """
        Create a new payment intent.

        Creates a payment intent that represents a request for payment.
        The intent includes an escrow address (reference_address) where
        the customer should send USDC. The merchant's payout address is
        stored separately and not exposed to the customer.

        Idempotency is automatically handled: if you retry the same
        request with the same order_id and amount_cents within a short
        window, the existing intent will be returned instead of creating
        a duplicate.

        If idempotency_key is not provided, a UUID v4 is automatically
        generated and added to the Idempotency-Key header.

        Args:
            amount_cents: Amount to charge in cents (e.g., 4999 = $49.99)
                Must be positive (> 0).
            order_id: Unique order reference from your system.
                Must be unique per merchant. Used to prevent duplicate
                charges if the same order is submitted multiple times.
                Max length: 100 characters.
            terminal_id: Optional terminal UUID for POS scenarios.
                If provided, any other pending intents for this terminal
                will be automatically cancelled.
            idempotency_key: Custom idempotency key (UUID v4 format).
                Use this if you need explicit control over idempotency.
                If not provided, one will be auto-generated.

        Returns:
            PaymentIntent: Created or existing payment intent object with
                all fields including escrow address and expiry time.

        Raises:
            AuthenticationError: Invalid or missing API key
            ValidationError: Invalid parameters (amount <= 0, order_id too long, etc.)
            RateLimitError: Too many requests (retry after header provided)
            APIConnectionError: Network failure after retries
            StendlyError: Other API errors

        Example:
            Basic usage:
            >>> intent = client.intents.create(
            ...     amount_cents=999,
            ...     order_id="premium_sub_001"
            ... )
            >>> print(f"Pay to: {intent.reference_address}")

            With terminal (POS):
            >>> intent = client.intents.create(
            ...     amount_cents=2500,
            ...     order_id="table_5_order",
            ...     terminal_id="222e4567-e89b-12d3-a456-426614174000"
            ... )

            Custom idempotency key:
            >>> import uuid
            >>> key = str(uuid.uuid4())
            >>> intent = client.intents.create(
            ...     amount_cents=5000,
            ...     order_id="order_123",
            ...     idempotency_key=key
            ... )

            Error handling:
            >>> from stendly import ValidationError, AuthenticationError
            >>> try:
            ...     intent = client.intents.create(
            ...         amount_cents=-100,
            ...         order_id="bad"
            ...     )
            ... except ValidationError as e:
            ...     print(f"Bad input: {e.message}")
            ... except AuthenticationError:
            ...     print("Check your API key")

        Note:
            - The same order_id with the same amount will return the
              existing intent for ~5 minutes (server-side deduplication).
            - Intents expire after 30 minutes by default.
            - Status starts as "pending" and transitions to "paid" when
              payment is detected.
        """
        # Generate idempotency key if not provided
        if idempotency_key is None:
            idempotency_key = self._http_client.generate_idempotency_key()


        # Validate request data using Pydantic, convert to our ValidationError
        try:
            request_data = CreatePaymentIntentRequest(
                amount_cents=amount_cents,
                order_id=order_id,
                terminal_id=terminal_id if terminal_id else None,
            )
        except PydanticValidationError as e:
            err = e.errors()[0]
            field = str(err["loc"][0]) if err["loc"] else None
            raise ValidationError(
                message=err["msg"],
                field=field,
                details={"errors": e.errors()},
            ) from e

        logger.debug(
            f"Creating payment intent: order_id={order_id}, "
            f"amount_cents={amount_cents}, idempotency_key={idempotency_key}"
        )

        # Make API request
        response = self._http_client.request(
            method="POST",
            path="/api/merchants/intents",
            json=request_data.model_dump(by_alias=True, exclude_none=True),
            idempotency_key=idempotency_key,
        )

        # Parse response
        response_data = response.json()
        intent = PaymentIntent.model_validate(response_data)

        logger.info(
            f"Payment intent created: id={intent.id}, "
            f"reference={intent.reference_address}"
        )

        return intent

    def retrieve(self, intent_id: str | UUID) -> PaymentIntent:
        """
        Retrieve a payment intent by ID.

        Fetches the full details of a payment intent, including its
        current status, amounts, and addresses. Use this to check the
        payment status after redirecting the customer.

        Args:
            intent_id: Payment intent UUID (string or UUID object)
                Can be obtained from create() response or webhook event.

        Returns:
            PaymentIntent: Full payment intent object with current status.

        Raises:
            AuthenticationError: Invalid API key
            ValidationError: Invalid intent_id format
            StendlyError: Intent not found (404) or other API errors

        Example:
            >>> # Check status of existing intent
            >>> intent_id = "123e4567-e89b-12d3-a456-426614174000"
            >>> intent = client.intents.retrieve(intent_id)
            >>> if intent.status == "paid":
            ...     print("Payment received!")
            ... elif intent.status == "pending":
            ...     print("Still waiting...")
            ... elif intent.status == "expired":
            ...     print("Intent expired - create new one")

        Note:
            - Intent statuses: "pending", "paid", "underpaid", "expired", "cancelled"
            - The expires_at field indicates when the intent becomes invalid
            - underpaid status means payment was received but less than expected
        """
        logger.debug(f"Retrieving payment intent: id={intent_id}")

        response = self._http_client.request(
            "GET",
            f"/api/merchants/intents/{intent_id}",
        )

        response_data = response.json()
        intent = PaymentIntent.model_validate(response_data)

        logger.debug(f"Retrieved intent: id={intent.id}, status={intent.status}")

        return intent


class AsyncIntentsNamespace:
    """
    Payment intents management (asynchronous).

    Provides async methods to create and retrieve payment intents. Payment
    intents are the core resource for requesting payments from customers.
    Each intent generates a unique escrow address (reference_address)
    where the customer sends USDC.

    This namespace is available as `client.intents` on the asynchronous AsyncClient.

    Attributes:
        _async_http_client: Asynchronous HTTP client

    Example:
        >>> client = AsyncClient(api_key="st_live_...")
        >>>
        >>> # Create intent with automatic idempotency key
        >>> intent = await client.intents.create(
        ...     amount_cents=4999,
        ...     order_id="order_001"
        ... )
        >>>
        >>> # Retrieve by ID
        >>> same_intent = await client.intents.retrieve(intent.id)
    """

    def __init__(
        self,
        async_http_client: AsyncHTTPClient,
    ) -> None:
        """
        Initialize async intents namespace.

        Args:
            async_http_client: Asynchronous HTTP client
        """
        self._async_http_client = async_http_client

    async def create(
        self,
        amount_cents: int,
        order_id: str,
        terminal_id: Optional[str | UUID] = None,
        idempotency_key: Optional[str] = None,
    ) -> PaymentIntent:
        """
        Create a new payment intent (async).

        Creates a payment intent that represents a request for payment.
        The intent includes an escrow address (reference_address) where
        the customer should send USDC.

        Idempotency is automatically handled: if you retry the same
        request with the same order_id and amount_cents within a short
        window, the existing intent will be returned instead of creating
        a duplicate.

        Args:
            amount_cents: Amount to charge in cents (e.g., 4999 = $49.99)
            order_id: Unique order reference from your system.
            terminal_id: Optional terminal UUID for POS scenarios.
            idempotency_key: Custom idempotency key (UUID v4 format).

        Returns:
            PaymentIntent: Created or existing payment intent object.

        Raises:
            AuthenticationError: Invalid or missing API key
            ValidationError: Invalid parameters
            RateLimitError: Too many requests
            APIConnectionError: Network failure after retries
            StendlyError: Other API errors

        Example:
            >>> import asyncio
            >>> from stendly import AsyncClient
            >>>
            >>> async def main():
            ...     client = AsyncClient(api_key="st_live_...")
            ...     intent = await client.intents.create(
            ...         amount_cents=5000,
            ...         order_id="order_456"
            ...     )
            ...     print(intent.id)
            >>> asyncio.run(main())
        """
        if idempotency_key is None:
            idempotency_key = self._async_http_client.generate_idempotency_key()

        try:
            request_data = CreatePaymentIntentRequest(
                amount_cents=amount_cents,
                order_id=order_id,
                terminal_id=terminal_id if terminal_id else None,
            )
        except PydanticValidationError as e:
            err = e.errors()[0]
            field = str(err["loc"][0]) if err["loc"] else None
            raise ValidationError(
                message=err["msg"],
                field=field,
                details={"errors": e.errors()},
            ) from e

        response = await self._async_http_client.request(
            method="POST",
            path="/api/merchants/intents",
            json=request_data.model_dump(by_alias=True, exclude_none=True),
            idempotency_key=idempotency_key,
        )

        response_data = response.json()
        return PaymentIntent.model_validate(response_data)

    async def retrieve(self, intent_id: str | UUID) -> PaymentIntent:
        """
        Retrieve a payment intent by ID (async).

        Fetches the full details of a payment intent, including its
        current status, amounts, and addresses.

        Args:
            intent_id: Payment intent UUID (string or UUID object)

        Returns:
            PaymentIntent: Full payment intent object with current status.

        Raises:
            AuthenticationError: Invalid API key
            ValidationError: Invalid intent_id format
            StendlyError: Intent not found (404) or other API errors

        Example:
            >>> import asyncio
            >>> from stendly import AsyncClient
            >>>
            >>> async def check_payment(intent_id):
            ...     client = AsyncClient(api_key="st_live_...")
            ...     intent = await client.intents.retrieve(intent_id)
            ...     return intent.status
            >>>
            >>> status = asyncio.run(check_payment("123e4567..."))
        """
        response = await self._async_http_client.request(
            method="GET",
            path=f"/api/merchants/intents/{intent_id}",
        )

        response_data = response.json()
        return PaymentIntent.model_validate(response_data)