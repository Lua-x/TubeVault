<p align="center">
  <img src="frontend/public/favicon.svg" width="88" height="88" alt="" />
</p>

<h1 align="center">TubeVault</h1>

<p align="center">
  A self-hosted media server for YouTube and your own videos – download them, keep them with
  their metadata and watch them in a calm, Apple TV-like library, on the TV too.<br />
  No ads, no tracking, entirely on your own server.
</p>

<p align="center">
  <a href="https://github.com/Lua-x/TubeVault/actions/workflows/ci.yml"><img src="https://github.com/Lua-x/TubeVault/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <a href="https://github.com/Lua-x/TubeVault/actions/workflows/docker.yml"><img src="https://github.com/Lua-x/TubeVault/actions/workflows/docker.yml/badge.svg" alt="Docker" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPL--3.0-blue" alt="License: AGPL-3.0" /></a>
</p>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: light)" srcset="docs/screenshots/home-desktop-light.png" />
    <img src="docs/screenshots/home-desktop-dark.png" width="860" alt="The home page: a sidebar with playlists, a large hero to continue watching, and below it the continue-watching row with progress bars." />
  </picture>
</p>

<p align="center">
  <img src="docs/screenshots/video-desktop-dark.png" width="600" alt="The video page: a 'sponsor skipped' notice with a back button, SponsorBlock and chapter markers on the timeline, and the playlist that is playing next to it." />
  &nbsp;
  <img src="docs/screenshots/home-phone-dark.png" width="200" alt="The home page on a phone, with the tab bar at the bottom." />
</p>

<p align="center">
  <img src="docs/screenshots/channel-desktop-dark.png" width="420" alt="A channel page with banner, avatar, a watched/unwatched filter and all of the channel's videos." />
  &nbsp;
  <img src="docs/screenshots/playlist-desktop-dark.png" width="420" alt="A playlist with a cover made of four thumbnails, a play button and a list sortable by drag and drop." />
</p>

<p align="center">
  <img src="docs/screenshots/subscriptions-desktop-dark.png" width="420" alt="The subscriptions overview with channel banners, avatars and check status." />
  &nbsp;
  <img src="docs/screenshots/admin-desktop-dark.png" width="420" alt="The admin area with key figures, storage per channel, downloads of the last 30 days, yt-dlp update and maintenance." />
</p>

<p align="center">
  <img src="docs/screenshots/tv-dark.png" width="640" alt="The TV view: big tiles for continue watching and watch later, the selected tile outlined in white – usable with the arrow keys of a remote." />
</p>

> The screenshots show demo videos made with `backend/scripts/seed_demo.py`.
> **The interface is in German** for now; this documentation names its menus in German with
> an English translation, e.g. **Einstellungen** (settings) and **Verwaltung** (admin area).

## Features

**Library and downloads**

- Add videos by link, or subscribe to channels and playlists: per-subscription filters
  (Shorts, livestreams, length, date), check interval, quality and clean-up rules
- New uploads usually arrive within minutes (RSS pre-check), and a better quality is fetched
  automatically if YouTube only had a low resolution right after the upload
- Import an existing yt-dlp archive, or your own videos from phone and camera – the folder
  becomes the channel
- **Media server only:** switch the YouTube downloader off, and TubeVault talks to nobody but
  your devices
- Works with Jellyfin, Emby, Kodi and Plex: NFO files and an optional series layout
  (channel = show, year = season)
- Full-text search with filters, watch later, history, similar videos, comments saved for
  offline reading (optional), [SponsorBlock](https://sponsor.ajay.app)

**Watching**

- Plays on every device: the original file, a quick remux, or live transcoding (HLS) – with
  hardware acceleration on Intel/AMD (VAAPI) and NVIDIA (NVENC)
- Resume per user, playlists, chapters, seek previews, even volume across videos and the
  speed remembered per channel
- Subtitles from YouTube – or from speech recognition on your own server, for videos without
  any (optional, downloaded only on request)
- Listen mode with a mini player, lock-screen controls and a sleep timer; channels and
  playlists as podcast feeds
- Save videos to your phone and watch them without the server, in the installable app (PWA)

**Living room**

- Chromecast and AirPlay from the player, a TV view for the remote, and a DLNA server for
  smart TVs, consoles, VLC and Kodi
- **"Wer schaut?"** (who's watching): profiles instead of a login on the TV and the family
  tablet, with PINs where needed
- The phone as a remote for the TV view, and watching together in sync

**Accounts and operation**

- Several users with rights per user (kids profile, watch-only), two-factor login, login via
  your own identity provider (OpenID Connect), API tokens
- Daily backups with restore in the browser, notifications to ntfy, Gotify or a webhook, an
  admin dashboard and yt-dlp updates at the push of a button
- Keeps working without internet, sends no telemetry, one container for amd64 and arm64
  (Raspberry Pi, NAS)

## Quick start

You need Docker with Compose. Create a folder (e.g. `~/tubevault`) with this
`docker-compose.yml`:

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

Then open `http://<server>:8823` and create the admin account.

> **Updating from 0.x?** The default port moved from 8096 (Jellyfin's) to 8823 in 1.0.
> Existing installs keep 8096 as long as `PORT` isn't set, so nothing breaks – see
> [moving to the new port](docs/installation.md#port).

## Documentation

| Guide | What's in it |
| ----- | ------------ |
| [Installation](docs/installation.md) | Image or own build, users and permissions, port, volumes, folder layout, all environment variables, updates |
| [Library](docs/library.md) | Adding videos, subscriptions, import and your own videos, media server only, Jellyfin/Plex, comments, SponsorBlock |
| [Watching](docs/watching.md) | Playback on every device, hardware transcoding, previews and volume, subtitles from speech recognition, save to device, listening and podcasts, offline use |
| [Living room](docs/living-room.md) | Chromecast and AirPlay, TV view, DLNA, "Wer schaut?" profiles, phone as a remote, watch together |
| [Users and login](docs/users-and-login.md) | Rights per user, two-factor login, OpenID Connect (Authelia, Authentik, Keycloak, Pocket ID), API tokens and shortcuts |
| [Administration](docs/administration.md) | Backups, notifications, maintenance, logs |
| [Reverse proxy](docs/reverse-proxy.md) | Nginx, Nginx Proxy Manager, Caddy, Traefik |
| [Troubleshooting](docs/troubleshooting.md) | Common problems and their fixes |
| [Privacy](docs/privacy.md) | Every connection TubeVault makes, and when |

Release notes for every version are on the [releases page](https://github.com/Lua-x/TubeVault/releases)
and in [`docs/releases`](docs/releases).

## Contributing and security

Ideas and bug reports are welcome as [issues](https://github.com/Lua-x/TubeVault/issues). How to
run TubeVault locally and what the checks are: [CONTRIBUTING.md](CONTRIBUTING.md). Please
report security problems privately as described in [SECURITY.md](SECURITY.md).

## License

TubeVault is free software under the [GNU Affero General Public License v3.0](LICENSE) or any
later version. You may use, change and share it. Whoever offers a changed version to others
over a network must give them the source code of that version too.
