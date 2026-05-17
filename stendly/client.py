"""
Main Stendly SDK client.

This module provides the primary entry point for using the Stendly SDK.
It offers both synchronous (Client) and asynchronous (AsyncClient)
clients to suit different application architectures.

All methods and namespaces are fully type-hinted for IDE autocomplete
and static type checking with mypy/pyright.

Example:
    >>> # Synchronous usage (Django, Flask, scripts)
    >>> from stendly import Client
    >>> client = Client(api_key="st_live_...")
    >>>
    >>> # Create payment intent
    >>> intent = client.intents.create(
    ...     amount_cents=4999,
    ...     order_id="order_001"
    ... )
    >>> print(f"Pay to: {intent.reference_address}")
    >>>
    >>> # Async usage (FastAPI, Starlette, aiogram)
    >>> from stendly import AsyncClient
    >>> import asyncio
    >>>
    >>> async def main():
    ...     client = AsyncClient(api_key="st_live_...")
    ...     intent = await client.intents.create(
    ...         amount_cents=4999,
    ...         order_id="order_001"
    ...     )
    ...     print(intent.id)
    >>> asyncio.run(main())
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

# Import HTTP clients
from ._http import HTTPClient, AsyncHTTPClient

# Import namespaces (sync)
from .namespaces.intents import IntentsNamespace
from .namespaces.terminals import TerminalsNamespace
from .namespaces.webhooks import WebhooksNamespace
from .namespaces.merchant import MerchantNamespace

# Import namespaces (async)
from .namespaces.intents import AsyncIntentsNamespace
from .namespaces.terminals import AsyncTerminalsNamespace
from .namespaces.webhooks import AsyncWebhooksNamespace
from .namespaces.merchant import AsyncMerchantNamespace

# Import exceptions for convenience
from .exceptions import (
    StendlyError,
    AuthenticationError,
    ValidationError,
    RateLimitError,
    APIConnectionError,
    SignatureVerificationError,
)

# Import models for convenience
from .models import (
    PaymentIntent,
    PaymentIntentStatus,
    Terminal,
    MerchantProfile,
    MerchantStats,
    WebhookEvent,
)

logger = logging.getLogger(__name__)

__all__ = [
    "Client",
    "AsyncClient",
    "StendlyError",
    "AuthenticationError",
    "ValidationError",
    "RateLimitError",
    "APIConnectionError",
    "SignatureVerificationError",
    "PaymentIntent",
    "PaymentIntentStatus",
    "Terminal",
    "MerchantProfile",
    "MerchantStats",
    "WebhookEvent",
]


class BaseClient:
    """
    Base client class with shared initialization logic.

    This is an abstract base class that both Client and AsyncClient
    inherit from. It handles common setup like environment detection,
    namespace initialization, and resource cleanup.

    Attributes:
        api_key: Merchant API key
        environment: "mainnet" or "devnet"
        base_url: Resolved API base URL
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts
        http2: HTTP/2 support enabled

    Properties:
        intents: Payment intents namespace
        terminals: POS terminals namespace
        webhooks: Webhook management namespace
        merchant: Merchant account namespace
    """

    # Base URLs for different environments
    _ENVIRONMENTS = {
        "mainnet": "https://api.stendly.com",
        "devnet": "https://api-devnet.stendly.com",
    }

    # App URLs for public invoice/checkout pages
    _APP_URLS = {
        "mainnet": "https://app.stendly.com",
        "devnet": "https://app-devnet.stendly.com",
    }

    def invoice_url(self, intent_id: str) -> str:
        """
        Build a public checkout URL for a payment intent.

        Args:
            intent_id: Payment intent UUID

        Returns:
            Full URL to the checkout page (e.g. https://app.stendly.com/checkout?invoice=...)
        """
        app_url = self._APP_URLS.get(self.environment, self._APP_URLS["mainnet"])
        return f"{app_url}/checkout?invoice={intent_id}"

    def __init__(
        self,
        api_key: str,
        environment: str = "mainnet",
        timeout: float = 10.0,
        max_retries: int = 2,
        http2: bool = True,
    ) -> None:
        """
        Initialize Stendly client.

        Args:
            api_key: Merchant API key (starts with st_live_)
                Example: "st_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                Get this from your Stendly merchant dashboard.
            environment: API environment to use
                - "mainnet": Production API (default)
                - "devnet": Development/sandbox API
                Tests and development should use "devnet".
            timeout: Request timeout in seconds (default: 10.0)
                All requests will timeout after this many seconds.
            max_retries: Number of automatic retry attempts (default: 2)
                Failed requests will be retried with exponential backoff.
                Set to 0 to disable retries.
            http2: Enable HTTP/2 support (default: True)
                HTTP/2 provides better performance via connection multiplexing.
                Set to False only if you have compatibility issues.

        Example:
            >>> # Production client
            >>> client = Client(api_key="st_live_...")
            >>>
            >>> # Development client (same key prefix, different environment)
            >>> client = Client(
            ...     api_key="st_live_...",
            ...     environment="devnet"
            ... )
            >>>
            >>> # Custom timeout and retries
            >>> client = Client(
            ...     api_key="st_live_...",
            ...     timeout=30.0,  # Longer timeout for slow networks
            ...     max_retries=5   # More retries for unreliable connections
            ... )

            Environment selection:
            >>> # Choose environment explicitly
            >>> client = Client(api_key="st_live_...", environment="mainnet")
            >>> client = Client(api_key="st_live_...", environment="devnet")

        Raises:
            ValueError: Invalid environment name or API key format

        Note:
            - API keys always start with "st_live_" for both environments
            - Use environment="devnet" for development/testing
            - Use environment="mainnet" for production
        """
        # Validate API key format
        if not (api_key.startswith("st_live_") or api_key == "..."):
            raise ValueError(
                "Invalid API key format. Must start with 'st_live_'."
            )

        # Resolve base URL
        if environment not in self._ENVIRONMENTS:
            raise ValueError(
                f"Invalid environment '{environment}'. "
                f"Valid options: {list(self._ENVIRONMENTS.keys())}"
            )

        base_url = self._ENVIRONMENTS[environment]

        logger.info(
            f"Initializing Stendly client: env={environment}, "
            f"base_url={base_url}, timeout={timeout}s, max_retries={max_retries}"
        )

        self.api_key = api_key
        self.environment = environment
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.http2 = http2

        # HTTP clients will be initialized by subclasses
        self._http_client: Optional[HTTPClient] = None
        self._async_http_client: Optional[AsyncHTTPClient] = None

        # Namespaces (initialized in subclass)
        self._init_namespaces()

    def _init_namespaces(self) -> None:
        """Initialize all API namespaces. Overridden by subclasses."""
        raise NotImplementedError

    def close(self) -> None:
        """
        Close HTTP connection pools and free resources.

        After calling close(), the client cannot be used for new requests.

        Example:
            >>> client = Client(api_key="st_live_...")
            >>> try:
            ...     intent = client.intents.create(...)
            ... finally:
            ...     client.close()

            Using context manager:
            >>> with Client(api_key="st_live_...") as client:
            ...     intent = client.intents.create(...)
            ...     # Client automatically closed on exit
        """
        if self._http_client:
            self._http_client.close()
            self._http_client = None
        logger.info("Client closed")

    def __enter__(self) -> BaseClient:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()

    def __del__(self) -> None:
        """Destructor - ensure connections are closed."""
        try:
            self.close()
        except Exception:
            pass


class Client(BaseClient):
    """
    Synchronous Stendly API client.

    This is the main entry point for synchronous applications such as
    Django, Flask, FastAPI (sync endpoints), scripts.

    All API methods are available as namespaces under the client:
    - client.intents - Payment intent operations
    - client.terminals - Terminal management
    - client.webhooks - Webhook verification and config
    - client.merchant - Merchant profile and analytics

    The client uses connection pooling and HTTP/2 by default for
    optimal performance. Requests are automatically retried on
    transient failures (5xx errors, timeouts, network errors).

    Example:
        Basic usage:
        >>> from stendly import Client
        >>>
        >>> client = Client(api_key="st_live_...")
        >>>
        >>> # Create payment intent
        >>> intent = client.intents.create(
        ...     amount_cents=4999,
        ...     order_id="ORDER-001"
        ... )
        >>> print(f"Escrow: {intent.reference_address}")
        >>>
        >>> # Check status
        >>> retrieved = client.intents.retrieve(intent.id)
        >>> print(f"Status: {retrieved.status}")
        >>>
        >>> # Close when done
        >>> client.close()

        Context manager:
        >>> with Client(api_key="st_live_...") as client:
        ...     intent = client.intents.create(
        ...         amount_cents=5000,
        ...         order_id="order_123"
        ...     )
        ...     print(intent.id)
        # Automatically closed

        Django settings.py:
        >>> from stendly import Client
        >>>
        >>> STENDLY_CLIENT = Client(
        ...     api_key=settings.STENDLY_API_KEY,
        ...     environment="mainnet"
        ... )

        Flask app.py:
        >>> from flask import Flask
        >>> from stendly import Client
        >>>
        >>> app = Flask(__name__)
        >>> stendly_client = Client(api_key="st_live_...")
        >>>
        >>> @app.route("/create-intent", methods=["POST"])
        >>> def create_intent():
        ...     data = request.get_json()
        ...     intent = stendly_client.intents.create(
        ...         amount_cents=data["amount"],
        ...         order_id=data["order_id"]
        ...     )
        ...     return {"reference": intent.reference_address}

        Error handling:
        >>> from stendly import (
        ...     StendlyError,
        ...     AuthenticationError,
        ...     ValidationError,
        ...     RateLimitError,
        ...     APIConnectionError,
        ... )
        >>>
        >>> client = Client(api_key="st_live_...")
        >>> try:
        ...     intent = client.intents.create(
        ...         amount_cents=1000,
        ...         order_id="test"
        ...     )
        ... except AuthenticationError:
        ...     print("Invalid API key")
        ... except ValidationError as e:
        ...     print(f"Bad input: {e.field} - {e.message}")
        ... except RateLimitError as e:
        ...     print(f"Slow down: retry after {e.retry_after}s")
        ... except APIConnectionError:
        ...     print("Network error - check connection")
        ... except StendlyError as e:
        ...     print(f"API error: {e.message}")

    Attributes:
        intents: IntentsNamespace - Payment intent methods
        terminals: TerminalsNamespace - Terminal management
        webhooks: WebhooksNamespace - Webhook verification
        merchant: MerchantNamespace - Profile and stats

    Thread Safety:
        The client is thread-safe for concurrent use. Connection pooling
        and retry logic are handled internally. You can share a single
        client instance across multiple threads or requests.
    """

    @property
    def intents(self) -> IntentsNamespace:
        return self._intents

    @property
    def terminals(self) -> TerminalsNamespace:
        return self._terminals

    @property
    def webhooks(self) -> WebhooksNamespace:
        return self._webhooks

    @property
    def merchant(self) -> MerchantNamespace:
        return self._merchant

    def _init_namespaces(self) -> None:
        """Initialize synchronous namespaces."""
        self._http_client = HTTPClient(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=self.timeout,
            max_retries=self.max_retries,
            http2=self.http2,
        )

        # Initialize namespaces
        self._intents = IntentsNamespace(http_client=self._http_client)
        self._terminals = TerminalsNamespace(http_client=self._http_client)
        self._webhooks = WebhooksNamespace(http_client=self._http_client)
        self._merchant = MerchantNamespace(http_client=self._http_client)

    def __repr__(self) -> str:
        """Return developer-friendly representation."""
        return (
            f"Client(environment={self.environment}, "
            f"base_url={self.base_url}, "
            f"timeout={self.timeout}s, "
            f"max_retries={self.max_retries})"
        )


class AsyncClient(BaseClient):
    """
    Asynchronous Stendly API client.

    This is the main entry point for async applications such as
    FastAPI, Starlette, aiogram, or any asyncio-based code.

    All API methods are available as async functions under namespaces.
    Remember to use `await` for all API calls.

    Example:
        FastAPI endpoint:
        >>> from fastapi import FastAPI, Depends
        >>> from stendly import AsyncClient
        >>>
        >>> app = FastAPI()
        >>> client = AsyncClient(api_key="st_live_...")
        >>>
        >>> @app.post("/create-intent")
        >>> async def create_intent(data: dict):
        ...     intent = await client.intents.create(
        ...         amount_cents=data["amount"],
        ...         order_id=data["order_id"]
        ...     )
        ...     return {"reference": intent.reference_address}
        >>>
        >>> # Close on shutdown
        >>> @app.on_event("shutdown")
        >>> async def shutdown():
        ...     await client.aclose()

        aiogram bot:
        >>> from aiogram import Bot, Dispatcher
        >>> from stendly import AsyncClient
        >>>
        >>> bot = Bot(token="...")
        >>> dp = Dispatcher()
        >>> client = AsyncClient(api_key="st_live_...")
        >>>
        >>> @dp.message(Command("pay"))
        >>> async def handle_pay(message: Message):
        ...     intent = await client.intents.create(
        ...         amount_cents=1000,
        ...         order_id=f"tg_{message.from_user.id}"
        ...     )
        ...     await message.answer(
        ...         f"Send USDC to: {intent.reference_address}"
        ...     )
        >>>
        >>> async def main():
        ...     await dp.start_polling(bot)
        >>>
        >>> if __name__ == "__main__":
        ...     asyncio.run(main())

        Error handling:
        >>> from stendly import StendlyError
        >>>
        >>> async def safe_create(amount: int, order_id: str):
        ...     client = AsyncClient(api_key="st_live_...")
        ...     try:
        ...         intent = await client.intents.create(
        ...             amount_cents=amount,
        ...             order_id=order_id
        ...         )
        ...         return intent
        ...     except StendlyError as e:
        ...         logger.error(f"API error: {e}")
        ...         return None
        ...     finally:
        ...         await client.aclose()

    Attributes:
        intents: AsyncIntentsNamespace (async methods)
        terminals: AsyncTerminalsNamespace (async methods)
        webhooks: AsyncWebhooksNamespace (async methods)
        merchant: AsyncMerchantNamespace (async methods)

    Note:
        - Always use `await` with API methods
        - Close the client with `await client.aclose()` on shutdown
        - Consider using as a context manager for automatic cleanup
        - Thread-safe within a single event loop
    """

    @property
    def intents(self) -> AsyncIntentsNamespace:
        return self._intents

    @property
    def terminals(self) -> AsyncTerminalsNamespace:
        return self._terminals

    @property
    def webhooks(self) -> AsyncWebhooksNamespace:
        return self._webhooks

    @property
    def merchant(self) -> AsyncMerchantNamespace:
        return self._merchant

    def _init_namespaces(self) -> None:
        """Initialize asynchronous namespaces."""
        self._async_http_client = AsyncHTTPClient(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=self.timeout,
            max_retries=self.max_retries,
            http2=self.http2,
        )

        # Initialize namespaces with async client
        self._intents = AsyncIntentsNamespace(
            async_http_client=self._async_http_client,
        )
        self._terminals = AsyncTerminalsNamespace(
            async_http_client=self._async_http_client,
        )
        self._webhooks = AsyncWebhooksNamespace(
            async_http_client=self._async_http_client,
        )
        self._merchant = AsyncMerchantNamespace(
            async_http_client=self._async_http_client,
        )

    async def aclose(self) -> None:
        """
        Close async HTTP connection pools.

        Always call this when shutting down your application to
        properly close connection pools and prevent resource leaks.

        Example:
            >>> client = AsyncClient(api_key="st_live_...")
            >>> try:
            ...     # Use client
            ...     intent = await client.intents.create(...)
            ... finally:
            ...     await client.aclose()

            Context manager:
            >>> async with AsyncClient(api_key="st_live_...") as client:
            ...     intent = await client.intents.create(...)
            ... # Automatically closed
        """
        if self._async_http_client:
            aclose_method = self._async_http_client.aclose
            if asyncio.iscoroutinefunction(aclose_method):
                await aclose_method()
            else:
                aclose_method()
            self._async_http_client = None
        logger.info("AsyncClient closed")

    async def __aenter__(self) -> AsyncClient:
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[object],
    ) -> None:
        """Async context manager exit."""
        await self.aclose()

    def __repr__(self) -> str:
        """Return developer-friendly representation."""
        return (
            f"AsyncClient(environment={self.environment}, "
            f"base_url={self.base_url}, "
            f"timeout={self.timeout}s, "
            f"max_retries={self.max_retries})"
        )
