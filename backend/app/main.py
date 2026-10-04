"""Application factory: API, WebSocket and the built frontend in one process."""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app import __version__
from app.config import Settings
from app.core.context import AppContext
from app.core.events import EventBus
from app.core.security import CSRF_HEADER
from app.db import make_engine, make_session_factory
from app.logging_setup import setup_logging
from app.migrate import run_migrations
from app.routers import (
    admin,
    auth,
    cast,
    channels,
    comments,
    dlna,
    downloads,
    family,
    history,
    home,
    imports,
    media,
    oidc,
    playback,
    playlists,
    podcasts,
    settings,
    subscriptions,
    system,
    users,
    videos,
    ws,
)
from app.services.app_settings import AnalysisOptions, TranscodeOptions, load_app_settings
from app.services.auth import bootstrap_admin, purge_expired_sessions
from app.services.backups import apply_staged_restore
from app.services.catalog import Catalog, YtDlpCatalog
from app.services.comments import CommentFetcher
from app.services.connectivity import Connectivity
from app.services.dlna import DlnaService
from app.services.downloader import Downloader, YtDlpDownloader
from app.services.importer import Importer
from app.services.notifications import Notifier, Sender
from app.services.notifications import send as send_notification
from app.services.oidc import OidcClient
from app.services.podcasts import AudioPrefetch
from app.services.rss import FeedFetcher, RssWatcher, fetch_feed_ids
from app.services.search import ensure_search_index
from app.services.subscriptions import SubscriptionChecker
from app.services.upgrades import QualityUpgrades
from app.workers.analyzer import MediaAnalyzer
from app.workers.download_manager import DownloadManager
from app.workers.library_tasks import LibraryTasks
from app.workers.scheduler import SubscriptionScheduler
from app.workers.transcoder import Transcoder

log = logging.getLogger(__name__)

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_PREFIX_RE = re.compile(r"^/[A-Za-z0-9._~/-]*$")
# PWA files must always be revalidated so updates reach installed apps.
_NO_CACHE_FILES = {"sw.js", "manifest.webmanifest"}

mimetypes.add_type("application/manifest+json", ".webmanifest")


class BasePathMiddleware:
    """Serves the app below BASE_PATH.

    Works whether the reverse proxy forwards the prefix (`/tubevault/api/...`) or strips it
    (`/api/...`).
    """

    def __init__(self, app: ASGIApp, base_path: str) -> None:
        self.app = app
        self.base = base_path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self.base and scope["type"] in ("http", "websocket"):
            path: str = scope["path"]
            if path == self.base and scope["type"] == "http":
                query = scope.get("query_string", b"").decode()
                target = f"{self.base}/" + (f"?{query}" if query else "")
                await RedirectResponse(target, status_code=308)(scope, receive, send)
                return
            if path.startswith(self.base + "/"):
                scope = dict(scope)
                scope["path"] = path[len(self.base) :]
                raw = scope.get("raw_path")
                if isinstance(raw, bytes) and raw.startswith(self.base.encode()):
                    scope["raw_path"] = raw[len(self.base) :]
        await self.app(scope, receive, send)


# Everything comes from TubeVault itself: no CDNs, fonts or trackers – and the UI keeps
# working without internet. Inline styles are needed by the player (video.js), blob: by
# HLS playback (media source + worker) and by videos saved on the device (the player
# fetches their subtitles and chapters from blob: URLs).
CONTENT_SECURITY_POLICY = (
    b"default-src 'self'; "
    b"script-src 'self'; "
    b"style-src 'self' 'unsafe-inline'; "
    b"img-src 'self' data: blob:; "
    b"media-src 'self' blob:; "
    b"font-src 'self' data:; "
    b"connect-src 'self' blob: ws: wss:; "
    b"worker-src 'self' blob:; "
    b"manifest-src 'self'; "
    b"object-src 'none'; "
    b"base-uri 'self'; "
    b"form-action 'self'; "
    b"frame-ancestors 'self'"
)


class SecurityMiddleware:
    """CSRF protection for the cookie-based API and a few defensive headers.

    Unsafe API requests must carry `X-Requested-With`. Browsers only allow that header on
    same-origin requests (cross-origin ones would need a CORS preflight we never answer).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope["path"]
        if scope["method"] in UNSAFE_METHODS and path.startswith("/api/"):
            headers = {k.decode().lower(): v for k, v in scope.get("headers", [])}
            # Bearer tokens aren't sent automatically by browsers, so they can't be forged.
            bearer = headers.get("authorization", b"").lower().startswith(b"bearer ")
            if CSRF_HEADER.lower() not in headers and not bearer:
                response = JSONResponse(
                    {"detail": f"Header {CSRF_HEADER} fehlt"}, status_code=status.HTTP_403_FORBIDDEN
                )
                await response(scope, receive, send)
                return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                existing = {k.lower() for k, _ in headers}
                for name, value in (
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"same-origin"),
                    (b"x-frame-options", b"SAMEORIGIN"),
                    (b"content-security-policy", CONTENT_SECURITY_POLICY),
                ):
                    if name not in existing:
                        headers.append((name, value))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


class ImmutableStaticFiles(StaticFiles):
    """Vite puts a content hash in asset names, so they can be cached forever."""

    def file_response(self, *args: object, **kwargs: object) -> Response:
        response = super().file_response(*args, **kwargs)  # type: ignore[arg-type]
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def _api_router() -> APIRouter:
    api = APIRouter(prefix="/api")
    for module in (
        system,
        auth,
        family,
        oidc,
        users,
        home,
        history,
        videos,
        comments,
        media,
        playback,
        cast,
        channels,
        playlists,
        podcasts,
        subscriptions,
        downloads,
        imports,
        settings,
        admin,
        ws,
    ):
        api.include_router(module.router)
    return api


def _mount_frontend(app: FastAPI, settings: Settings) -> None:
    static_dir = settings.static_dir
    index_file = static_dir / "index.html"
    if not index_file.is_file():
        log.warning("Frontend nicht gefunden (%s) – nur die API ist verfügbar.", static_dir)

        @app.get("/", include_in_schema=False)
        def no_frontend() -> dict[str, str]:
            return {"name": "TubeVault", "version": __version__, "detail": "Frontend not built"}

        return

    template = index_file.read_text(encoding="utf-8")
    root = static_dir.resolve()
    if (static_dir / "assets").is_dir():
        app.mount("/assets", ImmutableStaticFiles(directory=static_dir / "assets"), name="assets")

    def render_index(request: Request) -> HTMLResponse:
        prefix = settings.base_path
        forwarded = request.headers.get("x-forwarded-prefix", "").rstrip("/")
        if not prefix and forwarded and _PREFIX_RE.match(forwarded):
            prefix = forwarded
        html = template.replace("<head>", f'<head>\n    <base href="{prefix}/" />', 1)
        return HTMLResponse(html, headers={"Cache-Control": "no-cache"})

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str, request: Request) -> Response:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")
        if path:
            candidate = (root / path).resolve()
            if (
                candidate.is_relative_to(root)
                and candidate.is_file()
                and candidate != index_file.resolve()
            ):
                headers = {"Cache-Control": "no-cache"} if path in _NO_CACHE_FILES else None
                return FileResponse(candidate, headers=headers)
        return render_index(request)


def init_storage(settings: Settings) -> None:
    settings.config_dir.mkdir(parents=True, exist_ok=True)
    settings.media_dir.mkdir(parents=True, exist_ok=True)
    settings.temp_dir.mkdir(parents=True, exist_ok=True)


def create_app(
    settings: Settings | None = None,
    downloader: Downloader | None = None,
    catalog: Catalog | None = None,
    *,
    configure_logging: bool = True,
    scheduler_poll_interval: float = 30.0,
    connectivity: Connectivity | None = None,
    feeds: FeedFetcher | None = None,
    notification_sender: Sender | None = None,
    media_analysis: bool = True,
) -> FastAPI:
    settings = settings or Settings()
    init_storage(settings)
    if configure_logging:
        setup_logging(settings.log_level, settings.logs_dir)

    restored = apply_staged_restore(settings)
    engine = make_engine(settings.db_url)
    run_migrations(engine)
    ensure_search_index(engine)
    sessions = make_session_factory(engine)
    with sessions() as db:
        bootstrap_admin(db, settings)
        purge_expired_sessions(db)

    events = EventBus()
    catalog = catalog or YtDlpCatalog()
    downloader = downloader or YtDlpDownloader()
    connectivity = connectivity or Connectivity()
    notifier = Notifier(sessions, notification_sender or send_notification)
    manager = DownloadManager(
        settings, sessions, events, downloader, connectivity=connectivity, notifier=notifier
    )
    checker = SubscriptionChecker(
        settings,
        sessions,
        events,
        catalog,
        on_jobs_created=lambda _ids: manager.wake(),
        connectivity=connectivity,
        notifier=notifier,
    )
    scheduler = SubscriptionScheduler(
        settings,
        sessions,
        events,
        checker,
        catalog,
        poll_interval=scheduler_poll_interval,
        connectivity=connectivity,
        rss=RssWatcher(sessions, connectivity, feeds or fetch_feed_ids),
        notifier=notifier,
        upgrades=QualityUpgrades(
            sessions,
            settings.media_dir,
            downloader,
            connectivity,
            on_queued=lambda _ids: manager.wake(),
        ),
    )

    def connectivity_changed(online: bool) -> None:
        events.publish("system.connectivity", online=online)
        if online:
            manager.wake()
            scheduler.wake()

    connectivity.on_change = connectivity_changed

    def transcode_options() -> TranscodeOptions:
        with sessions() as db:
            return load_app_settings(db).transcoding

    transcoder = Transcoder(settings, transcode_options)

    def analysis_options() -> AnalysisOptions:
        with sessions() as db:
            return load_app_settings(db).analysis

    analyzer = MediaAnalyzer(settings, sessions, analysis_options)

    def file_replaced(video_id: int) -> None:
        transcoder.purge(video_id)
        analyzer.forget(video_id)

    def download_finished() -> None:
        scheduler.request_cleanup()
        analyzer.wake()

    manager.on_file_replaced = file_replaced
    manager.on_download_finished = download_finished
    library_tasks = LibraryTasks(settings, sessions, events)
    comment_fetcher = CommentFetcher(sessions, downloader, events, connectivity)
    podcast_prefetch = AudioPrefetch(transcoder)
    manager.on_comments_wanted = comment_fetcher.request
    importer = Importer(settings.media_dir, settings.import_dir, downloader)
    dlna_service = DlnaService(sessions, settings.port)
    ctx = AppContext(
        settings=settings,
        engine=engine,
        sessions=sessions,
        events=events,
        downloads=manager,
        catalog=catalog,
        checker=checker,
        scheduler=scheduler,
        transcoder=transcoder,
        library_tasks=library_tasks,
        importer=importer,
        connectivity=connectivity,
        notifier=notifier,
        oidc=OidcClient(settings),
        comments=comment_fetcher,
        podcasts=podcast_prefetch,
        dlna=dlna_service,
        analyzer=analyzer,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        events.bind(asyncio.get_running_loop())
        notifier.start()
        manager.start()
        scheduler.start()
        transcoder.start()
        await asyncio.to_thread(dlna_service.apply)
        if media_analysis:
            analyzer.start()
        if restored:
            library_tasks.verify_files()  # the backup may know files that are gone now
        else:
            library_tasks.backfill_nfo_if_needed()
        log.info("TubeVault %s läuft auf Port %s%s", __version__, settings.port, settings.base_path)
        try:
            yield
        finally:
            await asyncio.to_thread(dlna_service.stop)
            await asyncio.to_thread(analyzer.stop)
            await asyncio.to_thread(library_tasks.wait, 10.0)
            await asyncio.to_thread(transcoder.stop)
            await asyncio.to_thread(scheduler.stop)
            await asyncio.to_thread(manager.stop)
            comment_fetcher.shutdown()
            podcast_prefetch.shutdown()
            await asyncio.to_thread(notifier.stop)
            engine.dispose()

    app = FastAPI(
        title="TubeVault",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.ctx = ctx
    app.include_router(_api_router())
    # Outside /api: TVs know nothing of logins or CSRF headers (see app/routers/dlna.py).
    app.include_router(dlna.router)
    _mount_frontend(app, settings)
    app.add_middleware(SecurityMiddleware)
    app.add_middleware(BasePathMiddleware, base_path=settings.base_path)
    return app
