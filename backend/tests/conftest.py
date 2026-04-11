from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel

# Point Trove at a temp config dir BEFORE importing the app.
_TMP_DIR = tempfile.mkdtemp(prefix="trove-test-")
os.environ["TROVE_CONFIG_DIR"] = str(Path(_TMP_DIR) / "config")
os.environ["TROVE_DATA_DIR"] = str(Path(_TMP_DIR) / "data")
os.environ["TROVE_SESSION_SECRET"] = "test-secret-do-not-use-in-prod"
os.environ["TROVE_AI_ENABLED"] = "false"

from trove.config import get_settings  # noqa: E402
from trove.db import get_engine  # noqa: E402
from trove.main import create_app  # noqa: E402


@pytest.fixture
def app():
    # Reset DB between tests by dropping & recreating tables.
    engine = get_engine()
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    _ = get_settings()
    return create_app()


@pytest.fixture
def client(app) -> Generator[TestClient, None, None]:
    with TestClient(app) as c:
        yield c
