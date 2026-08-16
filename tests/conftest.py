"""
tests/conftest.py
==================
Shared pytest fixtures. Sets up an isolated, temporary SQLite database and
a clean environment BEFORE any application module is imported, so tests
never touch a developer's real .env / database.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

# --- Point the app at an isolated temp DB and clear any provider keys the
# developer's shell might have set, BEFORE importing anything app-related. ---
_tmp_dir = tempfile.mkdtemp(prefix="insightforge-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp_dir) / 'test.db'}"
os.environ["APP_ENV"] = "test"
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("GEMINI_API_KEY", None)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import get_settings  # noqa: E402


@pytest.fixture(autouse=True, scope="session")
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def client():
    """Fresh TestClient with a clean database for every test function.

    Tables are dropped and recreated before each test so sessions created
    by one test (e.g. the agent integration tests) never leak into another
    test's assertions (e.g. an "empty list" check).
    """
    from fastapi.testclient import TestClient

    from app import app
    from database import Base, engine, init_db

    Base.metadata.drop_all(bind=engine)
    init_db()
    with TestClient(app) as c:
        yield c
