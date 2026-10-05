# Privacy

TubeVault sends no telemetry and loads no external scripts or fonts – a Content Security Policy
enforces that in the browser too. With the YouTube downloader switched off
([media server only](library.md#media-server-only)), no connection leaves the server – unless
you set up speech recognition. Otherwise TubeVault only connects to:

- **YouTube:** downloads, subscription checks including RSS feeds, fetching better quality and
  – only when switched on – comments. After a network error, a small request checks whether
  YouTube is reachable.
- **PyPI:** the yt-dlp update on start and at the push of a button (can be switched off with
  `YTDLP_AUTO_UPDATE=false`), plus once a day if you switch on the "yt-dlp update available"
  notification.
- **SponsorBlock**, only when switched on. Only the first four characters of a SHA-256 hash of
  the video ID leave the server, so SponsorBlock doesn't learn which video you watch.
- **Your notification service**, only if you enter one.
- **Your identity provider** (OIDC), only if you set one up.
- **PyPI and Hugging Face**, once, when an admin **sets up** speech recognition (program and
  model, without a login and with telemetry switched off). Recognition itself runs offline
  afterwards; audio and text never leave the server.

The DLNA server (when switched on) announces itself by multicast in the local network only and
only answers devices from the home network. The phone remote and "watch together" run only
through your server; rooms and codes live in memory and are gone after a restart.

Videos saved with "save to device" live only in the browser of that device; TubeVault learns
nothing about them except the download itself. Podcast feeds are fetched by your app directly
from your server; the key is part of the address and therefore also ends up in the logs of a
reverse proxy.

Passwords are stored as Argon2 hashes; sign-in sessions, API tokens and family-device keys only
as SHA-256 hashes. The podcast key is stored as it is, because the app shows you the feed
address again – renewing it under **Einstellungen → Podcasts** makes old addresses useless. The
OIDC client secret lives in an environment variable, never in the database or in backups.
