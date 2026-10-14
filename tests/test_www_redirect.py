from fastapi.testclient import TestClient


def make_client():
    from app.main import app
    # Not used as a context manager, so the lifespan (DB, Redis, scheduler) doesn't run
    return TestClient(app, base_url="https://www.deadmancheck.io", follow_redirects=False)


def test_www_redirects_permanently_to_apex():
    response = make_client().get("/pricing")
    assert response.status_code == 301
    assert response.headers["location"] == "https://deadmancheck.io/pricing"


def test_www_redirect_keeps_query_string():
    response = make_client().get("/pricing?ref=hn")
    assert response.headers["location"] == "https://deadmancheck.io/pricing?ref=hn"


def test_apex_is_not_redirected():
    from app.main import app
    client = TestClient(app, base_url="https://deadmancheck.io", follow_redirects=False)
    response = client.get("/robots.txt")
    assert response.status_code != 301
