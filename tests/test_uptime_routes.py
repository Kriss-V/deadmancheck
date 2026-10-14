import uuid
from unittest.mock import MagicMock

from fastapi.testclient import TestClient


class FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value


class FakeSession:
    """Just enough of AsyncSession for the create-uptime-monitor route."""

    def __init__(self, monitor_count):
        self.monitor_count = monitor_count
        self.added = []

    async def execute(self, query):
        # _count_all_monitors runs two count queries (cron + uptime); split the total across them
        value, self.monitor_count = self.monitor_count, 0
        return FakeResult(value)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        pass


def make_client(plan, monitor_count):
    from app.main import app
    from app.database import get_db
    from app.services.auth import get_current_user

    user = MagicMock()
    user.id = uuid.uuid4()
    user.plan = plan
    session = FakeSession(monitor_count)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: session
    return TestClient(app, base_url="https://deadmancheck.io"), session


def teardown_function():
    from app.main import app
    app.dependency_overrides.clear()


def test_free_user_can_create_uptime_monitor():
    client, session = make_client("free", monitor_count=0)
    response = client.post("/api/uptime", json={"name": "Site", "url": "https://example.com"})
    assert response.status_code == 200
    assert len(session.added) == 1


def test_free_user_blocked_at_monitor_limit():
    client, session = make_client("free", monitor_count=20)
    response = client.post("/api/uptime", json={"name": "Site", "url": "https://example.com"})
    assert response.status_code == 402
    assert session.added == []
