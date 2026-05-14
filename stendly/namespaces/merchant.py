"""
Merchant namespace for merchant account management and analytics.

This namespace provides methods to retrieve merchant profile information
and analytics statistics. All methods require merchant verification
(status: "verified").

Example:
    >>> from stendly import Client
    >>> client = Client(api_key="st_live_...")
    >>> 
    >>> # Get merchant profile
    >>> profile = client.merchant.get_profile()
    >>> print(f"Merchant: {profile.name}")
    >>> print(f"Payout address: {profile.payout_address}")
    >>> 
    >>> # Get statistics
    >>> stats = client.merchant.get_stats()
    >>> print(f"Total volume: ${stats.total_volume_cents / 100:.2f}")
    >>> print(f"Success rate: {stats.success_rate:.1f}%")
"""

from __future__ import annotations

import logging
from typing import Optional

from .._http import HTTPClient, AsyncHTTPClient
from ..models import (
    MerchantProfile,
    MerchantStats,
)


class MerchantNamespace:
    """
    Merchant account and analytics management (synchronous).

    Provides access to merchant profile information and 30-day
    transaction statistics. Useful for dashboard displays and
    account management.

    This namespace is available as `client.merchant` on the synchronous Client.

    Note: Requires merchant verification status "verified". Some
    operations may return 403 for unverified merchants.

    Example:
        >>> client = Client(api_key="st_live_...")
        >>> 
        >>> # Get profile
        >>> profile = client.merchant.get_profile()
        >>> print(f"Name: {profile.name}")
        >>> print(f"Payout: {profile.payout_address}")
        >>> if profile.webhook_url:
        ...     print(f"Webhook: {profile.webhook_url}")
        >>> 
        >>> # Get stats
        >>> stats = client.merchant.get_stats()
        >>> print(f"Volume: ${stats.total_volume_cents / 100:.2f}")
        >>> print(f"Transactions: {stats.total_transactions}")
        >>> print(f"Success rate: {stats.success_rate:.1f}%")
    """

    def __init__(
        self,
        http_client: HTTPClient,
    ) -> None:
        """
        Initialize merchant namespace.

        Args:
            http_client: Synchronous HTTP client
        """
        self._http_client = http_client

    def get_profile(self) -> MerchantProfile:
        """
        Retrieve current merchant profile.

        Fetches the authenticated merchant's profile information
        including payout address, webhook configuration, and API key.

        The API key (raw_api_key) is ONLY returned upon initial
        generation. Subsequent calls will return null for this field.
        Save the API key immediately when first generated — it cannot
        be retrieved again!

        Returns:
            MerchantProfile: Merchant profile object containing:
                - id: Merchant UUID
                - name: Business name
                - payout_address: USDC receiving address
                - webhook_url: Configured webhook endpoint (or None)
                - webhook_secret: Secret for webhook verification (or None)
                - raw_api_key: Full API key (only shown once, then None)

        Raises:
            AuthenticationError: Invalid API key or unauthorized
            APIConnectionError: Network failure
            StendlyError: Not verified (403) or other errors

        Example:
            >>> profile = client.merchant.get_profile()
            >>> print(f"Merchant ID: {profile.id}")
            >>> print(f"Business Name: {profile.name}")
            >>> print(f"Payout Address: {profile.payout_address}")
            >>> 
            >>> # Check webhook configuration
            >>> if profile.webhook_url:
            ...     print(f"Webhook URL: {profile.webhook_url}")
            ...     print(f"Webhook Secret: {profile.webhook_secret}")
            >>> else:
            ...     print("Webhook not configured")
            >>> 
            >>> # Save API key securely (only available once!)
            >>> if profile.raw_api_key:
            ...     # Save to environment variable or secure storage
            ...     import os
            ...     os.environ["STENDLY_API_KEY"] = profile.raw_api_key
            ...     print("API key saved (this is the ONLY time you'll see it)")

            Display info:
            >>> def display_profile(profile: MerchantProfile):
            ...     print("=" * 50)
            ...     print(f"Merchant: {profile.name}")
            ...     print(f"ID: {profile.id}")
            ...     print(f"Payout Address: {profile.payout_address[:8]}...{profile.payout_address[-4:]}")
            ...     print(f"Webhook: {profile.webhook_url or 'Not set'}")
            ...     print("=" * 50)

        Note:
            - The raw_api_key field is ONLY populated when the key is
              first generated via POST /api/b2b/merchants/generate-key
            - After that, it returns None for security
            - Webhook secret (whsec_...) is shown only once upon creation
            - Store both values in secure storage immediately
        """
        import logging
        logger = logging.getLogger(__name__)

        logger.debug("Fetching merchant profile")

        response = self._http_client.request(
            method="GET",
            path="/api/b2b/merchants/me",
        )

        response_data = response.json()
        profile = MerchantProfile.model_validate(response_data)

        logger.info(f"Retrieved merchant profile: name={profile.name}")

        return profile

    def get_stats(self) -> MerchantStats:
        """
        Retrieve merchant statistics for the last 30 days.

        Returns analytics data including total volume, transaction count,
        and daily breakdowns for the last 31 days (today + 30 prior).
        Only counts transactions with status "paid".

        Returns:
            MerchantStats: Statistics object containing:
                - total_volume_cents: Total payment volume in cents
                - total_transactions: Total transaction count
                - successful_transactions: Count of paid transactions
                - chart_data: DailyStats list (31 entries max)
                - success_rate: Calculated property (successful/total * 100)

        Raises:
            AuthenticationError: Invalid API key
            APIConnectionError: Network failure
            StendlyError: Not verified (403) or other errors

        Example:
            >>> stats = client.merchant.get_stats()
            >>> 
            >>> # Display summary
            >>> total_usd = stats.total_volume_cents / 100
            >>> print(f"Total Volume: ${total_usd:,.2f}")
            >>> print(f"Transactions: {stats.total_transactions}")
            >>> print(f"Success Rate: {stats.success_rate:.1f}%")
            >>> 
            >>> # Display daily breakdown (last 5 days)
            >>> print("\nLast 5 days:")
            >>> for day in stats.chart_data[-5:]:
            ...     date_str = day.date.strftime("%Y-%m-%d")
            ...     volume_usd = day.volume_cents / 100
            ...     print(f"  {date_str}: ${volume_usd:.2f} ({day.transactions} txns)")

            Output:
            >>> Total Volume: $5,000.00
            >>> Transactions: 150
            >>> Success Rate: 98.7%
            >>> 
            >>> Last 5 days:
            ...   2026-05-10: $150.00 (5 txns)
            ...   2026-05-09: $200.00 (7 txns)
            ...   2026-05-08: $180.00 (6 txns)
            ...   2026-05-07: $120.00 (4 txns)
            ...   2026-05-06: $250.00 (8 txns)

            Calculate averages:
            >>> if stats.chart_data:
            ...     avg_daily = sum(d.volume_cents for d in stats.chart_data) / len(stats.chart_data)
            ...     print(f"Avg daily volume: ${avg_daily / 100:.2f}")

        Note:
            - Period: last 30 days + today = 31 days maximum
            - Only includes transactions with status "paid"
            - Days without activity have zeros for volume and count
            - Data is ordered chronologically (oldest first)
            - Requires merchant verification
        """
        import logging
        logger = logging.getLogger(__name__)

        logger.debug("Fetching merchant statistics (30-day period)")

        response = self._http_client.request(
            method="GET",
            path="/api/b2b/merchants/stats",
        )

        response_data = response.json()
        stats = MerchantStats.model_validate(response_data)

        logger.info(
            f"Retrieved merchant stats: volume=${stats.total_volume_cents/100:.2f}, "
            f"txns={stats.total_transactions}"
        )

        return stats


class AsyncMerchantNamespace:
    """
    Merchant account and analytics management (asynchronous).

    Provides async access to merchant profile information and 30-day
    transaction statistics.

    This namespace is available as `client.merchant` on the asynchronous AsyncClient.

    Note: Requires merchant verification status "verified".

    Example:
        >>> client = AsyncClient(api_key="st_live_...")
        >>> 
        >>> # Get profile
        >>> profile = await client.merchant.get_profile()
        >>> print(f"Name: {profile.name}")
        >>> 
        >>> # Get stats
        >>> stats = await client.merchant.get_stats()
        >>> print(f"Volume: ${stats.total_volume_cents / 100:.2f}")
    """

    def __init__(
        self,
        async_http_client: AsyncHTTPClient,
    ) -> None:
        """
        Initialize async merchant namespace.

        Args:
            async_http_client: Asynchronous HTTP client
        """
        self._async_http_client = async_http_client

    async def get_profile(self) -> MerchantProfile:
        """
        Retrieve current merchant profile (async).

        Fetches the authenticated merchant's profile information
        including payout address, webhook configuration, and API key.

        Returns:
            MerchantProfile: Merchant profile object.

        Raises:
            AuthenticationError: Invalid API key or unauthorized
            APIConnectionError: Network failure
            StendlyError: Not verified (403) or other errors

        Example:
            >>> import asyncio
            >>> from stendly import AsyncClient
            >>> 
            >>> async def main():
            ...     client = AsyncClient(api_key="st_live_...")
            ...     profile = await client.merchant.get_profile()
            ...     print(profile.name)
            >>> asyncio.run(main())
        """
        response = await self._async_http_client.request(
            method="GET",
            path="/api/b2b/merchants/me",
        )

        response_data = response.json()
        return MerchantProfile.model_validate(response_data)

    async def get_stats(self) -> MerchantStats:
        """
        Retrieve merchant statistics for the last 30 days (async).

        Returns analytics data including total volume, transaction count,
        and daily breakdowns for the last 31 days.

        Returns:
            MerchantStats: Statistics object.

        Raises:
            AuthenticationError: Invalid API key
            APIConnectionError: Network failure
            StendlyError: Not verified (403) or other errors

        Example:
            >>> import asyncio
            >>> from stendly import AsyncClient
            >>> 
            >>> async def show_stats():
            ...     client = AsyncClient(api_key="st_live_...")
            ...     stats = await client.merchant.get_stats()
            ...     print(f"Volume: ${stats.total_volume_cents / 100:.2f}")
            >>> asyncio.run(show_stats())
        """
        response = await self._async_http_client.request(
            method="GET",
            path="/api/b2b/merchants/stats",
        )

        response_data = response.json()
        return MerchantStats.model_validate(response_data)