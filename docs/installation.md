# Installation

TubeVault is one Docker container for amd64 and arm64 (Raspberry Pi 4/5, most NAS). You need
Docker with Compose.

- [Prebuilt image (recommended)](#prebuilt-image-recommended)
- [Building it yourself](#building-it-yourself)
- [User IDs (PUID/PGID)](#user-ids-puidpgid)
- [Port](#port)
- [Configuration](#configuration)
- [Volumes and folder layout](#volumes-and-folder-layout)
- [Updates](#updates)

## Prebuilt image (recommended)

Create a folder (e.g. `~/tubevault`) with a `docker-compose.yml`:

```yaml
services:
  tubevault:
    image: ghcr.io/lua-x/tubevault:latest
    container_name: tubevault
    ports:
      - "8823:8823"
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=Europe/Berlin
    volumes:
      - ./config:/config
      - /path/to/videos:/media
    restart: unless-stopped
```

```sh
docker compose up -d
```

Open `http://<server>:8823`. On the first visit you create the admin account – or set
`ADMIN_USER` and `ADMIN_PASSWORD` to have it created on start.

## Building it yourself

```sh
git clone https://github.com/Lua-x/TubeVault.git
cd TubeVault
docker compose up -d --build
```

The [`docker-compose.yml`](../docker-compose.yml) in the repository builds the image from the
source and lists every optional setting as a comment (DLNA, OIDC, GPU, import folder).

## User IDs (PUID/PGID)

The container starts as root for a moment, takes over `PUID`/`PGID`, fixes the ownership of
`/config` and then runs as a normal user – like the linuxserver.io images. `id` shows the IDs
of your user. In `/media` only the top folder and `/media/.tubevault` are changed; your
existing files stay untouched.

Instead of `PUID`/`PGID`, `user: "1000:1000"` in the compose file works too. Then nothing runs
as root at all – create the folders for `/config` and `/media` beforehand and give them to that
user.

## Port

TubeVault listens on **8823** ("TUBE" on a phone keypad). Change it with `PORT`, e.g.
`PORT=9000` together with `ports: ["9000:9000"]`.

Before 1.0 the default was 8096 – the same as Jellyfin's, which clashed whenever both ran on
one machine. **Installs from before 1.0 keep 8096** as long as `PORT` isn't set, so an update
never makes your server unreachable. **Verwaltung → System** (admin area → system) shows the
port in use and a hint while an install still runs on the old one. To move over:

```yaml
    ports:
      - "8823:8823"
    environment:
      - PORT=8823
```

Then `docker compose up -d`. To stay on 8096 for good, set `PORT=8096`; the hint disappears.
With `network_mode: host` (for [DLNA](living-room.md#dlna)) the port is the port on the host.

## Configuration

Infrastructure is set with environment variables; everything else (format, quality, subtitle
languages, SponsorBlock, transcoding, folder layout, users …) is set in the app under
**Einstellungen** (settings). A template for an `.env` file is in
[`.env.example`](../.env.example).

| Variable | Default | Meaning |
| -------- | ------- | ------- |
| `PUID` / `PGID` | `1000` | User and group that own the files |
| `TZ` | `Etc/UTC` | Time zone, e.g. `Europe/Berlin` |
| `PORT` | `8823` | Port inside the container (installs from before 1.0: `8096`, see [Port](#port)) |
| `BASE_PATH` | empty | Sub-path behind a reverse proxy, e.g. `/tubevault` |
| `ADMIN_USER` / `ADMIN_PASSWORD` | empty | Creates an admin on first start (password ≥ 8 characters). Empty = set up in the browser |
| `YTDLP_AUTO_UPDATE` | `true` | Update yt-dlp to the newest version on every start |
| `FORWARDED_ALLOW_IPS` | `*` | IPs of reverse proxies whose `X-Forwarded-*` headers are trusted. If TubeVault is reachable without the proxy too, set the proxy's address (e.g. `172.18.0.2`) |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `SESSION_DAYS` | `30` | How long a sign-in stays valid |
| `IMPORT_DIR` | `/import` | Folder that **Verwaltung → Import** takes existing videos from |
| `PUBLIC_URL`, `OIDC_*`, `PASSWORD_LOGIN` | empty | Login via your own identity provider, see [OpenID Connect](users-and-login.md#openid-connect) |

## Volumes and folder layout

| Path | Contents |
| ---- | -------- |
| `/config` | Database (`tubevault.db`), backups (`backups/`), logs (`logs/`), updated yt-dlp and – if set up – speech recognition (`.runtime/`), speech models (`models/`) |
| `/media` | Videos, thumbnails, subtitles, NFOs. The sub-folder `.tubevault/` only holds partial downloads, the transcoding cache and the seek previews |
| `/import` | Optional: existing videos to import (may be read-only, then choose "copy") |

Layout in `/media` (the default, "TubeVault"):

```
/media
└── Channel name/
    ├── folder.jpg        (channel avatar)
    ├── banner.jpg        (channel banner)
    └── 2026/
        ├── Video title [dQw4w9WgXcQ].mp4
        ├── Video title [dQw4w9WgXcQ].nfo
        ├── Video title [dQw4w9WgXcQ]-thumb.jpg
        ├── Video title [dQw4w9WgXcQ].de.vtt
        └── Video title [dQw4w9WgXcQ].en.vtt
```

**Einstellungen → Mediaserver** (settings → media server) switches to the series layout, where
every channel becomes a show in Jellyfin, Emby, Kodi or Plex and every year a season:

```
/media
└── Channel name/
    ├── tvshow.nfo, folder.jpg, banner.jpg, fanart.jpg
    └── Season 2026/
        ├── 2026-08-23 - Video title [dQw4w9WgXcQ].mp4
        ├── 2026-08-23 - Video title [dQw4w9WgXcQ].nfo
        └── …
```

Switching moves all existing files – rescan the library in Jellyfin/Plex afterwards (library
type "Shows" for the series layout, "Movies"/"Home videos" for the TubeVault layout). Title,
chapters and description are also embedded in the video file; NFO files written by other
programs are never overwritten.

## Updates

- **TubeVault:** `docker compose pull && docker compose up -d`. The database is migrated on
  start. Going back to an older version isn't possible afterwards – TubeVault refuses to start
  on a newer database and says why. Back up under **Verwaltung → Sicherung** (admin area →
  backup) before big updates.
- **Image tags:** `latest` is always the newest release; `1`, `1.0` or `1.0.0` keep you on a
  major, minor or exact version.
- **yt-dlp** updates itself on every container start (into `/config/.runtime`), without a new
  image. YouTube changes details often – a restart (`docker compose restart`) brings the newest
  version. **Verwaltung → yt-dlp** updates it at the push of a button.
- **Automatically** with [Watchtower](https://github.com/containrrr/watchtower), which updates
  the container as soon as a new image is published:

  ```yaml
    watchtower:
      image: containrrr/watchtower
      volumes:
        - /var/run/docker.sock:/var/run/docker.sock
      command: --cleanup --interval 86400 tubevault
      restart: unless-stopped
  ```
