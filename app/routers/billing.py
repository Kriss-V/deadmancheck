"""
Stripe billing — checkout, customer portal, and webhook handler.

Flow:
  1. User clicks upgrade on pricing page → POST /billing/checkout?plan=developer
  2. We create a Stripe Checkout session and redirect to Stripe
  3. Stripe redirects back to /dashboard on success
  4. Stripe sends webhook → checkout.session.completed → we update user.plan
  5. User can manage/cancel via GET /billing/portal → redirects to Stripe portal
"""
import logging

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import User
from app.services.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])

stripe.api_key = settings.stripe_secret_key

PLAN_PRICE_IDS = {
    "developer": settings.stripe_price_developer,
    "team": settings.stripe_price_team,
    "business": settings.stripe_price_business,
}

# Maps Stripe price ID back to plan name — built at import time from settings.
PRICE_TO_PLAN = {v: k for k, v in PLAN_PRICE_IDS.items() if v}


@router.post("/checkout")
async def create_checkout(
    plan: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Redirect logged-in user to Stripe Checkout for the given plan."""
    price_id = PLAN_PRICE_IDS.get(plan)
    if not price_id:
        raise HTTPException(status_code=400, detail=f"Unknown plan: {plan}")

    # Create or reuse Stripe customer
    customer_id = user.stripe_customer_id
    if not customer_id:
        customer = stripe.Customer.create(email=user.email, metadata={"user_id": str(user.id)})
        customer_id = customer.id
        user.stripe_customer_id = customer_id
        await db.commit()

    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{settings.app_url}/dashboard?upgraded=1",
        cancel_url=f"{settings.app_url}/pricing",
        allow_promotion_codes=True,
        subscription_data={"metadata": {"user_id": str(user.id)}},
    )
    return RedirectResponse(session.url, status_code=303)


@router.get("/portal")
async def customer_portal(
    user: User = Depends(get_current_user),
):
    """Redirect to Stripe Customer Portal so user can manage/cancel their subscription."""
    if not user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No active subscription found.")

    session = stripe.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url=f"{settings.app_url}/dashboard",
    )
    return RedirectResponse(session.url, status_code=303)


@router.post("/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Receive and verify Stripe webhook events.
    Handles:
      - checkout.session.completed   → activate plan after first payment
      - customer.subscription.updated → plan change / renewal
      - customer.subscription.deleted → cancellation → downgrade to free
    """
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig, settings.stripe_webhook_secret)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    if event["type"] == "checkout.session.completed":
        await _handle_checkout_completed(event["data"]["object"], db)

    elif event["type"] == "customer.subscription.updated":
        await _handle_subscription_updated(event["data"]["object"], db)

    elif event["type"] == "customer.subscription.deleted":
        await _handle_subscription_deleted(event["data"]["object"], db)

    return {"status": "ok"}


# ── Private helpers ───────────────────────────────────────────────────────────

async def _get_user_by_customer(customer_id: str, db: AsyncSession) -> User | None:
    result = await db.execute(select(User).where(User.stripe_customer_id == customer_id))
    return result.scalar_one_or_none()


async def _handle_checkout_completed(session: dict, db: AsyncSession) -> None:
    customer_id = session.get("customer")
    subscription_id = session.get("subscription")
    user = await _get_user_by_customer(customer_id, db)
    if not user:
        logger.warning("checkout.session.completed: no user found for customer %s", customer_id)
        return

    # Fetch the subscription to get the price/plan
    sub = stripe.Subscription.retrieve(subscription_id)
    plan = _plan_from_subscription(sub)

    user.stripe_subscription_id = subscription_id
    user.plan = plan
    await db.commit()
    logger.info("User %s upgraded to %s (sub %s)", user.email, plan, subscription_id)


async def _handle_subscription_updated(sub: dict, db: AsyncSession) -> None:
    customer_id = sub.get("customer")
    user = await _get_user_by_customer(customer_id, db)
    if not user:
        return

    plan = _plan_from_subscription(sub)
    user.plan = plan
    user.stripe_subscription_id = sub["id"]
    await db.commit()
    logger.info("User %s plan updated to %s", user.email, plan)


async def _handle_subscription_deleted(sub: dict, db: AsyncSession) -> None:
    customer_id = sub.get("customer")
    user = await _get_user_by_customer(customer_id, db)
    if not user:
        return

    user.plan = "free"
    user.stripe_subscription_id = None
    await db.commit()
    logger.info("User %s downgraded to free (subscription cancelled)", user.email)

    if settings.resend_api_key:
        try:
            import resend
            resend.api_key = settings.resend_api_key
            resend.emails.send({
                "from": settings.alert_from_email,
                "to": [user.email],
                "subject": "Your DeadManCheck subscription has been cancelled",
                "html": f"""
<h2>Subscription cancelled</h2>
<p>Your DeadManCheck subscription has been cancelled and your account has been downgraded to the free plan.</p>
<h3>What this means</h3>
<ul>
  <li>You can keep up to <strong>5 monitors</strong></li>
  <li>Monitors above the free limit will stop alerting</li>
  <li>Your data and history are preserved</li>
</ul>
<p>Changed your mind? You can resubscribe at any time:</p>
<p><a href="{settings.app_url}/pricing">Resubscribe →</a></p>
<p>If you cancelled because something wasn't working or you have feedback, reply to this email — we'd love to hear from you.</p>
<p style="color:#6b7280;font-size:12px">DeadManCheck.io — Cron job monitoring</p>
""",
            })
        except Exception as e:
            logger.error(f"[billing] failed to send cancellation email: {e}")


def _plan_from_subscription(sub: dict) -> str:
    """Extract plan name from a Stripe subscription object."""
    try:
        price_id = sub["items"]["data"][0]["price"]["id"]
        return PRICE_TO_PLAN.get(price_id, "free")
    except (KeyError, IndexError):
        return "free"
