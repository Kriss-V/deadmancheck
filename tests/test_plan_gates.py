import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException


def make_user(plan: str):
    user = MagicMock()
    user.plan = plan
    return user


def make_body(**kwargs):
    body = MagicMock()
    body.slack_webhook_url = kwargs.get("slack_webhook_url", None)
    body.discord_webhook_url = kwargs.get("discord_webhook_url", None)
    body.telegram_bot_token = kwargs.get("telegram_bot_token", None)
    body.pagerduty_key = kwargs.get("pagerduty_key", None)
    body.assertions = kwargs.get("assertions", None)
    return body


# ── Plan limits ───────────────────────────────────────────────────────────────

def test_plan_limits_free():
    from app.routers.monitors import PLAN_LIMITS
    assert PLAN_LIMITS["free"] == 5


def test_plan_limits_pro_is_unlimited():
    from app.routers.monitors import PLAN_LIMITS
    assert PLAN_LIMITS["pro"] is None


def test_plan_limits_no_old_tiers():
    from app.routers.monitors import PLAN_LIMITS
    assert "developer" not in PLAN_LIMITS
    assert "team" not in PLAN_LIMITS
    assert "business" not in PLAN_LIMITS


# ── Alert plan gate ───────────────────────────────────────────────────────────

def test_free_blocks_slack():
    from app.routers.monitors import check_alert_plan
    with pytest.raises(HTTPException) as exc:
        check_alert_plan(make_user("free"), make_body(slack_webhook_url="https://hooks.slack.com/x"))
    assert exc.value.status_code == 402


def test_free_blocks_discord():
    from app.routers.monitors import check_alert_plan
    with pytest.raises(HTTPException) as exc:
        check_alert_plan(make_user("free"), make_body(discord_webhook_url="https://discord.com/api/webhooks/x"))
    assert exc.value.status_code == 402


def test_free_blocks_telegram():
    from app.routers.monitors import check_alert_plan
    with pytest.raises(HTTPException) as exc:
        check_alert_plan(make_user("free"), make_body(telegram_bot_token="token123"))
    assert exc.value.status_code == 402


def test_free_blocks_pagerduty():
    from app.routers.monitors import check_alert_plan
    with pytest.raises(HTTPException) as exc:
        check_alert_plan(make_user("free"), make_body(pagerduty_key="abc"))
    assert exc.value.status_code == 402


def test_free_blocks_assertions():
    from app.routers.monitors import check_alert_plan
    with pytest.raises(HTTPException) as exc:
        check_alert_plan(make_user("free"), make_body(assertions='[{"field":"count","op":"gt","value":"0"}]'))
    assert exc.value.status_code == 402


def test_free_allows_no_alerts():
    from app.routers.monitors import check_alert_plan
    check_alert_plan(make_user("free"), make_body())  # no exception


def test_free_allows_empty_assertions():
    from app.routers.monitors import check_alert_plan
    check_alert_plan(make_user("free"), make_body(assertions=None))  # no exception


def test_pro_allows_slack():
    from app.routers.monitors import check_alert_plan
    check_alert_plan(make_user("pro"), make_body(slack_webhook_url="https://hooks.slack.com/x"))


def test_pro_allows_pagerduty():
    from app.routers.monitors import check_alert_plan
    check_alert_plan(make_user("pro"), make_body(pagerduty_key="abc"))


def test_pro_allows_assertions():
    from app.routers.monitors import check_alert_plan
    check_alert_plan(make_user("pro"), make_body(assertions='[{"field":"count","op":"gt","value":"0"}]'))
