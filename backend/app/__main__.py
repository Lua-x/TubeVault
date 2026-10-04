"""Command line: `python -m app [serve|update-ytdlp|reset-password]`."""

from __future__ import annotations

import argparse
import contextlib
import getpass
import logging
import sys

from app.config import Settings
from app.logging_setup import setup_logging


def serve(settings: Settings) -> None:
    import os

    import uvicorn

    from app.core.lifecycle import register_server, restart_requested

    config = uvicorn.Config(
        "app.main:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        proxy_headers=True,
        forwarded_allow_ips=settings.forwarded_allow_ips,
        log_config=None,
        ws_ping_interval=20,
        timeout_graceful_shutdown=10,
    )
    server = uvicorn.Server(config)
    register_server(server)
    server.run()
    if restart_requested():
        logging.getLogger("app").info("TubeVault startet neu …")
        # Same PID (the container keeps running), fresh interpreter (new yt-dlp is imported).
        os.execv(sys.executable, [sys.executable, "-m", "app", "serve"])  # noqa: S606


def youtube_enabled_on_disk(settings: Settings) -> bool:
    """The setting, read before the server (and its migrations) starts; True if unknown."""
    import json
    import sqlite3

    database = settings.config_dir / "tubevault.db"
    if settings.database_url or not database.is_file():
        return True
    try:
        with contextlib.closing(sqlite3.connect(f"file:{database}?mode=ro", uri=True)) as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = 'app'").fetchone()
        value = json.loads(row[0]) if row else {}
    except (sqlite3.Error, ValueError, TypeError):
        return True
    return not (isinstance(value, dict) and value.get("youtube_enabled") is False)


def update_ytdlp(settings: Settings, only_if_enabled: bool) -> None:
    from app.services.ytdlp_updater import drop_outdated_runtime, pypi_reachable, update_ytdlp

    setup_logging(settings.log_level, None)
    drop_outdated_runtime(settings.runtime_dir)
    if only_if_enabled and not settings.ytdlp_auto_update:
        logging.getLogger("app").info("YTDLP_AUTO_UPDATE ist aus – kein Update.")
        return
    if only_if_enabled and not youtube_enabled_on_disk(settings):
        print("YouTube-Downloader ausgeschaltet – yt-dlp-Update übersprungen.")
        return
    if only_if_enabled and not pypi_reachable():
        # Offline start: don't wait for pip's retries, the library works without internet.
        print("Kein Internet – yt-dlp-Update übersprungen.")
        return
    result = update_ytdlp(settings.runtime_dir)
    print(result.message)


def reset_password(settings: Settings, username: str) -> int:
    from app.core.security import hash_password
    from app.db import make_engine, make_session_factory
    from app.migrate import run_migrations
    from app.services.auth import find_user

    engine = make_engine(settings.db_url)
    run_migrations(engine)
    with make_session_factory(engine)() as db:
        user = find_user(db, username)
        if user is None:
            print(f"Benutzer '{username}' nicht gefunden.", file=sys.stderr)
            return 1
        password = getpass.getpass("Neues Passwort: ")
        if len(password) < 8 or password != getpass.getpass("Wiederholen: "):
            print(
                "Passwörter stimmen nicht überein oder sind kürzer als 8 Zeichen.", file=sys.stderr
            )
            return 1
        user.password_hash = hash_password(password)
        user.sessions.clear()
        db.commit()
    print("Passwort geändert.")
    return 0


def reset_two_factor(settings: Settings, username: str) -> int:
    """For a lost phone when no other admin can reset it in the UI."""
    from app.db import make_engine, make_session_factory
    from app.migrate import run_migrations
    from app.services.auth import find_user
    from app.services.two_factor import disable

    engine = make_engine(settings.db_url)
    run_migrations(engine)
    with make_session_factory(engine)() as db:
        user = find_user(db, username)
        if user is None:
            print(f"Benutzer '{username}' nicht gefunden.", file=sys.stderr)
            return 1
        disable(db, user)
    print(f"Zwei-Faktor-Anmeldung für '{username}' ausgeschaltet.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="tubevault")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("serve", help="Start the web server (default)")
    update = sub.add_parser("update-ytdlp", help="Update yt-dlp in /config/.runtime")
    update.add_argument("--if-enabled", action="store_true", help="Respect YTDLP_AUTO_UPDATE")
    reset = sub.add_parser("reset-password", help="Set a new password for a user")
    reset.add_argument("username")
    reset_2fa = sub.add_parser("reset-2fa", help="Turn off two-factor login for a user")
    reset_2fa.add_argument("username")
    args = parser.parse_args()

    settings = Settings()
    if args.command == "update-ytdlp":
        update_ytdlp(settings, args.if_enabled)
        return 0
    if args.command == "reset-password":
        return reset_password(settings, args.username)
    if args.command == "reset-2fa":
        return reset_two_factor(settings, args.username)
    serve(settings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
