# syntax=docker/dockerfile:1.7
# TubeVault – one image: the React frontend is built and served by the FastAPI backend.

ARG NODE_IMAGE=node:24-slim
ARG PYTHON_IMAGE=python:3.12-slim
# Statically linked ffmpeg + ffprobe (amd64 and arm64), no apt packages needed.
ARG FFMPEG_IMAGE=mwader/static-ffmpeg:7.1

FROM ${FFMPEG_IMAGE} AS ffmpeg

# --- 1. Frontend ----------------------------------------------------------------
# Built once on the build machine's platform; the output is plain static files.
FROM --platform=$BUILDPLATFORM ${NODE_IMAGE} AS frontend
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- 2. Python dependencies -------------------------------------------------------
FROM ${PYTHON_IMAGE} AS backend-deps
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
RUN pip install --no-cache-dir "uv>=0.9,<1"
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# --- 3. Runtime -------------------------------------------------------------------
FROM ${PYTHON_IMAGE}

ARG VERSION=dev
LABEL org.opencontainers.image.title="TubeVault" \
      org.opencontainers.image.description="Self-hosted media server for YouTube content" \
      org.opencontainers.image.source="https://github.com/Lua-x/TubeVault" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later"

RUN groupadd --gid 1000 tubevault \
 && useradd --uid 1000 --gid tubevault --home-dir /config --no-create-home \
      --shell /usr/sbin/nologin tubevault

COPY --from=ffmpeg /ffmpeg /ffprobe /usr/local/bin/

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # yt-dlp updated at runtime lives here and wins over the bundled version.
    PYTHONPATH="/config/.runtime/python" \
    XDG_CACHE_HOME="/config/.cache" \
    DENO_DIR="/config/.cache/deno" \
    HOME="/tmp" \
    CONFIG_DIR="/config" \
    MEDIA_DIR="/media" \
    PORT=8096 \
    PUID=1000 \
    PGID=1000 \
    TZ="Etc/UTC"

WORKDIR /app
COPY --from=backend-deps /app/.venv /app/.venv
COPY backend/alembic.ini ./
COPY backend/app ./app
COPY --from=frontend /src/dist ./app/static
COPY --chmod=755 docker/entrypoint.sh /usr/local/bin/entrypoint.sh

EXPOSE 8096
VOLUME ["/config", "/media"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD ["python", "-c", "import os, urllib.request as u; u.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PORT', '8096'), timeout=4)"]

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["python", "-m", "app"]
