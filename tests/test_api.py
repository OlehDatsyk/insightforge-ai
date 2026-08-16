"""End-to-end tests against the FastAPI app (sections 23, 24, 47)."""
import json


def test_health_endpoint(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("ok", "degraded")
    assert set(data["providers"].keys()) == {"openai", "anthropic", "gemini"}


def test_providers_endpoint_lists_all_three_vendors(client):
    resp = client.get("/api/providers")
    assert resp.status_code == 200
    names = {p["name"] for p in resp.json()}
    assert names == {"openai", "anthropic", "gemini"}


def test_config_status_endpoint(client):
    resp = client.get("/api/config/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "limits" in data
    assert "max_agent_iterations" in data["limits"]


def test_create_research_without_providers_returns_503(client):
    resp = client.post("/api/research", json={"research_question": "What is quantum computing?", "mode": "quick"})
    assert resp.status_code == 503
    assert "provider" in resp.json()["detail"].lower()


def test_create_research_returns_201_with_populated_progress_log(client):
    """
    Regression test for a bug where POST /api/research always 500'd with
    "An unexpected server error occurred": ResearchSession.progress_log's
    ORM column default (`list`) is only applied by SQLAlchemy at INSERT
    time, not when the Python object is constructed, so calling
    session.add_progress(...) on a brand-new, not-yet-flushed session
    raised `TypeError: Value after * must be an iterable, not NoneType`.
    """
    from app import app
    from config import Settings

    def _configured_settings():
        return Settings(openai_api_key="test-key-for-this-test-only")

    app.dependency_overrides[__import__("config").get_settings] = _configured_settings
    try:
        resp = client.post("/api/research", json={"research_question": "What is the tallest building?", "mode": "quick"})
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "pending"
    assert len(data["progress_log"]) == 1
    assert data["progress_log"][0]["message"] == "Research session created"


def test_create_research_rejects_short_question(client):
    resp = client.post("/api/research", json={"research_question": "hi", "mode": "quick"})
    assert resp.status_code == 422


def test_list_research_empty(client):
    resp = client.get("/api/research")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_missing_research_returns_404(client):
    resp = client.get("/api/research/does-not-exist")
    assert resp.status_code == 404


def test_delete_missing_research_returns_404(client):
    resp = client.delete("/api/research/does-not-exist")
    assert resp.status_code == 404


async def test_unhandled_exception_reveals_detail_outside_production(client, monkeypatch):
    """
    Locally (app_env != "production"), an unhandled exception should surface
    its type/message in the response so the app is self-debuggable without
    needing to find a separate server console window. Tests the handler
    function directly (rather than round-tripping through TestClient) since
    Starlette's BaseHTTPMiddleware can wrap exceptions from mid-stack
    middleware in ways unrelated to this handler's own logic.
    """
    import app as app_module
    from starlette.requests import Request

    request = Request(scope={"type": "http", "method": "GET", "path": "/api/whatever", "headers": []})
    exc = ValueError("synthetic failure for test coverage")

    monkeypatch.setattr(app_module.settings, "app_env", "development")
    response = await app_module.unhandled_exception_handler(request, exc)
    assert response.status_code == 500
    body = json.loads(response.body)
    assert "ValueError" in body["detail"]
    assert "synthetic failure for test coverage" in body["detail"]

    monkeypatch.setattr(app_module.settings, "app_env", "production")
    response = await app_module.unhandled_exception_handler(request, exc)
    assert response.status_code == 500
    body = json.loads(response.body)
    assert body["detail"] == "An unexpected server error occurred."
    assert "ValueError" not in body["detail"]


def test_landing_page_loads(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "InsightForge" in resp.text


def test_routing_settings_roundtrip(client):
    resp = client.get("/api/settings/routing")
    assert resp.status_code == 200
    assert "primary" in resp.json()

    resp = client.post("/api/settings/routing", json={"planning": "auto"})
    assert resp.status_code == 200

    resp = client.post("/api/settings/routing", json={"planning": "not-a-real-provider"})
    assert resp.status_code == 400
