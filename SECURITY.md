# Security

## Supported versions

Security fixes go into the newest release. Please update to the latest image
(`ghcr.io/lua-x/tubevault:latest` or the newest `1.x` tag) before reporting.

| Version | Supported |
| ------- | --------- |
| 1.x     | ✅ |
| 0.x     | ❌ – please update; the update keeps your data and your port |

## Reporting a vulnerability

Please **don't open a public issue** for security problems. Report them privately through
GitHub: on the repository's **Security** tab choose **Report a vulnerability**. Include:

- the TubeVault version (shown in **Verwaltung**, the admin area) and how you run it
  (reverse proxy, `BASE_PATH`, OIDC, DLNA …),
- what an attacker can do, and what they need for it (an account? which rights? network
  access?),
- steps to reproduce, ideally with a minimal request or script.

TubeVault is maintained in spare time. You'll get an answer within a week; a fix for a
confirmed problem is released as soon as it is ready, and you are credited in the release
notes unless you'd rather not be.

## Security model

What TubeVault protects, and what it relies on:

- **Accounts:** every page and API endpoint requires a sign-in, except the login itself, the
  health check, the [DLNA server](docs/living-room.md#dlna) (off by default, home network only)
  and podcast feeds (a secret key in the address). Passwords are Argon2 hashes; sessions, API
  tokens and family-device keys are stored as SHA-256 hashes only.
- **Rights:** admins can do everything. Other users only see the channels they are allowed to
  see – in lists, search, direct links, streams, subtitles, casting links, DLNA, podcast feeds
  and watch-together rooms alike – and only add videos if allowed.
- **Browser:** cookies are `HttpOnly` and `SameSite=Lax`, state-changing requests need a custom
  header (CSRF), WebSockets check the origin, and a Content Security Policy blocks external
  scripts.
- **Brute force:** wrong passwords (per address and per account), two-factor codes,
  family-device PINs and remote pairing codes are rate-limited.
- **Files:** every path from the database is checked to stay inside `/media`; ffmpeg and yt-dlp
  only get paths and arguments TubeVault built itself. Backups are checked before they are
  restored (format, integrity, size, schema version).
- **Child processes:** speech recognition only sees a short list of environment variables –
  no passwords or client secrets.
- **Not in scope:** TubeVault trusts its admins and the host it runs on. It should be reachable
  from the internet only through a reverse proxy with HTTPS – then set `FORWARDED_ALLOW_IPS` to
  the proxy's address, so client addresses can't be faked with `X-Forwarded-For`. Content
  downloaded from YouTube is played as media, never executed.

Every change runs through tests that check each API route needs a sign-in (except the ones
listed above), CodeQL code scanning, and Dependabot for dependency updates.
