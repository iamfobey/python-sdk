"""
Data models for Stendly API responses and requests.

All models use Pydantic v2 for robust validation, serialization, and
type safety. Models automatically convert snake_case JSON responses
to PascalCase Python attributes via ConfigDict.

This module contains all request/response DTOs used by the SDK.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PaymentIntentStatus(str, Enum):
    """
    Payment intent status enumeration.
    
    Attributes:
        PENDING: Intent created, payment not yet received
        PAID: Payment completed successfully
        UNDERPAID: Payment received but amount is less than expected
        EXPIRED: Intent expired without payment
        CANCELLED: Intent was cancelled by merchant or system
    """
    
    PENDING = "pending"
    PAID = "paid"
    UNDERPAID = "underpaid"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class PaymentIntent(BaseModel):
    """
    Payment intent object representing a pending or completed payment.
    
    A payment intent is created by a merchant to request a specific
    amount from a customer. It contains escrow and destination addresses
    for the USDC transfer on Solana.
    
    Attributes:
        id: Unique identifier for the payment intent (UUID)
        order_id: Merchant's order reference (must be unique per merchant)
        expected_amount_cents: Amount requested in cents (e.g., $50.00 = 5000)
        reference_address: Generated escrow address for the payment (SPL token account)
        destination_address: Merchant's USDC receiving address
        status: Current status of the payment intent
        expires_at: ISO 8601 timestamp when the intent expires
    
    Example:
        >>> intent = PaymentIntent(
        ...     id="123e4567-e89b-12d3-a456-426614174000",
        ...     order_id="ORDER-2025-001",
        ...     expected_amount_cents=4999,
        ...     reference_address="7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
        ...     destination_address="E7g2wdh9Z7a5vZkpQmdRZaVJ5z9pK2P38a6GKxeJ2Hc8",
        ...     status=PaymentIntentStatus.PENDING,
        ...     expires_at="2026-05-10T11:00:00Z"
        ... )
    """
    
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        use_enum_values=True,
        populate_by_name=True,
    )
    
    id: UUID = Field(
        ...,
        description="Unique payment intent identifier (UUID v4)",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
    )
    order_id: str = Field(
        ...,
        alias="orderId",
        description="Merchant's order reference number (unique per merchant)",
        max_length=100,
        examples=["ORDER-2025-001", "invoice_12345"],
    )
    expected_amount_cents: int = Field(
        ...,
        alias="expectedAmountCents",
        description="Expected payment amount in cents (e.g., 4999 = $49.99)",
        gt=0,
        examples=[5000, 9999, 25000],
    )
    reference_address: str = Field(
        ...,
        alias="referenceAddress",
        description="Escrow address (SPL token account) for the payment",
        min_length=32,
        max_length=44,
        examples=["7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"],
    )
    destination_address: str = Field(
        ...,
        alias="destinationAddress",
        description="Merchant's USDC receiving address",
        min_length=32,
        max_length=44,
        examples=["E7g2wdh9Z7a5vZkpQmdRZaVJ5z9pK2P38a6GKxeJ2Hc8"],
    )
    paid_amount_cents: int = Field(
        0,
        alias="paidAmountCents",
        description="Amount actually paid in cents (0 if not yet paid)",
        ge=0,
        examples=[0, 5000],
    )
    status: PaymentIntentStatus = Field(
        ...,
        description="Current payment intent status (pending, paid, underpaid, expired, cancelled)",
    )
    expires_at: datetime = Field(
        ...,
        description="UTC timestamp when the intent expires (ISO 8601)",
        examples=["2026-05-10T11:00:00Z"],
        alias="expiresAt",
    )
    
    @field_validator("reference_address", "destination_address")
    @classmethod
    def validate_solana_address(cls, v: str) -> str:
        """
        Validate Solana address format (base-58 encoded, 32-44 chars).
        
        Args:
            v: Address string
            
        Returns:
            Validated address
            
        Raises:
            ValueError: If address is invalid
        """
        if not (32 <= len(v) <= 44):
            raise ValueError("Solana address must be 32-44 characters long")
        allowed_chars = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")
        if not all(c in allowed_chars for c in v):
            raise ValueError("Solana address contains invalid base58 characters")
        return v


class DailyStats(BaseModel):
    """
    Daily statistics entry for chart data.
    
    Attributes:
        date: Date for this entry (YYYY-MM-DD)
        volume_cents: Total payment volume in cents for this day
        transactions: Number of transactions for this day
    
    Example:
        >>> from datetime import date
        >>> stats = DailyStats(
        ...     date=date(2026, 5, 10),
        ...     volume_cents=15000,
        ...     transactions=5
        ... )
        >>> print(f"Volume: ${stats.volume_cents / 100:.2f}")
    """
    
    model_config = ConfigDict(
        populate_by_name=True,
    )
    
    date: datetime = Field(
        ...,
        description="Date for this statistics entry",
        examples=["2026-05-10T00:00:00Z"],
    )
    volume_cents: int = Field(
        ...,
        alias="volumeCents",
        description="Total volume in cents for this day",
        ge=0,
        examples=[15000, 25000],
    )
    transactions: int = Field(
        ...,
        description="Number of transactions for this day",
        ge=0,
        examples=[5, 12],
    )


class MerchantStats(BaseModel):
    """
    Merchant analytics and statistics (30-day period).
    
    Revenue and transaction metrics for the merchant dashboard.
    Includes daily chart data for visualization.
    
    Attributes:
        total_volume_cents: Total payment volume in cents for last 30 days
        total_transactions: Total number of transactions
        successful_transactions: Number of completed (paid) transactions
        chart_data: Daily breakdown for last 31 days (today + 30 prior)
    
    Example:
        >>> stats = MerchantStats(
        ...     total_volume_cents=50000,
        ...     total_transactions=150,
        ...     successful_transactions=148,
        ...     chart_data=[
        ...         DailyStats(date=datetime(...), volume_cents=1500, transactions=5)
        ...     ]
        ... )
        >>> print(f"Success rate: {stats.success_rate:.1f}%")
    """
    
    model_config = ConfigDict(
        populate_by_name=True,
    )
    
    total_volume_cents: int = Field(
        ...,
        alias="totalVolumeCents",
        description="Total payment volume in cents over the last 30 days",
        ge=0,
        examples=[50000, 1000000],
    )
    total_transactions: int = Field(
        ...,
        alias="totalTransactions",
        description="Total transaction count (last 30 days)",
        ge=0,
        examples=[150, 2500],
    )
    successful_transactions: int = Field(
        ...,
        alias="successfulTransactions",
        description="Number of successfully paid transactions",
        ge=0,
        examples=[148, 2480],
    )
    chart_data: List[DailyStats] = Field(
        default_factory=list,
        alias="chartData",
        description="Daily statistics for last 31 days (today + 30 days prior)",
    )
    
    @property
    def success_rate(self) -> float:
        """
        Calculate payment success rate as percentage.
        
        Returns:
            Success rate (0-100). Returns 0 if no transactions.
        
        Example:
            >>> stats = MerchantStats(total_transactions=100, successful_transactions=98)
            >>> print(f"Success rate: {stats.success_rate:.1f}%")
            Success rate: 98.0%
        """
        if self.total_transactions == 0:
            return 0.0
        return (self.successful_transactions / self.total_transactions) * 100
    
    @property
    def average_transaction_cents(self) -> float:
        """
        Calculate average transaction amount in cents.
        
        Returns:
            Average transaction amount. Returns 0 if no successful transactions.
        
        Example:
            >>> stats = MerchantStats(
            ...     total_volume_cents=50000,
            ...     successful_transactions=100
            ... )
            >>> print(f"Avg: ${stats.average_transaction_cents / 100:.2f}")
            Avg: $50.00
        """
        if self.successful_transactions == 0:
            return 0.0
        return self.total_volume_cents / self.successful_transactions


class Terminal(BaseModel):
    """
    POS terminal object for in-person payments.
    
    Terminals are used for point-of-sale scenarios where a merchant
    wants to accept payments via QR code or other physical means.
    
    Attributes:
        id: Unique terminal identifier (UUID)
        name: Human-readable terminal name
        is_active: Whether terminal is accepting payments
        created_at: Timestamp when terminal was created
    
    Example:
        >>> terminal = Terminal(
        ...     id="123e4567-e89b-12d3-a456-426614174000",
        ...     name="Main Store Counter",
        ...     is_active=True,
        ...     created_at="2026-05-01T10:00:00Z"
        ... )
    """
    
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        populate_by_name=True,
    )
    
    id: UUID = Field(
        ...,
        description="Unique terminal identifier",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
    )
    name: str = Field(
        ...,
        description="Terminal display name (max 100 characters)",
        max_length=100,
        examples=["Main Store Counter", "Cash Register 1"],
    )
    is_active: bool = Field(
        ...,
        alias="isActive",
        description="Whether the terminal is active and accepting payments",
    )
    created_at: datetime = Field(
        ...,
        alias="createdAt",
        description="Terminal creation timestamp (ISO 8601)",
        examples=["2026-05-01T10:00:00Z"],
    )


class MerchantProfile(BaseModel):
    """
    Merchant profile information.
    
    Contains core merchant details including payout address and webhook
    configuration. Sensitive fields like API keys are only shown once
    upon generation.
    
    Attributes:
        id: Merchant identifier (UUID)
        name: Merchant business name
        payout_address: Merchant's USDC receiving address
        webhook_url: URL for payment notifications (optional)
        webhook_secret: Secret for verifying webhook signatures (whsec_...)
        raw_api_key: Full API key (st_live_...). Only returned once.
    
    Security Note:
        The raw_api_key and webhook_secret are ONLY returned upon
        initial generation. Save them immediately — they cannot be
        retrieved again from the API.
    """
    
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        populate_by_name=True,
    )
    
    id: UUID = Field(
        ...,
        description="Merchant unique identifier",
    )
    name: str = Field(
        ...,
        description="Merchant business name",
        max_length=200,
        examples=["My Online Store", "VPN Service Ltd"],
    )
    payout_address: str = Field(
        ...,
        alias="payoutAddress",
        description="USDC receiving address for receiving payments",
        min_length=32,
        max_length=44,
        examples=["E7g2wdh9Z7a5vZkpQmdRZaVJ5z9pK2P38a6GKxeJ2Hc8"],
    )
    webhook_url: Optional[str] = Field(
        None,
        alias="webhookUrl",
        description="Webhook endpoint URL for payment events",
        examples=["https://myshop.com/webhooks/stendly"],
    )
    webhook_secret: Optional[str] = Field(
        None,
        description="Secret for verifying webhook signatures (prefix: whsec_)",
        examples=["whsec_abc123def456789..."],
    )
    raw_api_key: Optional[str] = Field(
        None,
        description=(
            "Full API key for API authentication (prefix: st_live_). "
            "ONLY shown once upon generation. Store in secure location!"
        ),
        examples=["st_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"],
    )
    verification_status: Optional[str] = Field(
        None,
        alias="verificationStatus",
        description="KYB verification status (pending, verified, rejected)",
    )


class WebhookData(BaseModel):
    """
    Webhook event payload data.
    
    Contains core information about the event that occurred.
    
    Attributes:
        payment_intent_id: ID of the related payment intent
        order_id: Merchant's order reference
        amount_cents: Actual amount involved (may differ from expected)
        expected_amount_cents: Originally expected amount
        tx_signature: Solana transaction signature (if payment completed)
    """
    
    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
    )
    
    payment_intent_id: UUID = Field(
        ...,
        alias="paymentIntentId",
        description="Payment intent UUID that triggered this event",
    )
    order_id: str = Field(
        ...,
        alias="orderId",
        description="Merchant's order reference",
        max_length=100,
    )
    amount_cents: int = Field(
        ...,
        alias="amountCents",
        description="Actual amount in cents (may differ from expected)",
        ge=0,
    )
    expected_amount_cents: int = Field(
        ...,
        alias="expectedAmountCents",
        description="Originally expected payment amount in cents",
        ge=0,
    )
    tx_signature: Optional[str] = Field(
        None,
        alias="txSignature",
        description="Solana transaction signature (base-58 encoded)",
        examples=["5Ua6gE9bX9J4EyR7kf3p2..."],
    )


class WebhookEvent(BaseModel):
    """
    Complete verified webhook event object.
    
    Returned by construct_event after successful signature verification.
    Contains both event type and structured data payload.
    
    Attributes:
        event_type: Event type string (e.g., "payment_intent.succeeded")
        data: Event data payload with payment details
    
    Example:
        >>> event = client.webhooks.construct_event(
        ...     payload=raw_body,
        ...     signature_header=signature,
        ...     webhook_secret="whsec_..."
        ... )
        >>> print(f"Event: {event.event_type}")
        >>> print(f"Order: {event.data.order_id}")
    """
    
    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
    )
    
    event_type: str = Field(
        ...,
        alias="event",
        description="Webhook event type",
        examples=["payment_intent.succeeded", "payment_intent.failed"],
    )
    data: WebhookData = Field(
        ...,
        description="Event data containing payment details",
    )


# Request Models

class CreatePaymentIntentRequest(BaseModel):
    """
    Request model for creating a payment intent.
    
    Note: Idempotency-Key header is auto-generated if not provided
    to the create() method (not part of this model).
    
    Attributes:
        amount_cents: Amount to charge in cents (must be positive)
        order_id: Unique merchant order reference (max 100 chars)
        terminal_id: Optional terminal UUID for POS scenarios
    
    Example:
        >>> req = CreatePaymentIntentRequest(
        ...     amount_cents=4999,
        ...     order_id="ORDER-001"
        ... )
    """
    
    amount_cents: int = Field(
        ...,
        gt=0,
        description="Amount to charge in cents (e.g., 4999 = $49.99)",
        examples=[5000, 9999, 25000],
    )
    order_id: str = Field(
        ...,
        min_length=1,
        description="Unique order reference (max 100 characters)",
        max_length=100,
        examples=["ORDER-001", "invoice_2025_05"],
    )
    terminal_id: Optional[UUID] = Field(
        None,
        description="Optional terminal ID for POS/payment scenarios",
    )


class UpdateWebhookRequest(BaseModel):
    """Request model for updating webhook URL."""
    
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)
    
    webhook_url: str = Field(
        ...,
        alias="webhookUrl",
        description="New webhook endpoint URL (must be HTTPS in production)",
        examples=["https://myshop.com/webhooks/stendly"],
    )


class CreateTerminalRequest(BaseModel):
    """Request model for creating a POS terminal."""
    
    name: str = Field(
        ...,
        min_length=1,
        description="Terminal display name (max 100 characters)",
        max_length=100,
        examples=["Main Counter", "Table 5"],
    )
