#!/bin/sh
# Prepares /config and /media, then runs TubeVault as an unprivileged user.
#
# Started as root (default): adopts PUID/PGID like linuxserver.io images, fixes ownership
# and drops privileges with setpriv. Started with `user:` set: skips all of that.
set -eu

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

if [ "$(id -u)" = "0" ]; then
  if [ "$PUID" = "0" ] || [ "$PGID" = "0" ]; then
    echo "[tubevault] PUID/PGID 0 is not supported - use the id of a normal user." >&2
    exit 1
  fi
  [ "$(id -g tubevault)" = "$PGID" ] || groupmod -o -g "$PGID" tubevault
  [ "$(id -u tubevault)" = "$PUID" ] || usermod -o -u "$PUID" tubevault >/dev/null

  mkdir -p /config /media/.tubevault
  # /config is small: fix everything that is not ours yet.
  find /config \! -user "$PUID" -exec chown "$PUID:$PGID" {} + 2>/dev/null || true
  # /media can be huge (or a share with root squash): only touch our own folders.
  chown "$PUID:$PGID" /media 2>/dev/null || true
  find /media/.tubevault \! -user "$PUID" -exec chown "$PUID:$PGID" {} + 2>/dev/null || true

  # GPU for hardware transcoding: join the groups that own /dev/dri (render, video, …).
  for dev in /dev/dri/renderD* /dev/dri/card*; do
    [ -e "$dev" ] || continue
    gid="$(stat -c %g "$dev")"
    name="$(getent group "$gid" | cut -d: -f1)"
    if [ -z "$name" ]; then
      name="gpu$gid"
      groupadd -o -g "$gid" "$name"
    fi
    id -nG tubevault | tr ' ' '\n' | grep -qx "$name" || usermod -aG "$name" tubevault
  done

  echo "[tubevault] running as uid=$PUID gid=$PGID"
  exec setpriv --reuid="$PUID" --regid="$PGID" --init-groups "$0" "$@"
fi

# --- unprivileged from here on ---------------------------------------------------
if [ ! -w /config ]; then
  echo "[tubevault] /config is not writable for uid $(id -u). Check the volume permissions." >&2
  exit 1
fi

if [ "${1:-}" = "python" ] && [ "${2:-}" = "-m" ] && [ "${3:-}" = "app" ] && [ "$#" -eq 3 ]; then
  # Keep yt-dlp current without rebuilding the image (YTDLP_AUTO_UPDATE=false disables it).
  python -m app update-ytdlp --if-enabled || echo "[tubevault] yt-dlp update skipped"
fi

exec "$@"
