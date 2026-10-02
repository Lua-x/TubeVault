"""Command line: `python -m app [serve|update-ytdlp|reset-password]`."""

from __future__ import annotations

import argparse
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


def update_ytdlp(settings: Settings, only_if_enabled: bool) -> None:
    from app.services.ytdlp_updater import drop_outdated_runtime, update_ytdlp

    setup_logging(settings.log_level, None)
    drop_outdated_runtime(settings.runtime_dir)
    if only_if_enabled and not settings.ytdlp_auto_update:
        logging.getLogger("app").info("YTDLP_AUTO_UPDATE ist aus – kein Update.")
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


def main() -> int:
    parser = argparse.ArgumentParser(prog="tubevault")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("serve", help="Start the web server (default)")
    update = sub.add_parser("update-ytdlp", help="Update yt-dlp in /config/.runtime")
    update.add_argument("--if-enabled", action="store_true", help="Respect YTDLP_AUTO_UPDATE")
    reset = sub.add_parser("reset-password", help="Set a new password for a user")
    reset.add_argument("username")
    args = parser.parse_args()

    settings = Settings()
    if args.command == "update-ytdlp":
        update_ytdlp(settings, args.if_enabled)
        return 0
    if args.command == "reset-password":
        return reset_password(settings, args.username)
    serve(settings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
