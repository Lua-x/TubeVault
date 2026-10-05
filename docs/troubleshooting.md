# Troubleshooting

| Problem | Solution |
| ------- | -------- |
| `/config is not writable` in the log | `PUID`/`PGID` don't match the folder permissions, or with `user:` the folder doesn't belong to that user |
| Not reachable after updating to 1.0 | Installs from before 1.0 keep port 8096 unless `PORT` is set. If you changed `ports:` to `8823:8823`, also set `PORT=8823` – see [port](installation.md#port) |
| Port 8823 is taken | Set another one: `PORT=9000` and `ports: ["9000:9000"]` |
| Forgotten password | `docker exec -it tubevault python -m app reset-password <user>` |
| Phone with the authenticator app lost | Sign in with a recovery code. Otherwise an admin resets two-factor login under **Einstellungen → Benutzer**, or `docker exec -it tubevault python -m app reset-2fa <user>` |
| Authenticator code refused | The clock of the server or the phone is wrong – TubeVault allows 30 seconds of difference |
| Provider says "invalid redirect_uri" | The redirect address at the provider must match the one under **Verwaltung → Anmeldung über OIDC** exactly; behind a proxy, set `PUBLIC_URL` |
| "Der Anmeldedienst ist nicht erreichbar" (provider unreachable) | TubeVault itself must reach `OIDC_ISSUER` – in the same Docker network, choose an address the container can resolve |
| Forgotten family-device PIN | Set a new one under **Einstellungen → Wer schaut?**, or an admin does it in the user settings |
| Phone remote doesn't connect | Both devices must be signed in; the code is valid for 10 minutes – **Neuer Code** on the TV makes a fresh one. Behind a proxy, WebSockets must be passed through |
| Podcast app doesn't load the feed | The app has to reach the server (see [listening and podcasts](watching.md#listening-and-podcasts)); behind a proxy, set `PUBLIC_URL`. Many apps refuse self-signed certificates |
| Sound stops when the iPhone is locked | iOS sometimes pauses web apps in the background. Started from the home screen it usually works better – or listen to the channel "as a podcast" in a podcast app |
| Comments missing | They are off by default: **Einstellungen → Kommentare**, and "Kommentare laden" for existing videos |
| "Aufs Gerät" (save to device) missing | It needs HTTPS; over `http://` with an IP address the browser grants no storage |
| Saved videos are gone | Site data was cleared, the app removed, or the system cleaned up because space was low (mostly iOS) |
| Downloads fail with "not a bot" / HTTP 429 | YouTube is throttling. TubeVault retries later automatically (backoff up to 6 h) |
| Video doesn't play (MKV) | Safari/iOS can't play MKV directly; TubeVault remuxes it – if that fails too, switch the format to MP4 in the settings |
| "Install app" missing | Android/desktop require HTTPS – put TubeVault behind a reverse proxy with a certificate |
| Hardware test reports an error | Pass `/dev/dri` (Intel/AMD) or the NVIDIA GPU through in the compose file; the test message says why. Without a GPU, TubeVault transcodes in software |
| Transcoded videos stutter | The CPU can't do the quality in real time – switch on hardware acceleration or pick a lower quality in the player |
| Speech recognition set-up fails | It needs PyPI and Hugging Face once; the message says why (no connection, no space). Without internet, place the model by hand, see [speech recognition](watching.md#subtitles-from-speech-recognition) |
| yt-dlp is too old | **Verwaltung → yt-dlp → Jetzt aktualisieren**, then **Neu starten** |
| Downloads stuck at "Keine Internetverbindung" (no internet) | YouTube can't be reached from the server (internet, DNS, firewall). They start by themselves once it works again |
| Notifications don't arrive | **Test senden** shows the reason, e.g. a wrong address or token. If the service runs in the same Docker network, use the container name instead of `localhost` |
| TubeVault doesn't start after going back to an older image | The database was migrated by the newer version. Use the current image, or restore a backup made by the older version |
| Something broke | **Verwaltung → Sicherung**: restore an earlier state |
| Logs | `docker logs tubevault` or `config/logs/tubevault.log` |

Still stuck? Open an [issue](https://github.com/Lua-x/TubeVault/issues) with the TubeVault
version (shown in **Verwaltung**) and the relevant log lines – without passwords or tokens.
