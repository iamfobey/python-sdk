"""
Terminals namespace for managing POS terminals.

This namespace provides methods to create and list POS terminals.
Terminals are used for point-of-sale scenarios where a merchant
wants to accept payments via QR code or other physical means.

Example:
    >>> from stendly import Client
    >>> client = Client(api_key="st_live_...")
    >>> 
    >>> # List all terminals
    >>> terminals = client.terminals.list()
    >>> for terminal in terminals:
    ...     print(f"{terminal.name}: {'active' if terminal.is_active else 'inactive'}")
    >>> 
    >>> # Create new terminal
    >>> new_terminal = client.terminals.create(name="Store Counter 1")
    >>> print(f"Created: {new_terminal.id}")
"""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from pydantic import ValidationError as PydanticValidationError

from .._http import HTTPClient, AsyncHTTPClient
from ..exceptions import ValidationError
from ..models import CreateTerminalRequest, Terminal


class TerminalsNamespace:
    """
    POS terminals management (synchronous).

    Provides methods to create and list payment terminals for
    point-of-sale scenarios. Terminals can be used to generate
    QR codes for in-person payments.

    This namespace is available as `client.terminals` on the synchronous Client.

    Note: Requires merchant verification status "verified".

    Example:
        >>> client = Client(api_key="st_live_...")
        >>> 
        >>> # List terminals
        >>> terminals = client.terminals.list()
        >>> print(f"Total terminals: {len(terminals)}")
        >>> 
        >>> # Create new
        >>> terminal = client.terminals.create(name="Main Counter")
        >>> print(f"New terminal ID: {terminal.id}")
    """

    def __init__(
        self,
        http_client: HTTPClient,
    ) -> None:
        """
        Initialize terminals namespace.

        Args:
            http_client: Synchronous HTTP client
        """
        self._http_client = http_client

    def create(
        self,
        name: str,
    ) -> Terminal:
        """
        Create a new POS terminal.

        Creates a terminal that can be used for point-of-sale payments.
        Terminals are associated with your merchant account and can
        be used to generate QR codes for in-person payments.

        Args:
            name: Terminal display name (e.g., "Store Counter 1", "Table 5")
                Max length: 100 characters

        Returns:
            Terminal: Created terminal object with ID, name, and creation time.

        Raises:
            AuthenticationError: Invalid API key or unauthorized
            ValidationError: Invalid name (empty or too long)
            RateLimitError: Too many requests
            APIConnectionError: Network failure
            StendlyError: Not verified (403) or other errors

        Example:
            >>> # Create a terminal for a physical location
            >>> terminal = client.terminals.create(name="Main Store Counter")
            >>> print(f"Terminal ID: {terminal.id}")
            >>> print(f"Active: {terminal.is_active}")

            >>> # Create terminal for restaurant tables
            >>> for i in range(1, 11):
            ...     client.terminals.create(name=f"Table {i}")

            Error handling:
            >>> from stendly import ValidationError
            >>> try:
            ...     client.terminals.create(name="")  # Empty name
            ... except ValidationError as e:
            ...     print(f"Validation failed: {e.message}")

        Note:
            - Terminals are always created as active (is_active=True)
            - Terminal ID can be used in payment intent creation to ensure
              only one pending intent exists per terminal at a time
            - All terminals for a merchant can be listed with list()
        """
        import logging
        logger = logging.getLogger(__name__)

        logger.info(f"Creating terminal: name={name}")

        # Validate input
        try:
            request = CreateTerminalRequest(name=name)
        except PydanticValidationError as e:
            err = e.errors()[0]
            field = str(err["loc"][0]) if err["loc"] else None
            raise ValidationError(
                message=err["msg"],
                field=field,
                details={"errors": e.errors()},
            ) from e

        response = self._http_client.request(
            method="POST",
            path="/api/b2b/merchants/terminals",
            json=request.model_dump(by_alias=True),
        )

        response_data = response.json()

        # Response contains: {"terminal": {...}}
        terminal_data = response_data.get("terminal", response_data)
        terminal = Terminal.model_validate(terminal_data)

        logger.info(f"Terminal created: id={terminal.id}, name={terminal.name}")

        return terminal

    def list(self) -> List[Terminal]:
        """
        List all terminals for the merchant.

        Returns all terminals associated with the authenticated merchant
        account. Useful for displaying terminal options in a dashboard
        or selecting a terminal for a new payment intent.

        Returns:
            List[Terminal]: List of terminal objects, ordered by creation
                date (newest first). Each terminal includes id, name,
                is_active, and created_at.

        Raises:
            AuthenticationError: Invalid API key
            APIConnectionError: Network failure
            StendlyError: Other API errors

        Example:
            >>> # Get all terminals
            >>> terminals = client.terminals.list()
            >>> 
            >>> # Display in table
            >>> for terminal in terminals:
            ...     status = "✓" if terminal.is_active else "✗"
            ...     print(f"{status} {terminal.name} (ID: {terminal.id})")
            >>> 
            >>> # Use terminal ID when creating intent
            >>> if terminals:
            ...     intent = client.intents.create(
            ...         amount_cents=1000,
            ...         order_id="order_123",
            ...         terminal_id=terminals[0].id
            ...     )

            Empty list:
            >>> terminals = client.terminals.list()
            >>> if not terminals:
            ...     print("No terminals yet. Create one first.")

        Note:
            - Only returns terminals for the authenticated merchant
            - Includes both active and inactive terminals
            - To deactivate a terminal, contact support (no API method yet)
        """
        import logging
        logger = logging.getLogger(__name__)

        logger.debug("Listing terminals")

        response = self._http_client.request(
            method="GET",
            path="/api/b2b/merchants/terminals",
        )

        response_data = response.json()

        # Response is a list directly
        terminals = [Terminal.model_validate(item) for item in response_data]

        logger.info(f"Retrieved {len(terminals)} terminals")

        return terminals


class AsyncTerminalsNamespace:
    """
    POS terminals management (asynchronous).

    Provides async methods to create and list payment terminals for
    point-of-sale scenarios. Terminals can be used to generate
    QR codes for in-person payments.

    This namespace is available as `client.terminals` on the asynchronous AsyncClient.

    Note: Requires merchant verification status "verified".

    Example:
        >>> client = AsyncClient(api_key="st_live_...")
        >>> 
        >>> # List terminals
        >>> terminals = await client.terminals.list()
        >>> print(f"Total terminals: {len(terminals)}")
        >>> 
        >>> # Create new
        >>> terminal = await client.terminals.create(name="Main Counter")
        >>> print(f"New terminal ID: {terminal.id}")
    """

    def __init__(
        self,
        async_http_client: AsyncHTTPClient,
    ) -> None:
        """
        Initialize async terminals namespace.

        Args:
            async_http_client: Asynchronous HTTP client
        """
        self._async_http_client = async_http_client

    async def create(
        self,
        name: str,
    ) -> Terminal:
        """
        Create a new POS terminal (async).

        Creates a terminal that can be used for point-of-sale payments.

        Args:
            name: Terminal display name (e.g., "Store Counter 1", "Table 5")

        Returns:
            Terminal: Created terminal object with ID, name, and creation time.

        Raises:
            AuthenticationError: Invalid API key or unauthorized
            ValidationError: Invalid name (empty or too long)
            RateLimitError: Too many requests
            APIConnectionError: Network failure
            StendlyError: Not verified (403) or other errors

        Example:
            >>> import asyncio
            >>> from stendly import AsyncClient
            >>> 
            >>> async def setup_terminals():
            ...     client = AsyncClient(api_key="st_live_...")
            ...     terminal = await client.terminals.create(name="Counter 1")
            ...     return terminal
            >>> asyncio.run(setup_terminals())
        """
        # Validate input
        try:
            request = CreateTerminalRequest(name=name)
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
            path="/api/b2b/merchants/terminals",
            json=request.model_dump(by_alias=True),
        )

        response_data = response.json()
        terminal_data = response_data.get("terminal", response_data)
        return Terminal.model_validate(terminal_data)

    async def list(self) -> List[Terminal]:
        """
        List all terminals for the merchant (async).

        Returns all terminals associated with the authenticated merchant
        account.

        Returns:
            List[Terminal]: List of terminal objects, ordered by creation
                date (newest first).

        Raises:
            AuthenticationError: Invalid API key
            APIConnectionError: Network failure
            StendlyError: Other API errors

        Example:
            >>> import asyncio
            >>> from stendly import AsyncClient
            >>> 
            >>> async def show_terminals():
            ...     client = AsyncClient(api_key="st_live_...")
            ...     terminals = await client.terminals.list()
            ...     for t in terminals:
            ...         print(t.name)
            >>> asyncio.run(show_terminals())
        """
        response = await self._async_http_client.request(
            method="GET",
            path="/api/b2b/merchants/terminals",
        )

        response_data = response.json()
        return [Terminal.model_validate(item) for item in response_data]