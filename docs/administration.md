# Administration

**Verwaltung** (the admin area, for admins) shows key figures, storage per channel, the
downloads of the last 30 days and system information (versions, transcoding, cache, port), and
has the tools below.

- [Backups](#backups)
- [Notifications](#notifications)
- [Maintenance](#maintenance)
- [yt-dlp and restart](#yt-dlp-and-restart)
- [YouTube sign-in (cookies)](#youtube-sign-in-cookies)
- [Logs](#logs)
- [Command line](#command-line)

## Backups

Everything except the videos themselves is in the database under `/config`: settings, users,
subscriptions, playlists and watch progress. **Verwaltung → Sicherung** (backup)

- creates a backup under `/config/backups` automatically every day (the last 7 are kept,
  adjustable or switchable off), plus **Jetzt sichern** (back up now) by hand,
- offers every backup as a ZIP to download – keep a copy somewhere else now and then; it
  contains the user accounts too,
- restores a backup from the list or from a file. TubeVault checks it, backs up the current
  state first and restarts; afterwards "verify files" runs in case the backup knows videos that
  no longer exist.

Backups are made with SQLite's backup function, so they are consistent even while downloads
run. A backup from an older TubeVault version can be restored – it is migrated on the restart;
one from a newer version is refused. Videos, thumbnails and subtitles live in `/media` – back
those up like other large files (e.g. with a snapshot of your NAS).

## Notifications

Under **Verwaltung → Benachrichtigungen** (notifications) TubeVault sends messages to a service
you run – off by default:

- **ntfy:** the address including the topic, e.g. `https://ntfy.example.org/tubevault`,
  optionally with an access token
- **Gotify:** the server's address and an application token
- **Webhook:** any address, e.g. a Home Assistant automation. TubeVault sends a POST with
  `{"event": "video_downloaded", "title": "…", "message": "…", "data": {…}}`

You can choose: new videos, failed downloads, failed subscription checks (once per problem),
low disk space (below 5 % or 5 GB free), expired [YouTube cookies](#youtube-sign-in-cookies)
and yt-dlp updates (asks PyPI once a day for this, off by default). Whatever happens within 30 seconds arrives as one message – a new subscription with
50 videos reports "50 new videos". The token is only stored, never shown again; **Test senden**
(send test) checks the settings right away.

## Maintenance

**Verwaltung → Wartung** (maintenance):

- **Dateien prüfen** (verify files): marks videos whose file is gone as missing – and found
  ones as available again
- **Suchindex neu aufbauen** (rebuild search index)
- **Kanalbilder neu laden** (reload channel art)
- **Bessere Qualität suchen** (look for better quality): asks YouTube about every video below
  its target quality (the subscription's limit, else 4K) and downloads again where a better
  version exists – in place, with watch progress and playlists kept. One request per video; if
  YouTube starts to throttle, it stops and can simply be started again later
- **NFO-Dateien neu schreiben** (rewrite NFO files)
- **Umwandlungs-Cache leeren** (empty the transcoding cache)

**Verwaltung → Import** takes existing videos, see [import](library.md#import-and-your-own-videos).

## yt-dlp and restart

**Verwaltung → yt-dlp** shows the active and the newest version and updates yt-dlp at the push
of a button; **Neu starten** (restart) then loads it. The update lands in `/config/.runtime`,
so it survives container restarts; when a newer image brings a newer yt-dlp, the copy in
`/config` is dropped by itself.

## YouTube sign-in (cookies)

Some videos YouTube only shows to a signed-in account: age-restricted ones, members-only
videos and private videos (or private playlists) shared with you. For those, upload the cookies
of a YouTube account under **Verwaltung → YouTube-Anmeldung** (YouTube sign-in).

1. Install a browser add-on that exports cookies as a `cookies.txt` (Netscape format).
2. Open a private window, sign in on youtube.com, export the cookies – and close the private
   window right away. Otherwise the browser keeps renewing them, and YouTube ends the session
   TubeVault has after a few days.
3. Upload the file with **cookies.txt hochladen** (upload cookies.txt).

A second account is safer than your main one: YouTube may block accounts that download a lot.

TubeVault always asks YouTube without the cookies first and only tries again with them when
YouTube answers that a sign-in is needed ("Sign in to confirm your age", "members-only",
"private"). Everything else – and YouTube's "not a bot" check – runs without an account. The
admin area shows until when the cookies are valid and when they were last needed.

Only the cookies of youtube.com and google.com are kept; everything else in the file is
dropped. They are stored in `/config/cookies`, readable only by TubeVault – not in the
database, so not in backups, never in the logs and never sent back to the browser. What
YouTube renews on the way is saved, so the cookies stay valid longer.

When they run out – by their date, or because YouTube ended the session – the admin area says
so and TubeVault sends the "YouTube-Cookies abgelaufen" notification once. Upload new ones; videos
that failed in the meantime can be retried under **Downloads**.

## Logs

The log viewer at the bottom of the admin area shows the latest entries, filterable by level.
The same lines are in `docker logs tubevault` and in `config/logs/tubevault.log`.

## Command line

```sh
docker exec -it tubevault python -m app reset-password <user>   # forgotten password
docker exec -it tubevault python -m app reset-2fa <user>        # lost authenticator phone
docker exec -it tubevault python -m app update-ytdlp            # update yt-dlp now
docker exec -it tubevault python -m app healthcheck             # exit code 0 = healthy
```
