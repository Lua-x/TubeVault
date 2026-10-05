#!/bin/sh
# A fresh TubeVault with demo videos for the browser tests: migrate, create the admin, seed,
# serve. Needs uv, ffmpeg and a built frontend (npm run build).
set -eu
root="$(cd "$(dirname "$0")/../.." && pwd)"
data="$root/frontend/.e2e"
rm -rf "$data"
mkdir -p "$data/config" "$data/media"

export CONFIG_DIR="$data/config" MEDIA_DIR="$data/media" IMPORT_DIR="$data/import"
export STATIC_DIR="$root/frontend/dist" PORT="${E2E_PORT:-18823}" LOG_LEVEL=WARNING
export ADMIN_USER=admin ADMIN_PASSWORD=e2e-password-1 YTDLP_AUTO_UPDATE=false

cd "$root/backend"
# Migrations and the admin account, without starting the server yet.
uv run python -c "from app.main import create_app; create_app(configure_logging=False)"
DEMO_VIDEO_SECONDS=15 uv run python scripts/seed_demo.py > /dev/null
# Nothing may reach YouTube during the tests: no quality upgrades, no RSS checks.
uv run python - <<'PY'
from app.config import Settings
from app.db import make_engine, make_session_factory
from app.services.app_settings import load_app_settings, save_app_settings

settings = Settings()
with make_session_factory(make_engine(settings.db_url))() as db:
    options = load_app_settings(db)
    options.automation.upgrade_quality = False
    options.automation.rss = False
    save_app_settings(db, options)
PY
exec uv run python -m app serve
