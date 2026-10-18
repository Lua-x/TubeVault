#!/usr/bin/env bash
# Every check CI runs, in one go – run it before every commit: ./scripts/check.sh
# On Windows in Git Bash. Stops at the first failure. SKIP_E2E=1 leaves out the browser tests
# (they need ffmpeg and take about a minute).
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"

cd "$root/backend"
echo "== backend: ruff, mypy, pytest"
uv run ruff check .
uv run ruff format --check .
uv run mypy app
uv run pytest -q

cd "$root/frontend"
echo "== frontend: eslint, prettier, typescript, vitest, build"
npm run -s lint
npx prettier --check src e2e
npm run -s typecheck
npm test
npm run -s build

if [ "${SKIP_E2E:-}" != "1" ]; then
  echo "== browser tests (Playwright)"
  npm run -s e2e
fi

echo "ALL CHECKS GREEN"
