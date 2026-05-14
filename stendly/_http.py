"""
Internal HTTP client implementation with retry logic and connection pooling.

This module provides the low-level HTTP handling for both sync and async
clients. It uses httpx with HTTP/2 support, automatic retries, and
idempotency key management.

This is an internal module and should not be used directly by end users.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
import uuid
from typing import Any, Optional, Tuple, TypeVar
from urllib.parse import urljoin

import httpx
from httpx import Limits, Timeout

from .exceptions import (
    APIConnectionError,
    AuthenticationError,
    RateLimitError,
    StendlyError,
    ValidationError,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class HTTPClient:
    """
    Low-level synchronous HTTP client with retry logic and idempotency support.

    Handles all HTTP communication with the Stendly API, including:
    - HTTP/2 support via httpx
    - Connection pooling for performance
    - Exponential backoff retry for transient failures
    - Automatic Idempotency-Key generation
    - Error response parsing

    This class is not intended for direct use by SDK consumers.

    Args:
        base_url: API base URL (e.g., "https://api.stendly.com")
        api_key: Merchant API key (st_live_* or st_test_*)
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts for failed requests
        http2: Enable HTTP/2 support

    Example:
        >>> client = HTTPClient(
        ...     base_url="https://api.stendly.com",
        ...     api_key="st_live_xxx",
        ...     timeout=10.0,
        ...     max_retries=2,
        ...     http2=True
        ... )
        >>> response = client.request("GET", "/api/merchants/me")
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 10.0,
        max_retries: int = 2,
        http2: bool = True,
    ) -> None:
        """
        Initialize HTTP client with configuration.

        Args:
            base_url: API base URL (with https://)
            api_key: Secret API key
            timeout: Request timeout in seconds
            max_retries: Max retry attempts for transient failures
            http2: Enable HTTP/2 protocol
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = Timeout(timeout=timeout)
        self.max_retries = max_retries

        # Configure connection pooling for performance
        limits = Limits(
            max_connections=100,
            max_keepalive_connections=20,
            keepalive_expiry=30.0,
        )

        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            limits=limits,
            http2=http2,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": f"stendly-python-sdk/0.1.0",
                "X-Stendly-SDK": "python",
            },
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        idempotency_key: Optional[str] = None,
        retry_on_status: Tuple[int, ...] = (500, 502, 503, 504),
    ) -> httpx.Response:
        """
        Make HTTP request with retry logic and error handling.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API endpoint path (e.g., "/api/merchants/intents")
            json: Request body as dict (will be JSON-encoded)
            params: Query parameters
            headers: Additional request headers
            idempotency_key: Idempotency key for POST requests (auto-generated if None)
            retry_on_status: HTTP status codes that trigger a retry

        Returns:
            httpx.Response object

        Raises:
            APIConnectionError: On network failure or timeout
            AuthenticationError: On 401/403 responses
            ValidationError: On 400 responses
            RateLimitError: On 429 responses
            StendlyError: On other HTTP errors

        Example:
            >>> client = HTTPClient(...)
            >>> resp = client.request("POST", "/api/merchants/intents", json={...})
            >>> data = resp.json()
        """
        # Build request headers
        request_headers = dict(self._client.headers)
        if headers:
            request_headers.update(headers)

        if idempotency_key:
            request_headers["Idempotency-Key"] = idempotency_key

        url = urljoin(self.base_url, path)

        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                response = self._client.request(
                    method=method,
                    url=url,
                    json=json,
                    params=params,
                    headers=request_headers,
                )

                # Handle rate limiting (429) immediately - may retry if attempts left
                if response.status_code == 429:
                    if attempt < self.max_retries:
                        # Extract Retry-After if available
                        retry_after = response.headers.get("Retry-After")
                        if retry_after and retry_after.isdigit():
                            delay = int(retry_after)
                        else:
                            delay = self._calculate_backoff(attempt)
                        logger.warning(
                            f"Rate limited (429). Retrying in {delay}s "
                            f"(attempt {attempt + 1}/{self.max_retries})"
                        )
                        time.sleep(delay)
                        continue
                    else:
                        self._handle_error_response(response)

                # Client errors (4xx except 429) are not retryable
                if 400 <= response.status_code < 500:
                    self._handle_error_response(response)
                    return response  # unreachable due to raise in handler

                # Server errors may be retried
                if response.status_code in retry_on_status:
                    if attempt < self.max_retries:
                        delay = self._calculate_backoff(attempt)
                        logger.warning(
                            f"Request failed with {response.status_code}, "
                            f"retrying in {delay:.2f}s (attempt {attempt + 1}/{self.max_retries})"
                        )
                        time.sleep(delay)
                        continue
                    else:
                        self._handle_error_response(response)

                # Success or non-retryable error
                response.raise_for_status()
                return response

            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_error = e
                if attempt < self.max_retries:
                    delay = self._calculate_backoff(attempt)
                    logger.warning(f"Network error: {e}. Retrying in {delay:.2f}s")
                    time.sleep(delay)
                else:
                    break

        from stendly.exceptions import APIConnectionError

        if last_error:
            raise APIConnectionError(
                message=f"Request failed after {self.max_retries + 1} attempts",
                original_error=last_error,
            )
        raise APIConnectionError("Request failed with unknown error")

    def _calculate_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff with jitter."""
        base_delay = 2 ** attempt
        jitter = random.uniform(0, 0.1 * base_delay)
        return min(base_delay + jitter, 60.0)

    def _handle_error_response(self, response: httpx.Response) -> None:
        """Parse error and raise appropriate exception."""
        from stendly.exceptions import (
            AuthenticationError,
            ValidationError,
            RateLimitError,
            StendlyError,
        )

        request_id = response.headers.get("X-Request-Id")

        try:
            error_data = response.json()
            error_message = error_data.get("error", "Unknown error")
            error_details = error_data.get("details", {})
        except Exception:
            error_message = response.text or f"HTTP {response.status_code}"
            error_details = {}

        if response.status_code in (401, 403):
            raise AuthenticationError(error_message, response.status_code, request_id)
        elif response.status_code == 400:
            field = error_details.get("field") if isinstance(error_details, dict) else None
            raise ValidationError(error_message, field, error_details, 400, request_id)
        elif response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            retry_secs = int(retry_after) if retry_after and retry_after.isdigit() else None
            raise RateLimitError(error_message, retry_secs, 429, request_id)
        else:
            raise StendlyError(error_message, response.status_code, request_id)

    def generate_idempotency_key(self) -> str:
        """Generate UUID v4 idempotency key."""
        return str(uuid.uuid4())

    def close(self) -> None:
        """Close the synchronous client connection pool."""
        self._client.close()

    def __enter__(self) -> HTTPClient:
        """Context manager entry."""
        return self

    def __exit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[object],
    ) -> None:
        """Context manager exit."""
        self.close()


class AsyncHTTPClient:
    """
    Low-level asynchronous HTTP client with retry logic and idempotency support.

    Handles all HTTP communication with the Stendly API, including:
    - HTTP/2 support via httpx
    - Connection pooling for performance
    - Exponential backoff retry for transient failures
    - Automatic Idempotency-Key generation
    - Error response parsing

    This class is not intended for direct use by SDK consumers.

    Args:
        base_url: API base URL (e.g., "https://api.stendly.com")
        api_key: Merchant API key (st_live_* or st_test_*)
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts for failed requests
        http2: Enable HTTP/2 support

    Example:
        >>> client = AsyncHTTPClient(
        ...     base_url="https://api.stendly.com",
        ...     api_key="st_live_xxx",
        ...     timeout=10.0,
        ...     max_retries=2,
        ...     http2=True
        ... )
        >>> response = await client.request("GET", "/api/merchants/me")
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 10.0,
        max_retries: int = 2,
        http2: bool = True,
    ) -> None:
        """
        Initialize async HTTP client with configuration.

        Args:
            base_url: API base URL (with https://)
            api_key: Secret API key
            timeout: Request timeout in seconds
            max_retries: Max retry attempts for transient failures
            http2: Enable HTTP/2 protocol
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = Timeout(timeout=timeout)
        self.max_retries = max_retries

        # Configure connection pooling for performance
        limits = Limits(
            max_connections=100,
            max_keepalive_connections=20,
            keepalive_expiry=30.0,
        )

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            limits=limits,
            http2=http2,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": f"stendly-python-sdk/0.1.0",
                "X-Stendly-SDK": "python",
            },
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        idempotency_key: Optional[str] = None,
        retry_on_status: Tuple[int, ...] = (500, 502, 503, 504),
    ) -> httpx.Response:
        """
        Make async HTTP request with retry logic and error handling.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API endpoint path (e.g., "/api/merchants/intents")
            json: Request body as dict (will be JSON-encoded)
            params: Query parameters
            headers: Additional request headers
            idempotency_key: Idempotency key for POST requests (auto-generated if None)
            retry_on_status: HTTP status codes that trigger a retry

        Returns:
            httpx.Response object

        Raises:
            APIConnectionError: On network failure or timeout
            AuthenticationError: On 401/403 responses
            ValidationError: On 400 responses
            RateLimitError: On 429 responses
            StendlyError: On other HTTP errors
        """
        # Build request headers
        request_headers = dict(self._client.headers)
        if headers:
            request_headers.update(headers)

        if idempotency_key:
            request_headers["Idempotency-Key"] = idempotency_key

        url = urljoin(self.base_url, path)

        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                response = await self._client.request(
                    method=method,
                    url=url,
                    json=json,
                    params=params,
                    headers=request_headers,
                )

                # Handle rate limiting (429) immediately - may retry if attempts left
                if response.status_code == 429:
                    if attempt < self.max_retries:
                        # Extract Retry-After if available
                        retry_after = response.headers.get("Retry-After")
                        if retry_after and retry_after.isdigit():
                            delay = int(retry_after)
                        else:
                            delay = self._calculate_backoff(attempt)
                        logger.warning(
                            f"Rate limited (429). Retrying in {delay}s "
                            f"(attempt {attempt + 1}/{self.max_retries})"
                        )
                        await asyncio.sleep(delay)
                        continue
                    else:
                        self._handle_error_response(response)

                # Client errors (4xx except 429) are not retryable
                if 400 <= response.status_code < 500:
                    self._handle_error_response(response)
                    return response  # unreachable due to raise in handler

                # Server errors may be retried
                if response.status_code in retry_on_status:
                    if attempt < self.max_retries:
                        delay = self._calculate_backoff(attempt)
                        logger.warning(
                            f"Request failed with {response.status_code}, "
                            f"retrying in {delay:.2f}s (attempt {attempt + 1}/{self.max_retries})"
                        )
                        await asyncio.sleep(delay)
                        continue
                    else:
                        self._handle_error_response(response)

                # Success or non-retryable error
                response.raise_for_status()
                return response

            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_error = e
                if attempt < self.max_retries:
                    delay = self._calculate_backoff(attempt)
                    logger.warning(f"Network error: {e}. Retrying in {delay:.2f}s")
                    await asyncio.sleep(delay)
                else:
                    break

        from stendly.exceptions import APIConnectionError

        if last_error:
            raise APIConnectionError(
                message=f"Request failed after {self.max_retries + 1} attempts",
                original_error=last_error,
            )
        raise APIConnectionError("Request failed with unknown error")

    def _calculate_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff with jitter."""
        base_delay = 2 ** attempt
        jitter = random.uniform(0, 0.1 * base_delay)
        return min(base_delay + jitter, 60.0)

    def _handle_error_response(self, response: httpx.Response) -> None:
        """Parse error and raise appropriate exception."""
        from stendly.exceptions import (
            AuthenticationError,
            ValidationError,
            RateLimitError,
            StendlyError,
        )

        request_id = response.headers.get("X-Request-Id")

        try:
            error_data = response.json()
            error_message = error_data.get("error", "Unknown error")
            error_details = error_data.get("details", {})
        except Exception:
            error_message = response.text or f"HTTP {response.status_code}"
            error_details = {}

        if response.status_code in (401, 403):
            raise AuthenticationError(error_message, response.status_code, request_id)
        elif response.status_code == 400:
            field = error_details.get("field") if isinstance(error_details, dict) else None
            raise ValidationError(error_message, field, error_details, 400, request_id)
        elif response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            retry_secs = int(retry_after) if retry_after and retry_after.isdigit() else None
            raise RateLimitError(error_message, retry_secs, 429, request_id)
        else:
            raise StendlyError(error_message, response.status_code, request_id)

    def generate_idempotency_key(self) -> str:
        """Generate UUID v4 idempotency key."""
        return str(uuid.uuid4())

    async def aclose(self) -> None:
        """Close the async client connection pool."""
        await self._client.aclose()

    async def __aenter__(self) -> AsyncHTTPClient:
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