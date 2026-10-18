"""YouTube cookies: kept only in /config, used only when YouTube asks for a sign-in."""

from __future__ import annotations

import logging
import os
import stat
import time
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.core.errors import LoginRequiredError, classify_error, needs_login
from app.models import ErrorKind
from app.services import backups, youtube_cookies
from app.services.downloader import with_login
from app.services.youtube_cookies import MAX_BYTES, CookieError, YouTubeCookies
from tests.conftest import FakeSender

SECRET = "geheimer-cookie-wert-1234"
WEBHOOK = {"service": "webhook", "url": "http://nas.local:8080/hook"}
# What yt-dlp says when YouTube wants a signed-in account.
AGE = "ERROR: [youtube] abc: Sign in to confirm your age. This video may be inappropriate"
MEMBERS = "ERROR: [youtube] abc: Join this channel to get access to members-only content"
PRIVATE = "ERROR: [youtube] abc: Private video. Sign in if you've been granted access"


def cookies_txt(*, sapisid: str = SECRET, login: bool = True, expires: int | None = None) -> bytes:
    until = int(time.time()) + 365 * 86400 if expires is None else expires

    def line(domain: str, name: str, value: str, http_only: bool = False) -> str:
        prefix = "#HttpOnly_" if http_only else ""
        return f"{prefix}{domain}\tTRUE\t/\tTRUE\t{until}\t{name}\t{value}"

    rows = [
        "# Netscape HTTP Cookie File",
        "",
        line(".youtube.com", "PREF", "f6=40000000"),
        line(".youtube.com", "SAPISID", sapisid),
        line(".bank.example", "session", "nicht-mitnehmen"),
        line(".google.com", "SID", "g1"),
    ]
    if login:
        rows.append(line(".youtube.com", "LOGIN_INFO", "AFmmF2sw", http_only=True))
    return ("\n".join(rows) + "\n").encode()


def _upload(client: TestClient, data: bytes) -> Any:
    return client.put("/api/admin/cookies", content=data, headers={"Content-Type": "text/plain"})


def _ctx(client: TestClient) -> Any:
    return client.app.state.ctx  # type: ignore[attr-defined]


def _signed_in_only(message: str) -> Any:
    """A yt-dlp run that YouTube only answers with cookies."""

    def run(login: dict[str, Any]) -> str:
        if not login:
            raise Exception(message)
        return "angemeldet"

    return run


def test_only_youtube_and_google_cookies_are_kept(tmp_path: Path) -> None:
    store = YouTubeCookies(tmp_path / "cookies")
    assert store.status().stored is False and not store.usable()

    state = store.save(cookies_txt())
    assert state.stored and state.count == 4 and state.problem is None
    assert state.uploaded_at is not None and state.expires_at is not None and store.usable()
    text = store.path.read_text(encoding="utf-8")
    assert SECRET in text and "#HttpOnly_.youtube.com" in text and "bank.example" not in text
    if os.name == "posix":
        assert stat.S_IMODE(store.path.stat().st_mode) == 0o600

    # Exported on Windows: byte order mark and CRLF line ends.
    windows = b"\xef\xbb\xbf" + cookies_txt().replace(b"\n", b"\r\n")
    assert store.save(windows).count == 4


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"nur Text", "keine YouTube-Cookies"),
        (b'[{"domain": ".youtube.com", "name": "SID"}]', "Netscape-Format"),
        (cookies_txt(login=False), "keine Anmeldung"),
        (cookies_txt(expires=int(time.time()) - 60), "schon abgelaufen"),
        (b"\xff\xfe\x00\x81", "keine Textdatei"),
        (b"x" * (MAX_BYTES + 1), "zu groß"),
    ],
    ids=["text", "json", "signed-out", "expired", "binary", "too-big"],
)
def test_unusable_files_are_refused(tmp_path: Path, data: bytes, message: str) -> None:
    store = YouTubeCookies(tmp_path / "cookies")
    with pytest.raises(CookieError, match=message):
        store.save(data)
    assert not store.path.exists()


@pytest.mark.parametrize(
    ("message", "login"),
    [
        (AGE, True),
        (MEMBERS, True),
        (PRIVATE, True),
        ("ERROR: [youtube:tab] This playlist is private", True),
        ("ERROR: [youtube] abc: Sign in to confirm you're not a bot", False),
        ("ERROR: [youtube] abc: Video unavailable", False),
        ("HTTP Error 429: Too Many Requests", False),
    ],
)
def test_what_counts_as_a_sign_in(message: str, login: bool) -> None:
    assert needs_login(Exception(message)) is login


def test_cookies_only_when_youtube_asks(tmp_path: Path) -> None:
    store = YouTubeCookies(tmp_path / "cookies")
    store.save(cookies_txt())
    calls: list[dict[str, Any]] = []

    def public(login: dict[str, Any]) -> str:
        calls.append(login)
        return "frei"

    assert with_login(store, public) == ("frei", False)
    assert calls == [{}]  # one run, no cookies

    def bot_check(login: dict[str, Any]) -> str:
        calls.append(login)
        raise Exception("ERROR: [youtube] abc: Sign in to confirm you're not a bot")

    with pytest.raises(Exception, match="not a bot"):
        with_login(store, bot_check)
    assert calls[-1] == {} and len(calls) == 2  # a rate limit: no second try with the account

    copies: list[Path] = []

    def age_restricted(login: dict[str, Any]) -> str:
        if not login:
            raise Exception(AGE)
        copy = Path(login["cookiefile"])
        copies.append(copy)
        assert copy != store.path and SECRET in copy.read_text(encoding="utf-8")
        return "angemeldet"

    assert with_login(store, age_restricted) == ("angemeldet", True)
    assert not copies[0].exists()  # yt-dlp worked on a copy, which is gone again
    assert store.status().used_at is not None


def test_without_usable_cookies_the_error_says_what_to_do(tmp_path: Path) -> None:
    store = YouTubeCookies(tmp_path / "cookies")
    with pytest.raises(Exception, match="members-only") as plain:
        with_login(None, _signed_in_only(MEMBERS))
    assert not isinstance(plain.value, LoginRequiredError)

    with pytest.raises(LoginRequiredError, match="Verwaltung → YouTube-Anmeldung") as missing:
        with_login(store, _signed_in_only(MEMBERS))
    assert "members-only" in str(missing.value)
    assert classify_error(missing.value) is ErrorKind.UNAVAILABLE  # not retried over and over

    store.save(cookies_txt())

    def still_members_only(login: dict[str, Any]) -> str:
        raise Exception(MEMBERS)

    with pytest.raises(LoginRequiredError, match="Auch mit den hinterlegten YouTube-Cookies"):
        with_login(store, still_members_only)
    assert store.status().problem is None  # not a member – the cookies are fine


def test_refreshed_cookies_are_kept_unless_new_ones_came(tmp_path: Path) -> None:
    store = YouTubeCookies(tmp_path / "cookies")
    store.save(cookies_txt())

    def refresh(login: dict[str, Any]) -> str:
        if not login:
            raise Exception(PRIVATE)
        copy = Path(login["cookiefile"])
        copy.write_text(copy.read_text(encoding="utf-8").replace("f6=40000000", "f6=neu"))
        return "angemeldet"

    with_login(store, refresh)
    assert "f6=neu" in store.path.read_text(encoding="utf-8")

    def replaced_meanwhile(login: dict[str, Any]) -> str:
        if not login:
            raise Exception(PRIVATE)
        store.save(cookies_txt(sapisid="neu-hochgeladen"))
        copy = Path(login["cookiefile"])
        copy.write_text(copy.read_text(encoding="utf-8").replace("f6=neu", "f6=alt"))
        return "angemeldet"

    with_login(store, replaced_meanwhile)
    text = store.path.read_text(encoding="utf-8")
    assert "neu-hochgeladen" in text and "f6=alt" not in text


def test_signed_out_cookies_are_reported_once(admin: TestClient, sender: FakeSender) -> None:
    admin.put("/api/admin/notifications", json=WEBHOOK)
    assert _upload(admin, cookies_txt()).status_code == 200
    store = _ctx(admin).cookies

    def signed_out(login: dict[str, Any]) -> str:
        if login:  # YouTube clears LOGIN_INFO: the session was ended
            copy = Path(login["cookiefile"])
            lines = copy.read_text(encoding="utf-8").splitlines()
            copy.write_text("\n".join(line for line in lines if "LOGIN_INFO" not in line))
        raise Exception(PRIVATE)

    with pytest.raises(LoginRequiredError):
        with_login(store, signed_out)
    assert admin.get("/api/admin/cookies").json()["problem"] == "rejected"
    assert "LOGIN_INFO" in store.path.read_text(encoding="utf-8")  # the upload stays as it was

    _ctx(admin).scheduler.cleanup()  # the hourly check doesn't report it again
    _ctx(admin).notifier.flush(force=True)
    assert [m.title for m in sender.messages] == ["YouTube-Cookies abgelaufen"]
    assert "YouTube hat die Anmeldung beendet" in sender.messages[0].body

    # Until new ones come, nothing is tried with them.
    with pytest.raises(LoginRequiredError, match="neue hochladen"):
        with_login(store, _signed_in_only(PRIVATE))
    assert _upload(admin, cookies_txt()).json()["problem"] is None
    assert with_login(store, _signed_in_only(PRIVATE)) == ("angemeldet", True)


def test_expiry_is_reported_once(
    admin: TestClient, sender: FakeSender, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin.put("/api/admin/notifications", json=WEBHOOK)
    expiry = datetime.now(UTC) + timedelta(days=30)
    _upload(admin, cookies_txt(expires=int(expiry.timestamp())))
    scheduler = _ctx(admin).scheduler
    scheduler.cleanup()
    _ctx(admin).notifier.flush(force=True)
    assert sender.messages == []

    later = expiry + timedelta(days=1)
    monkeypatch.setattr(youtube_cookies, "_now", lambda: later)
    assert admin.get("/api/admin/cookies").json()["problem"] == "expired"
    scheduler.cleanup()
    scheduler.cleanup()
    _ctx(admin).notifier.flush(force=True)
    assert [m.title for m in sender.messages] == ["YouTube-Cookies abgelaufen"]
    assert "abgelaufen" in sender.messages[0].body


def test_values_stay_out_of_the_api_backups_and_logs(
    admin: TestClient, settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    response = _upload(admin, cookies_txt())
    assert response.status_code == 200, response.text
    assert response.json() | {"uploaded_at": None, "expires_at": None} == {
        "stored": True,
        "count": 4,
        "uploaded_at": None,
        "expires_at": None,
        "used_at": None,
        "problem": None,
    }
    assert SECRET not in response.text and SECRET not in admin.get("/api/admin/cookies").text
    assert (settings.cookies_dir / "youtube.txt").is_file()

    refused = _upload(admin, cookies_txt(login=False))
    assert refused.status_code == 400 and "keine Anmeldung" in refused.json()["detail"]
    assert _upload(admin, b"").status_code == 400

    with_login(_ctx(admin).cookies, _signed_in_only(AGE))
    name = admin.post("/api/admin/backups").json()["name"]
    with zipfile.ZipFile(backups.backup_path(settings, name)) as archive:
        for member in archive.namelist():
            assert SECRET.encode() not in archive.read(member)
    assert SECRET not in caplog.text

    removed = admin.delete("/api/admin/cookies")
    assert removed.json()["stored"] is False
    assert not (settings.cookies_dir / "youtube.txt").exists()
