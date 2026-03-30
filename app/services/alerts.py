"""
Alert delivery: email via Resend, optional webhook.
"""
import httpx
import resend
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Monitor

resend.api_key = settings.resend_api_key


async def send_down_alert(monitor: Monitor, reason: str, db: AsyncSession) -> None:
    from datetime import datetime, timezone

    if monitor.alert_sent_at:
        # Don't spam — only one alert per down event
        return

    monitor.alert_sent_at = datetime.now(timezone.utc)
    await db.commit()

    subject = f"[DeadManCheck] {monitor.name} is DOWN"
    reason_text = {
        "missed_ping": f"No ping received within the grace period ({monitor.grace_seconds}s after due).",
        "explicit_fail": "The job reported an explicit failure.",
    }.get(reason, "The monitor has stopped responding.")

    body = f"""
<h2 style="color:#dc2626">⚠ {monitor.name} is DOWN</h2>
<p>{reason_text}</p>
<p>
  Last ping: {monitor.last_ping_at.strftime('%Y-%m-%d %H:%M:%S UTC') if monitor.last_ping_at else 'Never'}<br>
  Expected every: {_period_human(monitor)}
</p>
<p><a href="{settings.app_url}/monitors/{monitor.id}">View monitor →</a></p>
<hr>
<p style="color:#6b7280;font-size:12px">DeadManCheck.io — Cron job monitoring</p>
"""

    to_email = monitor.alert_email or await _get_user_email(monitor, db)
    if to_email and settings.resend_api_key:
        resend.emails.send({
            "from": settings.alert_from_email,
            "to": [to_email],
            "subject": subject,
            "html": body,
        })

    if monitor.alert_webhook_url:
        await _send_webhook(monitor, "down", reason)


async def maybe_send_recovery_alert(monitor: Monitor, db: AsyncSession) -> None:
    if not monitor.alert_on_recovery:
        return

    monitor.alert_sent_at = None  # reset so future down events alert again
    await db.commit()

    subject = f"[DeadManCheck] {monitor.name} recovered"
    body = f"""
<h2 style="color:#16a34a">✓ {monitor.name} is back UP</h2>
<p>A ping was received. The monitor is now healthy.</p>
<p><a href="{settings.app_url}/monitors/{monitor.id}">View monitor →</a></p>
"""

    to_email = monitor.alert_email or await _get_user_email(monitor, db)
    if to_email and settings.resend_api_key:
        resend.emails.send({
            "from": settings.alert_from_email,
            "to": [to_email],
            "subject": subject,
            "html": body,
        })

    if monitor.alert_webhook_url:
        await _send_webhook(monitor, "up", "recovery")


async def send_duration_anomaly_alert(monitor: Monitor, duration: float, db: AsyncSession) -> None:
    subject = f"[DeadManCheck] {monitor.name} — duration anomaly"
    avg = monitor.avg_duration_seconds or 0
    body = f"""
<h2 style="color:#d97706">⏱ {monitor.name} took longer than expected</h2>
<p>
  Duration: <strong>{duration:.1f}s</strong><br>
  Rolling average: {avg:.1f}s<br>
  Threshold: {monitor.duration_alert_pct}% of average
</p>
<p><a href="{settings.app_url}/monitors/{monitor.id}">View monitor →</a></p>
"""
    to_email = monitor.alert_email or await _get_user_email(monitor, db)
    if to_email and settings.resend_api_key:
        resend.emails.send({
            "from": settings.alert_from_email,
            "to": [to_email],
            "subject": subject,
            "html": body,
        })


async def _get_user_email(monitor: Monitor, db: AsyncSession) -> str | None:
    from sqlalchemy import select
    from app.models import User
    result = await db.execute(select(User.email).where(User.id == monitor.user_id))
    return result.scalar_one_or_none()


async def _send_webhook(monitor: Monitor, event: str, reason: str) -> None:
    payload = {
        "event": event,
        "reason": reason,
        "monitor": {
            "id": str(monitor.id),
            "name": monitor.name,
        },
    }
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            await client.post(monitor.alert_webhook_url, json=payload)
        except Exception:
            pass  # webhook delivery is best-effort


def _period_human(monitor: Monitor) -> str:
    if monitor.schedule_type == "cron" and monitor.cron_expression:
        return f"cron: {monitor.cron_expression}"
    if monitor.period_seconds:
        s = monitor.period_seconds
        if s < 120:
            return f"{s}s"
        if s < 7200:
            return f"{s // 60}m"
        return f"{s // 3600}h"
    return "unknown"
