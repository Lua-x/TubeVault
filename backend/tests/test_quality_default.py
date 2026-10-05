"""Best available quality is the default – installs on the old default (1080p) move along,
limits chosen on purpose stay."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import make_engine, make_session_factory
from app.migrate import MIGRATIONS_DIR
from app.models import Setting


def _migrate(tmp_path: Path, app_settings: dict[str, Any] | None) -> Any:
    """A 1.0.1 database (schema 0013) with these settings, updated to the newest schema."""
    engine = make_engine(f"sqlite:///{tmp_path / 'tubevault.db'}")
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0013")
    sessions = make_session_factory(engine)
    if app_settings is not None:
        with sessions() as db:
            db.add(Setting(key="app", value=app_settings))
            db.commit()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    with sessions() as db:
        value = db.scalar(select(Setting.value).where(Setting.key == "app"))
    engine.dispose()
    return value


def _app_settings(max_height: int | None) -> dict[str, Any]:
    return {"downloads": {"container": "mkv", "max_height": max_height, "prefer_h264": True}}


def test_old_default_becomes_best_available(tmp_path: Path) -> None:
    value = _migrate(tmp_path, _app_settings(1080))
    assert value["downloads"] == {"container": "mkv", "max_height": None, "prefer_h264": True}


@pytest.mark.parametrize("max_height", [2160, 720, None])
def test_chosen_limits_stay(tmp_path: Path, max_height: int | None) -> None:
    assert _migrate(tmp_path, _app_settings(max_height)) == _app_settings(max_height)


def test_never_saved_settings_stay_unsaved(tmp_path: Path) -> None:
    assert _migrate(tmp_path, None) is None


def test_new_install_downloads_in_best_quality(admin: TestClient) -> None:
    assert admin.get("/api/settings").json()["downloads"]["max_height"] is None


def test_add_video_dialog_remembers_choices(admin: TestClient) -> None:
    choices = {"max_height": 2160, "container": "mkv"}
    user = admin.put("/api/auth/me/preferences", json={"add_video": choices}).json()
    assert user["preferences"]["add_video"] == choices
    # Sent as a whole: back to "Standard" for everything.
    user = admin.put("/api/auth/me/preferences", json={"add_video": {}}).json()
    assert user["preferences"]["add_video"] == {}
    bad = admin.put("/api/auth/me/preferences", json={"add_video": {"max_height": 999}})
    assert bad.status_code == 422
