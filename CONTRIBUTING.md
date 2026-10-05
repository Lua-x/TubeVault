# Contributing

Thanks for wanting to help! Bug reports and ideas are welcome as
[issues](https://github.com/Lua-x/TubeVault/issues). For security problems, please follow
[SECURITY.md](SECURITY.md) instead.

## Running it locally

```sh
# Backend (Python 3.12, uv)
cd backend
uv sync
CONFIG_DIR=./.dev/config MEDIA_DIR=./.dev/media uv run python -m app   # http://localhost:8823

# Demo videos without YouTube access (needs ffmpeg); progress and playlists go to the first
# admin – so sign in once beforehand
CONFIG_DIR=./.dev/config MEDIA_DIR=./.dev/media uv run python scripts/seed_demo.py

# Frontend (Node 24) – Vite dev server with a proxy to the backend
cd frontend
npm ci
npm run dev        # http://localhost:5173
```

## Checks

Everything CI runs must pass before a change is merged:

```sh
cd backend
uv run ruff check . && uv run ruff format --check .
uv run mypy app
uv run pytest

cd ../frontend
npm run lint            # ESLint, no warnings allowed
npx prettier --check src
npm run typecheck
npm test
npm run build
npm run e2e          # browser tests against a real server with demo videos
                     # (needs uv and ffmpeg; first time: npx playwright install chromium)
```

## Layout

```
backend/app/
  routers/      HTTP and WebSocket endpoints
  services/     yt-dlp, library and file names, subscriptions, RSS, search, SponsorBlock,
                transcoding, NFO, import, backups, notifications, DLNA, rooms, speech, auth
  workers/      download queue, subscription scheduler, transcoder, library tasks,
                media analysis, speech recognition
  models/       SQLAlchemy models; migrations/ (Alembic)
frontend/src/
  pages/ components/ hooks/ api/ lib/ tv/ audio/ offline/
docker/         entrypoint
docs/           guides and release notes
```

## Conventions

- Commits follow [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`,
  `docs:`, …).
- Database changes come as a new Alembic migration in `backend/app/migrations/versions`; they
  must work on databases from every earlier version (CI tests upgrades from older releases).
- The interface is German; code, comments, commit messages and documentation are English.
- Every release gets a tag (`v1.0.0`, …) and notes in `docs/releases/`. GitHub Actions builds the
  image for amd64 and arm64 from the tag and publishes the release.
- Never commit secrets, `.env` files, cookies or downloaded videos.
