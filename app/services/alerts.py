"""
Alert delivery: email, webhook, Slack, Discord, Telegram, PagerDuty.
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
        return

    monitor.alert_sent_at = datetime.now(timezone.utc)
    await db.commit()

    reason_text = {
        "missed_ping": f"No ping received within the grace period ({monitor.grace_seconds}s after due).",
        "explicit_fail": "The job reported an explicit failure.",
    }.get(reason, "The monitor has stopped responding.")

    subject = f"[DeadManCheck] {monitor.name} is DOWN"
    html_body = f"""
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
    text = f"⚠ {monitor.name} is DOWN\n\n{reason_text}\nLast ping: {monitor.last_ping_at or 'Never'}\n{settings.app_url}/monitors/{monitor.id}"

    to_email = monitor.alert_email or await _get_user_email(monitor, db)
    if to_email and settings.resend_api_key:
        resend.Emails.send({
            "from": settings.alert_from_email,
            "to": [to_email],
            "subject": subject,
            "html": html_body,
        })

    await _dispatch_channels(monitor, event="down", text=text)


async def maybe_send_recovery_alert(monitor: Monitor, db: AsyncSession) -> None:
    if not monitor.alert_on_recovery:
        return
    if not monitor.alert_sent_at:
        return

    monitor.alert_sent_at = None
    await db.commit()

    subject = f"[DeadManCheck] {monitor.name} recovered"
    html_body = f"""
<h2 style="color:#16a34a">✓ {monitor.name} is back UP</h2>
<p>A ping was received. The monitor is now healthy.</p>
<p><a href="{settings.app_url}/monitors/{monitor.id}">View monitor →</a></p>
"""
    text = f"✓ {monitor.name} is back UP\n{settings.app_url}/monitors/{monitor.id}"

    to_email = monitor.alert_email or await _get_user_email(monitor, db)
    if to_email and settings.resend_api_key:
        resend.Emails.send({
            "from": settings.alert_from_email,
            "to": [to_email],
            "subject": subject,
            "html": html_body,
        })

    await _dispatch_channels(monitor, event="up", text=text)


async def send_duration_anomaly_alert(monitor: Monitor, duration: float, db: AsyncSession) -> None:
    avg = monitor.avg_duration_seconds or 0
    subject = f"[DeadManCheck] {monitor.name} — duration anomaly"
    html_body = f"""
<h2 style="color:#d97706">⏱ {monitor.name} took longer than expected</h2>
<p>
  Duration: <strong>{duration:.1f}s</strong><br>
  Rolling average: {avg:.1f}s<br>
  Threshold: {monitor.duration_alert_pct}% of average
</p>
<p><a href="{settings.app_url}/monitors/{monitor.id}">View monitor →</a></p>
"""
    text = f"⏱ {monitor.name} took longer than expected\nDuration: {duration:.1f}s (avg: {avg:.1f}s)\n{settings.app_url}/monitors/{monitor.id}"

    try:
        to_email = monitor.alert_email or await _get_user_email(monitor, db)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"[alerts] failed to get email for duration anomaly: {e}")
        to_email = None
    if to_email and settings.resend_api_key:
        resend.Emails.send({
            "from": settings.alert_from_email,
            "to": [to_email],
            "subject": subject,
            "html": html_body,
        })

    await _dispatch_channels(monitor, event="duration_anomaly", text=text)


# ── Assertion alerts ──────────────────────────────────────────────────────────

async def send_assertion_failed_alert(monitor: Monitor, failures: list, payload: dict, db: AsyncSession) -> None:
    import json
    failure_lines = "\n".join(
        f"  • {f['field']} {f['op']} {f['value']} — got {f['actual']}"
        for f in failures
    )
    failure_html = "".join(
        f"<li><code>{f['field']} {f['op']} {f['value']}</code> — got <strong>{f['actual']}</strong></li>"
        for f in failures
    )

    subject = f"[DeadManCheck] {monitor.name} — assertion failed"
    html_body = f"""
<h2 style="color:#d97706">⚠ {monitor.name} — assertion failed</h2>
<p>The job ran successfully but its output failed your assertion rules:</p>
<ul style="font-family:monospace">{failure_html}</ul>
<p>Payload received: <code>{json.dumps(payload)[:500]}</code></p>
<p><a href="{settings.app_url}/monitors/{monitor.id}">View monitor →</a></p>
<hr>
<p style="color:#6b7280;font-size:12px">DeadManCheck.io — Cron job monitoring</p>
"""
    text = f"⚠ {monitor.name} — assertion failed\n\nFailed rules:\n{failure_lines}\n\n{settings.app_url}/monitors/{monitor.id}"

    to_email = monitor.alert_email or await _get_user_email(monitor, db)
    if to_email and settings.resend_api_key:
        resend.Emails.send({
            "from": settings.alert_from_email,
            "to": [to_email],
            "subject": subject,
            "html": html_body,
        })

    await _dispatch_channels(monitor, event="assertion_failed", text=text)


# ── Uptime alerts ─────────────────────────────────────────────────────────────

async def send_uptime_down_alert(monitor, status_code, error, db: AsyncSession) -> None:
    if monitor.alert_sent_at:
        return

    from datetime import datetime, timezone
    monitor.alert_sent_at = datetime.now(timezone.utc)
    await db.commit()

    reason = f"Status code: {status_code}" if status_code else f"Error: {error}"
    subject = f"[DeadManCheck] {monitor.name} is DOWN"
    html_body = f"""
<h2 style="color:#dc2626">⚠ {monitor.name} is DOWN</h2>
<p>{reason}</p>
<p>URL: <a href="{monitor.url}">{monitor.url}</a></p>
<hr>
<p style="color:#6b7280;font-size:12px">DeadManCheck.io — Uptime monitoring</p>
"""
    text = f"⚠ {monitor.name} is DOWN\n{reason}\nURL: {monitor.url}"

    to_email = monitor.alert_email or await _get_uptime_user_email(monitor, db)
    if to_email and settings.resend_api_key:
        resend.Emails.send({
            "from": settings.alert_from_email,
            "to": [to_email],
            "subject": subject,
            "html": html_body,
        })

    await _dispatch_uptime_channels(monitor, event="down", text=text)


async def maybe_send_uptime_recovery(monitor, db: AsyncSession) -> None:
    if not monitor.alert_on_recovery:
        return
    if not monitor.alert_sent_at:
        return

    monitor.alert_sent_at = None
    await db.commit()

    subject = f"[DeadManCheck] {monitor.name} is back UP"
    html_body = f"""
<h2 style="color:#16a34a">✓ {monitor.name} is back UP</h2>
<p>URL: <a href="{monitor.url}">{monitor.url}</a></p>
<p>Response time: {monitor.last_response_ms:.0f}ms</p>
"""
    text = f"✓ {monitor.name} is back UP\nURL: {monitor.url}"

    to_email = monitor.alert_email or await _get_uptime_user_email(monitor, db)
    if to_email and settings.resend_api_key:
        resend.Emails.send({
            "from": settings.alert_from_email,
            "to": [to_email],
            "subject": subject,
            "html": html_body,
        })

    await _dispatch_uptime_channels(monitor, event="up", text=text)


async def _dispatch_uptime_channels(monitor, event: str, text: str) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        if monitor.alert_webhook_url:
            try:
                await client.post(monitor.alert_webhook_url, json={"event": event, "monitor": {"name": monitor.name, "url": monitor.url}})
            except Exception:
                pass
        if monitor.slack_webhook_url:
            await _send_slack(client, monitor.slack_webhook_url, text)
        if monitor.discord_webhook_url:
            await _send_discord(client, monitor.discord_webhook_url, text)
        if monitor.telegram_bot_token and monitor.telegram_chat_id:
            await _send_telegram(client, monitor.telegram_bot_token, monitor.telegram_chat_id, text)
        if monitor.pagerduty_key and event == "down":
            await _send_pagerduty(client, monitor, event)
        if monitor.pagerduty_key and event == "up":
            await _resolve_pagerduty(client, monitor)


async def _get_uptime_user_email(monitor, db: AsyncSession) -> str | None:
    from sqlalchemy import select
    from app.models import User
    result = await db.execute(select(User.email).where(User.id == monitor.user_id))
    return result.scalar_one_or_none()


# ── Channel dispatcher ────────────────────────────────────────────────────────

async def _dispatch_channels(monitor: Monitor, event: str, text: str) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        if monitor.alert_webhook_url:
            await _send_webhook(client, monitor, event)

        if monitor.slack_webhook_url:
            await _send_slack(client, monitor.slack_webhook_url, text)

        if monitor.discord_webhook_url:
            await _send_discord(client, monitor.discord_webhook_url, text)

        if monitor.telegram_bot_token and monitor.telegram_chat_id:
            await _send_telegram(client, monitor.telegram_bot_token, monitor.telegram_chat_id, text)

        if monitor.pagerduty_key and event in ("down", "duration_anomaly", "assertion_failed"):
            await _send_pagerduty(client, monitor, event)

        if monitor.pagerduty_key and event == "up":
            await _resolve_pagerduty(client, monitor)


# ── Individual channel senders ────────────────────────────────────────────────

async def _send_webhook(client: httpx.AsyncClient, monitor: Monitor, event: str) -> None:
    payload = {
        "event": event,
        "monitor": {"id": str(monitor.id), "name": monitor.name},
    }
    try:
        await client.post(monitor.alert_webhook_url, json=payload)
    except Exception:
        pass


async def _send_slack(client: httpx.AsyncClient, webhook_url: str, text: str) -> None:
    try:
        await client.post(webhook_url, json={"text": text})
    except Exception:
        pass


async def _send_discord(client: httpx.AsyncClient, webhook_url: str, text: str) -> None:
    try:
        await client.post(webhook_url, json={"content": text})
    except Exception:
        pass


async def _send_telegram(client: httpx.AsyncClient, bot_token: str, chat_id: str, text: str) -> None:
    try:
        await client.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
        )
    except Exception:
        pass


async def _send_pagerduty(client: httpx.AsyncClient, monitor: Monitor, event: str) -> None:
    severity = "error" if event == "down" else "warning"
    summary = f"{monitor.name} is DOWN" if event == "down" else f"{monitor.name} duration anomaly"
    try:
        await client.post(
            "https://events.pagerduty.com/v2/enqueue",
            json={
                "routing_key": monitor.pagerduty_key,
                "event_action": "trigger",
                "dedup_key": str(monitor.id),
                "payload": {
                    "summary": summary,
                    "severity": severity,
                    "source": "DeadManCheck",
                    "custom_details": {"monitor_id": str(monitor.id), "monitor_name": monitor.name},
                },
            },
        )
    except Exception:
        pass


async def _resolve_pagerduty(client: httpx.AsyncClient, monitor: Monitor) -> None:
    try:
        await client.post(
            "https://events.pagerduty.com/v2/enqueue",
            json={
                "routing_key": monitor.pagerduty_key,
                "event_action": "resolve",
                "dedup_key": str(monitor.id),
            },
        )
    except Exception:
        pass


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_user_email(monitor: Monitor, db: AsyncSession) -> str | None:
    from sqlalchemy import select
    from app.models import User
    result = await db.execute(select(User.email).where(User.id == monitor.user_id))
    return result.scalar_one_or_none()


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
