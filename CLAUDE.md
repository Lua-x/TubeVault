# CLAUDE.md

Guidance for Claude Code sessions in this repository. Commands and layout are in
[CONTRIBUTING.md](CONTRIBUTING.md); this file adds how we work and what keeps the app right.

## Working with the owner

- Answer in **German**, short and plain. Say what changed, what was tested, and what the owner
  has to do next. Report honestly what could not be tested (real YouTube downloads, real TVs,
  the owner's NAS).
- Work in steps and explain architecture decisions briefly. Ask before larger deviations or
  when a request is ambiguous – with a recommended option.
- Commit and push to `main` after each working step, and only when `./scripts/check.sh` is green.
  Conventional Commits (`feat:`, `fix:`, `docs:`, `perf:`, `chore(release):` …).
- The owner pushes release tags from **PowerShell**: give commands one per line, no `&&`.
- No paid services, no telemetry, no external services except YouTube and (optional)
  SponsorBlock. Offline-first.
- Never commit secrets, `.env` files, cookies, databases or downloaded media – look at
  `git status` before every commit.

## Commands

- Everything CI runs: `./scripts/check.sh` (Git Bash on Windows). `SKIP_E2E=1 ./scripts/check.sh`
  leaves out the browser tests. First time: `cd frontend && npm ci && npx playwright install chromium`,
  `cd backend && uv sync`; ffmpeg must be on the PATH for the demo videos.
- One backend test: `cd backend && uv run pytest -q tests/test_folders.py`
- One frontend test: `cd frontend && npx vitest run src/lib/sleepTimer.test.ts`
- Dev server with demo videos: see "Running it locally" in CONTRIBUTING.md.

## Rules that keep the app right

- **Languages**: the interface is German; code, comments, commit messages and docs are English
  (docs name German menus with a translation, e.g. **Einstellungen → Downloads** (settings →
  downloads)). Design is Apple-like: grouped settings, rounded pills, calm colours.
- **Database changes**: a new Alembic migration in `backend/app/migrations/versions` with the
  next number, named constraints like the existing ones and `app.db.UTCDateTime` for times. It
  must upgrade databases from every earlier release – `tests/test_updates.py` runs the real
  fixtures in `tests/fixtures/upgrades`.
- **Settings**: app-wide in `AppSettings` (`services/app_settings.py`, one JSON document),
  per user in `Preferences` (`schemas/auth.py`). Settings pages save each change by themselves.
- **Let the disks sleep**: browsing must not touch `/media`. Pictures come from the image cache
  in `/config/cache/images` (`services/image_cache.py`); don't add file checks to list, home or
  search endpoints. Only playback, downloads and maintenance read `/media`. Known exception:
  podcast feeds look at the files.
- **Downloads like Pinchflat**: `services/downloader.build_format` must keep choosing the same
  streams as Pinchflat's options – `test_same_choice_as_pinchflat` checks it.
- **Security**: every new API route needs a signed-in user unless it is meant to be public;
  `tests/test_security.py` calls every route without signing in. Kids profiles only see their
  channels – use `services/access.py` (`visible_videos`, `ensure_visible`).
- **Frontend**: data hooks in `src/api/queries.ts`, types in `src/lib/types.ts`, browser tests in
  `frontend/e2e/app.e2e.ts`. New user-facing behaviour gets a test.

## Releases

1. Version in five places: `backend/app/__init__.py`, `backend/pyproject.toml`,
   `backend/uv.lock` (the `tubevault` package), `frontend/package.json` and
   `frontend/package-lock.json` (top and `packages[""]`).
2. Notes in `docs/releases/vX.Y.Z.md` (New / Changed / Fixed / Upgrade notes, ending with the
   `docker compose pull && docker compose up -d` block); update the guides in `docs/`.
3. Gate green → commit → push → wait until CI, CodeQL and Docker image are green on GitHub.
4. The owner tags: `git tag -a vX.Y.Z -m "TubeVault vX.Y.Z"` and `git push origin vX.Y.Z`. The
   release workflow publishes the notes; the Docker workflow builds `ghcr.io/lua-x/tubevault`
   (`latest`, `X`, `X.Y`, `X.Y.Z`) for amd64 and arm64.

Patch versions for fixes without a migration, minor versions for features or migrations. Never
move a published tag – ship a new version instead. If GitHub reports "The job was not acquired
by Runner", that is a GitHub outage: re-run the failed jobs, nothing in the code to fix.
