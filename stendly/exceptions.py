"""
Custom exceptions for Stendly SDK.

All exceptions inherit from StendlyError, which serves as the base exception
for all SDK-related errors. This allows users to catch all SDK errors with
a single except clause while also providing specific exception types for
different error categories.

Example:
    >>> from stendly import StendlyError, AuthenticationError
    >>> try:
    ...     client = Client(api_key="invalid")
    ...     client.intents.create(amount_cents=1000, order_id="order123")
    ... except AuthenticationError:
    ...     print("Invalid API key")
    ... except StendlyError as e:
    ...     print(f"SDK error: {e}")
"""

from __future__ import annotations


class StendlyError(Exception):
    """
    Base exception for all Stendly SDK errors.
    
    This exception serves as the root of the SDK's exception hierarchy.
    All other SDK-specific exceptions inherit from this class.
    
    Attributes:
        message: Human-readable error message
        status_code: HTTP status code (if applicable)
        request_id: Unique request identifier for debugging (if available)
    
    Example:
        >>> try:
        ...     client.intents.create(amount_cents=1000, order_id="123")
        ... except StendlyError as e:
        ...     print(f"Error: {e.message}")
        ...     print(f"Status: {e.status_code}")
    """
    
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        request_id: str | None = None,
    ) -> None:
        """
        Initialize StendlyError.
        
        Args:
            message: Human-readable error description
            status_code: HTTP status code returned by the API (optional)
            request_id: Request ID from response headers for support queries (optional)
        """
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.request_id = request_id
    
    def __str__(self) -> str:
        """Return string representation with status code if available."""
        if self.status_code:
            return f"[{self.status_code}] {self.message}"
        return self.message


class AuthenticationError(StendlyError):
    """
    Raised when API authentication fails (HTTP 401 or 403).
    
    This exception indicates that the provided API key is invalid,
    expired, or lacks necessary permissions.
    
    Example:
        >>> from stendly import Client, AuthenticationError
        >>> client = Client(api_key="invalid_key")
        >>> try:
        ...     client.intents.create(amount_cents=1000, order_id="123")
        ... except AuthenticationError as e:
        ...     print(f"Auth failed: {e.message}")
        ...     # Prompt user to check API key in dashboard
    """
    
    def __init__(
        self,
        message: str = "Authentication failed. Check your API key.",
        status_code: int = 401,
        request_id: str | None = None,
    ) -> None:
        """
        Initialize AuthenticationError.
        
        Args:
            message: Detailed authentication error message
            status_code: HTTP status code (always 401 or 403)
            request_id: Request ID for support
        """
        super().__init__(message, status_code, request_id)


class ValidationError(StendlyError):
    """
    Raised when request validation fails (HTTP 400).
    
    This exception contains detailed information about which fields
    failed validation and why. It helps developers correct their
    request parameters.
    
    Attributes:
        message: Error message
        field: Specific field that failed validation (if available)
        details: Additional error details from API response
    
    Example:
        >>> from stendly import Client, ValidationError
        >>> client = Client(api_key="st_live_...")
        >>> try:
        ...     client.intents.create(amount_cents=-100, order_id="123")
        ... except ValidationError as e:
        ...     print(f"Validation error: {e.message}")
        ...     if e.field:
        ...         print(f"Field: {e.field}")
    """
    
    def __init__(
        self,
        message: str,
        field: str | None = None,
        details: dict[str, str] | None = None,
        status_code: int = 400,
        request_id: str | None = None,
    ) -> None:
        """
        Initialize ValidationError.
        
        Args:
            message: Validation error description
            field: Name of the field that failed validation (optional)
            details: Additional error details from the API (optional)
            status_code: HTTP status code (always 400)
            request_id: Request ID for support
        """
        super().__init__(message, status_code, request_id)
        self.field = field
        self.details = details or {}
    
    def __str__(self) -> str:
        """Return string representation with field info if available."""
        base = super().__str__()
        if self.field:
            return f"{base} (field: {self.field})"
        return base


class RateLimitError(StendlyError):
    """
    Raised when API rate limit is exceeded (HTTP 429).
    
    This exception provides the Retry-After header value so developers
    can implement proper backoff strategies.
    
    Attributes:
        retry_after: Number of seconds to wait before retrying
        message: Error message with retry information
    
    Example:
        >>> from stendly import Client, RateLimitError
        >>> client = Client(api_key="st_live_...")
        >>> try:
        ...     for i in range(100):
        ...         client.intents.create(amount_cents=1000, order_id=f"order{i}")
        ... except RateLimitError as e:
        ...     print(f"Rate limited. Retry after {e.retry_after} seconds")
        ...     import time
        ...     time.sleep(e.retry_after)
    """
    
    def __init__(
        self,
        message: str = "Rate limit exceeded. Please slow down your requests.",
        retry_after: int | None = None,
        status_code: int = 429,
        request_id: str | None = None,
    ) -> None:
        """
        Initialize RateLimitError.
        
        Args:
            message: Rate limit error message
            retry_after: Seconds to wait before retrying (from Retry-After header)
            status_code: HTTP status code (always 429)
            request_id: Request ID for support
        """
        super().__init__(message, status_code, request_id)
        self.retry_after = retry_after
        
        if retry_after:
            self.message = f"{message} Retry after {retry_after} seconds."
    
    def __str__(self) -> str:
        """Return string representation with retry information."""
        return self.message


class APIConnectionError(StendlyError):
    """
    Raised when the SDK cannot connect to Stendly API.
    
    This exception covers network timeouts, DNS resolution failures,
    connection refused errors, and other network-related issues.
    
    Example:
        >>> from stendly import Client, APIConnectionError
        >>> client = Client(api_key="st_live_...")
        >>> try:
        ...     client.intents.create(amount_cents=1000, order_id="123")
        ... except APIConnectionError as e:
        ...     print(f"Connection failed: {e.message}")
        ...     print("Check internet connection or API endpoint")
    """
    
    def __init__(
        self,
        message: str = "Failed to connect to Stendly API. Check your internet connection.",
        original_error: Exception | None = None,
    ) -> None:
        """
        Initialize APIConnectionError.
        
        Args:
            message: Connection error description
            original_error: Original exception from httpx (for debugging)
        """
        super().__init__(message)
        self.original_error = original_error
        
        if original_error:
            self.message = f"{message} Original error: {type(original_error).__name__}"
    
    def __str__(self) -> str:
        """Return string representation."""
        return self.message


class SignatureVerificationError(StendlyError):
    """
    Raised when webhook signature verification fails.
    
    This exception indicates that the webhook payload signature does not
    match the expected signature, or the timestamp is too old (replay attack).
    Always verify webhooks before processing them.
    
    Attributes:
        reason: Specific reason for verification failure
    
    Example:
        >>> from stendly import Client
        >>> client = Client(api_key="st_live_...")
        >>> try:
        ...     event = client.webhooks.construct_event(
        ...         payload=raw_body,
        ...         signature_header=signature,
        ...         webhook_secret="whsec_..."
        ...     )
        ... except SignatureVerificationError as e:
        ...     print(f"Invalid webhook: {e.message}")
        ...     print(f"Reason: {e.reason}")
        ...     # Reject the webhook request immediately
    """
    
    def __init__(
        self,
        message: str = "Webhook signature verification failed.",
        reason: str | None = None,
    ) -> None:
        """
        Initialize SignatureVerificationError.
        
        Args:
            message: Error description
            reason: Specific reason (e.g., "signature_mismatch", "timestamp_expired")
        """
        super().__init__(message)
        self.reason = reason
        
        if reason:
            self.message = f"{message} Reason: {reason}"
    
    def __str__(self) -> str:
        """Return string representation with reason if available."""
        return self.message
