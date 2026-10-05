# syntax=docker/dockerfile:1.7
# TubeVault – one image: the React frontend is built and served by the FastAPI backend.

ARG NODE_IMAGE=node:24-slim
ARG PYTHON_IMAGE=python:3.12-slim

# --- 0. Signing key of the Jellyfin repository (for jellyfin-ffmpeg) ------------------
# jellyfin-ffmpeg is the ffmpeg Jellyfin ships: hardware transcoding with VAAPI (Intel and
# AMD, drivers included) and NVENC (NVIDIA), for amd64 and arm64.
FROM --platform=$BUILDPLATFORM ${PYTHON_IMAGE} AS jellyfin-key
RUN python -c "import urllib.request as u; u.urlretrieve('https://repo.jellyfin.org/jellyfin_team.gpg.key', '/jellyfin.asc')"

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

COPY --from=jellyfin-key /jellyfin.asc /etc/apt/keyrings/jellyfin.asc
# Try the repository for this Debian release first, then bookworm.
RUN set -eux; \
    . /etc/os-release; \
    for suite in "$VERSION_CODENAME" bookworm; do \
      echo "deb [signed-by=/etc/apt/keyrings/jellyfin.asc] https://repo.jellyfin.org/debian $suite main" \
        > /etc/apt/sources.list.d/jellyfin.list; \
      if apt-get update && apt-get install -y --no-install-recommends jellyfin-ffmpeg7; then break; fi; \
    done; \
    ln -s /usr/lib/jellyfin-ffmpeg/ffmpeg /usr/local/bin/ffmpeg; \
    ln -s /usr/lib/jellyfin-ffmpeg/ffprobe /usr/local/bin/ffprobe; \
    ffmpeg -hide_banner -version | head -n 1; \
    rm -rf /var/lib/apt/lists/*

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
    PUID=1000 \
    PGID=1000 \
    TZ="Etc/UTC" \
    # Lets the NVIDIA Container Toolkit mount the video encoding libraries.
    NVIDIA_DRIVER_CAPABILITIES="compute,video,utility"

WORKDIR /app
COPY --from=backend-deps /app/.venv /app/.venv
COPY backend/alembic.ini ./
COPY backend/app ./app
COPY --from=frontend /src/dist ./app/static
COPY --chmod=755 docker/entrypoint.sh /usr/local/bin/entrypoint.sh

# 8823 by default; installs from before 1.0 keep 8096 unless PORT is set (app/core/ports.py).
EXPOSE 8823
VOLUME ["/config", "/media"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD ["python", "-m", "app", "healthcheck"]

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["python", "-m", "app"]
