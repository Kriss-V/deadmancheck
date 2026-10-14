import uuid
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

RULES = '[{"op": ">", "value": 0}]'


class FakeResult:
    def scalar(self):
        return 0  # monitor count — well under the free limit


class FakeSession:
    """Just enough of AsyncSession for the create-monitor route. Models are mocked in
    conftest.py, so the 'is the free assertion slot used?' query is stubbed in make_client."""

    def __init__(self):
        self.added = []

    async def execute(self, query):
        return FakeResult()

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        pass

    async def refresh(self, obj):
        obj.id = uuid.uuid4()


def make_client(plan, assertion_monitor_exists, monkeypatch):
    from app.main import app
    from app.database import get_db
    from app.routers import monitors
    from app.services.auth import get_current_user

    async def slot_available(user_id, db, exclude_monitor_id=None):
        return not assertion_monitor_exists

    monkeypatch.setattr(monitors, "_free_assertion_slot_available", slot_available)
    monkeypatch.setattr(monitors, "compute_next_expected", lambda monitor: None)

    user = MagicMock()
    user.id = uuid.uuid4()
    user.plan = plan
    user.email = "test@example.com"
    session = FakeSession()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: session
    return TestClient(app, base_url="https://deadmancheck.io"), session


def teardown_function():
    from app.main import app
    app.dependency_overrides.clear()


def test_free_user_can_create_first_monitor_with_assertions(monkeypatch):
    client, session = make_client("free", assertion_monitor_exists=False, monkeypatch=monkeypatch)
    response = client.post("/api/monitors", json={"name": "Export", "period_seconds": 86400, "assertions": RULES})
    assert response.status_code == 200
    assert len(session.added) == 1


def test_free_user_blocked_from_second_monitor_with_assertions(monkeypatch):
    client, session = make_client("free", assertion_monitor_exists=True, monkeypatch=monkeypatch)
    response = client.post("/api/monitors", json={"name": "Export", "period_seconds": 86400, "assertions": RULES})
    assert response.status_code == 402
    assert session.added == []


def test_new_monitor_form_offers_assertions_to_free_user_with_slot(monkeypatch):
    client, _ = make_client("free", assertion_monitor_exists=False, monkeypatch=monkeypatch)
    response = client.get("/monitors/new")
    assert response.status_code == 200
    assert 'id="addAssertionBtn"' in response.text


def test_new_monitor_form_hides_assertions_when_free_slot_used(monkeypatch):
    client, _ = make_client("free", assertion_monitor_exists=True, monkeypatch=monkeypatch)
    response = client.get("/monitors/new")
    assert response.status_code == 200
    assert 'id="addAssertionBtn"' not in response.text
