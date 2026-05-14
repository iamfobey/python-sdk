# Example Applications

This directory contains complete example applications using Stendly SDK.

## Table of Contents

1. [Flask Webhook Receiver](#flask-webhook-receiver)
2. [FastAPI Create Intent](#fastapi-create-intent)
3. [Telegram Bot](#telegram-bot)
4. [Celery Payment Checker](#celery-payment-checker)
5. [Django Integration](#django-integration)
6. [AWS Lambda Function](#aws-lambda-function)

---

## Flask Webhook Receiver

Basic Flask app that receives Stendly webhooks and verifies signatures.

```python
# flask_app.py
from flask import Flask, request, abort
from stendly import Client, SignatureVerificationError
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize
app = Flask(__name__)
client = Client(api_key=os.getenv("STENDLY_API_KEY"))
WEBHOOK_SECRET = os.getenv("STENDLY_WEBHOOK_SECRET")

@app.route("/webhooks/stendly", methods=["POST"])
def stendly_webhook():
    # Get headers
    signature = request.headers.get("X-Stendly-Signature")
    if not signature:
        logger.warning("Missing signature header")
        abort(400, "Missing X-Stendly-Signature header")
    
    # Get raw payload
    payload = request.get_data()
    
    # Verify signature
    try:
        event = client.webhooks.construct_event(
            payload=payload,
            signature_header=signature,
            webhook_secret=WEBHOOK_SECRET
        )
    except SignatureVerificationError as e:
        logger.error(f"Signature verification failed: {e}")
        abort(400, "Invalid webhook signature")
    
    # Process event
    logger.info(f"Received event: {event.event_type}")
    handle_webhook_event(event)
    
    return "", 200

def handle_webhook_event(event):
    """Process verified webhook event."""
    from your_app import fulfill_order, notify_customer
    
    if event.event_type == "payment_intent.succeeded":
        order_id = event.data.order_id
        amount = event.data.amount_cents / 100
        logger.info(f"Payment succeeded: order={order_id}, amount=${amount:.2f}")
        fulfill_order(order_id)
    
    elif event.event_type == "payment_intent.failed":
        order_id = event.data.order_id
        logger.warning(f"Payment failed: {order_id}")
        notify_customer(order_id, status="failed")
    
    elif event.event_type == "payment_intent.expired":
        order_id = event.data.order_id
        logger.info(f"Payment expired: {order_id}")
        notify_customer(order_id, status="expired")

if __name__ == "__main__":
    app.run(port=5000, debug=True)
```

**Run:**

```bash
export STENDLY_API_KEY=st_live_...
export STENDLY_WEBHOOK_SECRET=whsec_...
python flask_app.py
```

---

## FastAPI Create Intent

FastAPI endpoint for creating payment intents.

```python
# fastapi_app.py
from fastapi import FastAPI, HTTPException, Depends, status
from pydantic import BaseModel
from stendly import AsyncClient, StendlyError
import os
from typing import Optional

app = FastAPI(title="Stendly Example API")
client = AsyncClient(api_key=os.getenv("STENDLY_API_KEY"))

class CreateIntentRequest(BaseModel):
    amount_cents: int
    order_id: str
    terminal_id: Optional[str] = None

@app.post("/api/intents")
async def create_intent(request: CreateIntentRequest):
    """
    Create a new payment intent.
    
    Returns escrow address for payment.
    """
    try:
        intent = await client.intents.create(
            amount_cents=request.amount_cents,
            order_id=request.order_id,
            terminal_id=request.terminal_id,
        )
        return {
            "id": str(intent.id),
            "reference_address": intent.reference_address,
            "destination_address": intent.destination_address,
            "expires_at": intent.expires_at.isoformat(),
            "status": intent.status,
        }
    except StendlyError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "error": str(e),
                "type": type(e).__name__,
                "request_id": e.request_id,
            }
        )

@app.get("/api/intents/{intent_id}")
async def get_intent(intent_id: str):
    """Retrieve payment intent by ID."""
    try:
        intent = await client.intents.retrieve(intent_id)
        return {
            "id": str(intent.id),
            "order_id": intent.order_id,
            "expected_amount_cents": intent.expected_amount_cents,
            "reference_address": intent.reference_address,
            "status": intent.status,
            "expires_at": intent.expires_at.isoformat(),
        }
    except StendlyError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    await client.aclose()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

**Run:**

```bash
uvicorn fastapi_app:app --reload
# POST http://localhost:8000/api/intents
```

---

## Telegram Bot (aiogram)

Complete Telegram bot that accepts payments via Stendly.

```python
# telegram_bot.py
import os
import asyncio
import time
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from stendly import AsyncClient

# Initialize
bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))
dp = Dispatcher()
stendly_client = AsyncClient(api_key=os.getenv("STENDLY_API_KEY"))

# User session storage (use Redis in production)
user_sessions = {}

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Welcome message."""
    await message.answer(
        "Welcome to Stendly Payment Bot!\n\n"
        "Commands:\n"
        "/pay <amount> - Create payment\n"
        "/status <intent_id> - Check payment status\n"
        "/help - Show help"
    )

@dp.message(Command("pay"))
async def cmd_pay(message: types.Message):
    """
    Create payment intent.
    Usage: /pay 5.50
    """
    try:
        # Parse amount
        parts = message.text.split()
        if len(parts) < 2:
            await message.answer("Usage: /pay <amount> (e.g., /pay 5.50)")
            return
        
        amount_usd = float(parts[1])
        amount_cents = int(amount_usd * 100)
        
        if amount_cents <= 0:
            await message.answer("Amount must be positive")
            return
        
        # Create intent
        user_id = message.from_user.id
        order_id = f"tg_{user_id}_{int(time.time())}"
        
        intent = await stendly_client.intents.create(
            amount_cents=amount_cents,
            order_id=order_id
        )
        
        # Store in session
        user_sessions[user_id] = {
            "intent_id": str(intent.id),
            "order_id": order_id,
            "amount_usd": amount_usd,
        }
        
        # Send payment instructions
        await message.answer(
            f"💰 Payment Request\n\n"
            f"Amount: ${amount_usd:.2f} USDC (Solana)\n\n"
            f"Send to this address:\n"
            f"`{intent.reference_address}`\n\n"
            f"⏱ Expires: {intent.expires_at.strftime('%H:%M')} UTC\n"
            f"Order ID: {order_id}",
            parse_mode="Markdown"
        )
        
    except ValueError:
        await message.answer("Invalid amount. Example: /pay 5.50")
    except StendlyError as e:
        await message.answer(f"Error: {e}")

@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    """Check payment status."""
    parts = message.text.split()
    if len(parts) < 2:
        # Check user's current intent
        session = user_sessions.get(message.from_user.id)
        if not session:
            await message.answer("No active payment. Use /pay first.")
            return
        intent_id = session["intent_id"]
    else:
        intent_id = parts[1]
    
    try:
        intent = await stendly_client.intents.retrieve(intent_id)
        
        status_emoji = {
            "pending": "⏳",
            "paid": "✅",
            "expired": "⏰",
            "cancelled": "❌",
            "underpaid": "⚠️",
        }.get(intent.status, "❓")
        
        await message.answer(
            f"{status_emoji} Status: {intent.status.upper()}\n"
            f"Amount: ${intent.expected_amount_cents / 100:.2f}\n"
            f"Order: {intent.order_id}\n"
            f"Expires: {intent.expires_at.strftime('%Y-%m-%d %H:%M UTC')}"
        )
        
        if intent.status == "paid":
            # Clear session
            user_sessions.pop(message.from_user.id, None)
            await message.answer("✅ Payment received! Your order is being processed.")
            
    except StendlyError as e:
        await message.answer(f"Error checking status: {e}")

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    """Show help."""
    help_text = """
**Stendly Payment Bot**

Available commands:
• /pay <amount> — Create payment (e.g., /pay 9.99)
• /status [intent_id] — Check payment status
• /help — Show this help

**How to pay:**
1. Use /pay to create intent
2. Copy the Solana address
3. Send USDC (Solana) to that address
4. Wait ~30 sec for confirmation
5. /status to verify

**Need USDC?**
Buy on Bybit, OKX, or use Jupiter swap.

Questions? @stendly_support
"""
    await message.answer(help_text, parse_mode="Markdown")

async def main():
    """Start bot."""
    print("Bot starting...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped")
    finally:
        asyncio.run(stendly_client.aclose())
```

**Run:**

```bash
pip install aiogram
export TELEGRAM_BOT_TOKEN=xxx
export STENDLY_API_KEY=st_live_...
python telegram_bot.py
```

---

## Celery Payment Checker

Background worker that checks payment status (alternative to webhooks).

```python
# tasks.py
from celery import Celery
from stendly import Client
import os
import time

celery = Celery(
    "stendly_tasks",
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
)

# Shared client (create once, reuse)
_client = None

def get_client():
    global _client
    if _client is None:
        _client = Client(api_key=os.getenv("STENDLY_API_KEY"))
    return _client

@celery.task(bind=True, max_retries=3)
def check_payment_status(self, intent_id):
    """
    Check payment intent status.
    
    Retry with exponential backoff on errors.
    Use webhooks instead when possible (more efficient).
    """
    client = get_client()
    
    try:
        intent = client.intents.retrieve(intent_id)
        
        if intent.status == "paid":
            # Payment received
            from orders import fulfill
            fulfill(intent.order_id, intent.expected_amount_cents)
            return {"status": "paid", "order_id": intent.order_id}
        
        elif intent.status in ["expired", "cancelled"]:
            # Failed
            from orders import cancel
            cancel(intent.order_id)
            return {"status": intent.status, "order_id": intent.order_id}
        
        else:
            # Still pending - retry
            raise self.retry(
                exc=Exception("Payment still pending"),
                countdown=min(2 ** self.request.retries, 60)
            )
    
    except StendlyError as e:
        if isinstance(e, (AuthenticationError, ValidationError)):
            # Don't retry - bad request
            raise
        else:
            # Network error - retry
            raise self.retry(exc=e, countdown=10)

# Schedule periodic check for old pending intents
@celery.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # Check all pending intents older than 5 min every 5 minutes
    sender.add_periodic_task(300.0, check_old_pending_intents.s())

@celery.task
def check_old_pending_intents():
    """Find old pending intents and check them."""
    from orders import get_old_pending_intents
    
    intents = get_old_pending_intents(minutes=5)
    for intent in intents:
        check_payment_status.delay(intent.id)
```

**Run Celery:**

```bash
celery -A tasks worker --loglevel=info
```

---

## Django Integration

Full Django + Stendly integration.

```python
# myproject/stendly.py
import os
from stendly import Client

STENDLY_CLIENT = Client(
    api_key=os.getenv("STENDLY_API_KEY"),
    environment=os.getenv("STENDLY_ENV", "mainnet")
)
```

```python
# myapp/views.py
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from stendly import SignatureVerificationError, StendlyError
from .stendly import STENDLY_CLIENT
import json
import logging

logger = logging.getLogger(__name__)

@csrf_exempt
@require_POST
def webhook(request):
    """Stendly webhook endpoint."""
    signature = request.headers.get("X-Stendly-Signature")
    if not signature:
        return HttpResponseBadRequest("Missing signature")
    
    try:
        event = STENDLY_CLIENT.webhooks.construct_event(
            payload=request.body,
            signature_header=signature,
            webhook_secret=os.getenv("STENDLY_WEBHOOK_SECRET"),
        )
    except SignatureVerificationError as e:
        logger.warning(f"Invalid webhook: {e}")
        return HttpResponseBadRequest("Invalid signature")
    
    # Process event
    process_webhook_event(event)
    
    return JsonResponse({"status": "ok"})

def process_webhook_event(event):
    """Handle webhook event."""
    from orders.models import Order
    
    if event.event_type == "payment_intent.succeeded":
        order_id = event.data.order_id
        amount = event.data.amount_cents / 100
        
        try:
            order = Order.objects.get(id=order_id)
            order.mark_paid(amount_cents=event.data.amount_cents)
            order.send_confirmation_email()
        except Order.DoesNotExist:
            logger.error(f"Order {order_id} not found")
```

---

## AWS Lambda

Serverless function for payment processing.

```python
# lambda_function.py
import json
import os
from stendly import Client, SignatureVerificationError

# Initialize client outside handler (connection reuse!)
client = Client(api_key=os.getenv("STENDLY_API_KEY"))
WEBHOOK_SECRET = os.getenv("STENDLY_WEBHOOK_SECRET")

def lambda_handler(event, context):
    """
    AWS Lambda handler for Stendly webhook.
    
    Deploy via:
    - AWS Console
    - Serverless Framework
    - AWS SAM
    """
    # API Gateway proxy integration
    headers = event.get("headers", {})
    body = event.get("body", "")
    
    if event.get("isBase64Encoded"):
        import base64
        body = base64.b64decode(body)
    
    signature = headers.get("x-stendly-signature") or headers.get("X-Stendly-Signature")
    
    if not signature:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Missing signature"})
        }
    
    try:
        webhook_event = client.webhooks.construct_event(
            payload=body,
            signature_header=signature,
            webhook_secret=WEBHOOK_SECRET,
        )
    except SignatureVerificationError as e:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": str(e)}),
        }
    
    # Process event
    process_event(webhook_event)
    
    return {
        "statusCode": 200,
        "body": json.dumps({"status": "ok"}),
    }

def process_event(event):
    """Handle verified webhook."""
    from your_app import fulfill
    
    if event.event_type == "payment_intent.succeeded":
        fulfill(event.data.order_id)
```

**serverless.yml (Serverless Framework):**

```yaml
service: stendly-webhook

provider:
  name: aws
  runtime: python3.11
  environment:
    STENDLY_API_KEY: ${env:STENDLY_API_KEY}
    STENDLY_WEBHOOK_SECRET: ${env:STENDLY_WEBHOOK_SECRET}

functions:
  webhook:
    handler: lambda_function.lambda_handler
    events:
      - http:
          path: /webhooks/stendly
          method: post
```

---

## Next Steps

- Read [API.md](API.md) for complete API reference
- Check [ADVANCED.md](ADVANCED.md) for advanced patterns
- Review [Security Best Practices](../README.md#security-best-practices)
- Join [Discord](https://discord.gg/stendly) for community support
