# Living room

- [Chromecast and AirPlay](#chromecast-and-airplay)
- [TV view](#tv-view)
- [DLNA](#dlna)
- ["Wer schaut?" – family devices](#wer-schaut--family-devices)
- [Phone as a remote](#phone-as-a-remote)
- [Watch together](#watch-together)

## Chromecast and AirPlay

A TV button appears in the player as soon as Chrome (Chromecast) or Safari (AirPlay) sees a
device in the network. TubeVault uses what the browser has built in – no script from Google.
The TV fetches the video through a signed link that is valid for 12 hours and opens only this
one video; TubeVault checks the account's rights again on every request. MKV files are remuxed
to MP4 for it once.

Important: the TV has to reach the address you open TubeVault under in the browser (so not
`localhost`), and Chromecast refuses self-signed certificates.

## TV view

In the TV's browser (Fire TV, Android TV, Tizen, webOS …) a view with big tiles opens by
itself, fully usable with the arrow keys of the remote: OK plays and pauses, left/right seeks,
back goes back and lands on the tile you chose last. On other devices it is under
**Einstellungen → Darstellung → TV-Ansicht** (settings → appearance → TV view) or at `/tv`.

## DLNA

Switched on under **Einstellungen → Fernseher im Heimnetz** (settings → TVs in the home
network), TubeVault shows up as a media source on smart TVs, consoles, in VLC and in Kodi –
with the folders "channels", "recently added" and "playlists", seeking included. TVs find
servers by multicast, which only reaches a container in the host network:

```yaml
services:
  tubevault:
    network_mode: host   # instead of ports: – TubeVault then listens directly on port 8823
```

DLNA has no login. That's why it is off by default, only answers addresses from the home
network (private, loopback and link-local addresses), refuses everything that comes through a
reverse proxy (`X-Forwarded-For`) and only shows what the account chosen in the settings may
see – a kids profile stays a kids profile on the TV too. The original file is played; MP4 with
H.264 is understood by practically every TV, MKV and WebM not by all.

## "Wer schaut?" – family devices

Nobody wants to type a password on the TV or the family tablet. That's what **family devices**
are for:

1. Sign in on the device as an admin and choose **Dieses Gerät als Familiengerät einrichten**
   (set up this device as a family device) under **Einstellungen → Familiengeräte** (settings →
   family devices). The device gets its own cookie, valid for 400 days.
2. Every account decides for itself under **Einstellungen → Wer schaut?** whether it appears
   there – for kids profiles an admin does it in the user settings. Admins and accounts with
   two-factor login only appear with a PIN (4–8 digits); everyone else may set one.
3. Instead of the login, the device now shows the profiles. You switch with **Profil wechseln**
   (switch profile) in the sidebar or at the top of the TV view – the previous profile is signed
   out.

After five wrong PINs a profile waits 15 minutes. A family device can be removed in the settings
at any time; it then shows the normal login again right away. Nothing changes on any other
device.

## Phone as a remote

In the TV view choose **Fernbedienung** (remote) at the top right: the TV shows a QR code and a
six-digit code (valid for 10 minutes). On the phone, scan the QR code or open **Fernbedienung**
in TubeVault and type the code. From then on the phone controls pause, seeking and back, shows
what's playing, and on every video page **Auf Fernseher** (to TV) sends the video straight
there. The phone stays connected after a reload; the TV can end the connection at any time. Both
devices have to be signed in to TubeVault – the phone with its own account. Wrong codes slow
guessing down.

## Watch together

On the video page, **Gemeinsam schauen** (watch together) opens a room with a link to share.
Whoever opens it sees the same video at the same point; play, pause and seeking apply to
everyone, and whoever falls a few seconds behind is gently pulled back. Any account that may see
this video can join – a kids profile doesn't get into a room with a video outside its channels.
The room closes ten minutes after everyone has left.

Good for long-distance relationships and family on several sofas; over the internet this needs
a [reverse proxy](reverse-proxy.md) with WebSockets.
