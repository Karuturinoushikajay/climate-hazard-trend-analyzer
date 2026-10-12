"""Keep tests on a throwaway TinyDB file and off the network."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="cha-pytest-"))
os.environ["STORE_PREFERENCE"] = "tinydb"
os.environ["DATA_DIR"] = str(_TMP)
os.environ["MONGO_URI"] = ""
os.environ["CORS_ORIGINS"] = "http://localhost:43123"

import pytest


@pytest.fixture(autouse=True)
def _quiet_rate_limit():
    from app.limiter import limiter

    previous = limiter.enabled
    limiter.enabled = False
    yield
    limiter.enabled = previous


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.db.store import get_store
    from app.main import app

    get_store().clear()
    with TestClient(app) as test_client:
        yield test_client
