"""The default port moved from 8096 to 8823 – without cutting off installs from before 1.0."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.config import Settings
from app.core.ports import DEFAULT_PORT, LEGACY_PORT, resolve_port
from app.db import make_engine, make_session_factory
from app.main import create_app
from app.migrate import MIGRATIONS_DIR
from app.models import User
from tests.conftest import HEADERS


def _settings(tmp_path: Path, **env: object) -> Settings:
    return Settings(
        config_dir=tmp_path / "config",
        media_dir=tmp_path / "media",
        static_dir=tmp_path / "static",
        **env,  # type: ignore[arg-type]
    )


def _database_from_0_9(settings: Settings, *, with_user: bool) -> None:
    """A database as TubeVault 0.9 left it (schema 0012)."""
    settings.config_dir.mkdir(parents=True)
    engine = make_engine(settings.db_url)
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0012")
    if with_user:
        with make_session_factory(engine)() as db:
            db.add(User(username="alt", password_hash="x", is_admin=True))
            db.commit()
    engine.dispose()


def _start(settings: Settings) -> TestClient:
    app = create_app(
        settings, configure_logging=False, media_analysis=False, speech_recognition=False
    )
    return TestClient(app, headers=HEADERS)


def test_new_installs_use_the_new_port(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    assert resolve_port(settings).port == DEFAULT_PORT == 8823
    with _start(settings) as client:
        assert settings.port == DEFAULT_PORT
        client.post("/api/auth/setup", json={"username": "admin", "password": "geheim123"})
        overview = client.get("/api/admin/overview").json()
        assert (overview["port"], overview["port_source"]) == (8823, "default")
    # Stays so after the first start, although the database now has a user.
    assert resolve_port(_settings(tmp_path)).source == "default"


def test_old_installs_keep_8096(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _database_from_0_9(settings, with_user=True)
    assert resolve_port(settings) == resolve_port(_settings(tmp_path))
    assert resolve_port(settings).port == LEGACY_PORT
    with _start(settings) as client:
        assert settings.port == LEGACY_PORT  # DLNA announces the port in use
        assert client.get("/api/health").status_code == 200
    # After the update the migration remembers it.
    again = resolve_port(_settings(tmp_path))
    assert (again.port, again.source) == (LEGACY_PORT, "legacy")
    # PORT always wins – that is how to move over.
    assert resolve_port(_settings(tmp_path, port=8823)).source == "env"


def test_unused_old_database_moves_over(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _database_from_0_9(settings, with_user=False)
    assert resolve_port(settings).port == DEFAULT_PORT
    with _start(settings):
        pass
    assert resolve_port(_settings(tmp_path)).port == DEFAULT_PORT


def test_unreadable_database_counts_as_new(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.config_dir.mkdir(parents=True)
    (settings.config_dir / "tubevault.db").write_bytes(b"not a database")
    assert resolve_port(settings).port == DEFAULT_PORT


def test_health_check_finds_the_port(tmp_path: Path) -> None:
    from app.__main__ import healthcheck

    settings = _settings(tmp_path)
    settings.runtime_dir.mkdir(parents=True)
    # Nothing listens there: unhealthy, not a crash.
    (settings.runtime_dir / "port").write_text("1")
    assert healthcheck(settings) == 1
