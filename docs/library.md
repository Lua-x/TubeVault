# Library

- [Adding videos](#adding-videos)
- [Subscriptions](#subscriptions)
- [Import and your own videos](#import-and-your-own-videos)
- [Media server only](#media-server-only)
- [MP4 or MKV?](#mp4-or-mkv)
- [Quality](#quality)
- [Comments](#comments)
- [Watch later and history](#watch-later-and-history)
- [SponsorBlock](#sponsorblock)

## Adding videos

**Video hinzufügen** (add video, the plus button) takes a YouTube link and downloads the video
with [yt-dlp](https://github.com/yt-dlp/yt-dlp) and ffmpeg – with title, description, channel,
upload date, thumbnail, chapters and subtitles (manual ones and the automatic ones in the
original language). Format and quality can be chosen per video; the defaults live under
**Einstellungen → Downloads** (settings → downloads).

The download queue shows live progress, can pause and resume single downloads (partial files
are kept) or the whole queue, and retries automatically with a backoff after network errors
and rate limits. Shared links also work from phones: see
[API tokens and shortcuts](users-and-login.md#api-tokens-and-shortcuts).

## Subscriptions

Under **Abos → Abonnieren** (subscriptions → subscribe) you add a channel
(`https://www.youtube.com/@name`, `/channel/…`, `/c/…`) or a playlist (`…/playlist?list=…`).

- **Existing videos:** on the first check TubeVault downloads only the newest 5 videos by
  default (5, 25, 100 or all can be chosen). Older ones are remembered as "skipped" and not
  fetched later.
- **Check interval** per subscription, from 15 minutes to weekly, plus **Jetzt prüfen** (check
  now) at any time.
- **Filters** – Shorts, livestreams, minimum/maximum length, only videos after a date – are
  applied twice: roughly on the channel listing (saves downloads) and exactly once a video's
  metadata is loaded. Filtered videos show up in the subscription's history with the reason.
  After changing filters, **Neu bewerten** (re-evaluate) applies them again.
- **Quality and format** per subscription (maximum resolution, prefer H.264, MP4/MKV).
- **Clean-up** ("older than X days" by upload date, "only the newest N") runs hourly and after
  every download. A video is only deleted when no other subscription wants to keep it and it
  wasn't added by hand. Deleted videos aren't downloaded again by the subscription. Only
  admins can change clean-up rules.
- **Channels:** for Shorts and livestreams the channel's tabs are read too. Running or
  announced livestreams are downloaded after they end.
- **Finding new uploads sooner:** every 15 minutes TubeVault reads each subscription's small
  RSS feed (the last 15 uploads). If an unknown video shows up, the thorough check runs early
  – new videos usually arrive within minutes without listing the whole channel all the time.
  Can be turned off under **Einstellungen → Automatik** (settings → automation).
- **Better quality later:** right after an upload YouTube often only offers low resolutions.
  If a video is below the target quality (the limit you set; with "Beste verfügbare" up to 4K),
  TubeVault asks again up to twice a day during the first 7 days and replaces the file as soon
  as a better one exists. Watch progress and playlists stay, and the old version plays until
  the swap. Admins can fetch any video again with **Neu laden** (reload) on its page, e.g.
  after switching to 4K.

## Import and your own videos

**Verwaltung → Import** (admin area → import) takes videos that are already on disk – from the
optional `/import` volume or unknown files under `/media` – and moves, copies or leaves them in
place.

**From YouTube:** the YouTube ID comes from a yt-dlp `.info.json` (then title, channel and date
too) or from the file name (`Title [ID].mp4`, `Title (ID).mp4`, `Title-ID.mp4`). Missing details
are fetched from YouTube; if a video no longer exists there, the file name is used. Thumbnails
and subtitles (`.vtt`, `.srt`) next to the file come along, and missing thumbnails are made by
ffmpeg.

**Your own videos:** files without a YouTube ID – from your phone, your camera, the last party –
are imported as your own videos. The folder becomes the channel
(`/import/Holiday 2024/IMG_1234.mp4` ends up in "Holiday 2024", files directly in the folder in
"Eigene Videos"), and title, description and recording date are read from the file, otherwise
the file name and modification date are used. A copy of the same file is recognised. Your own
videos work everywhere – player, TV view, DLNA, playlists, podcasts, kids profiles (the folder
can be shared like a channel); comments, SponsorBlock and "reload" don't exist for them. So
that an old archive doesn't land there by accident, they are only preselected in the import
when the YouTube downloader is off.

Videos without subtitles can get some from [speech recognition](watching.md#subtitles-from-speech-recognition),
also automatically after each import.

## Media server only

Under **Einstellungen → Betrieb** (settings → operation) the **YouTube downloader** can be
switched off. TubeVault is then a pure media server for your existing and your own videos:

- no connection to YouTube or SponsorBlock any more – not even the yt-dlp update on start
- no subscription checks, downloads, comments, channel art or quality upgrades; "add video",
  subscriptions and downloads disappear from the app, and the API refuses them
- the subscriptions' clean-up rules pause, so the library doesn't shrink bit by bit
- new videos come in through **Verwaltung → Import**

The only exception, and only on your click: setting up
[speech recognition](watching.md#subtitles-from-speech-recognition) downloads its program and
model once.

Subscriptions, queue and settings stay saved; switching the downloader back on continues
exactly where it stopped.

## MP4 or MKV?

Both work – globally in the settings or per video in the "add video" dialog.

- **MP4 (default):** plays directly in every browser, Safari and iPhone/iPad included. With
  "prefer H.264" compatibility is at its best.
- **MKV:** a flexible container that plays directly in Chrome, Edge and Firefox. Safari and iOS
  get a remuxed copy automatically (see [playback on every device](watching.md#playback-on-every-device)).

## Quality

Quality works like in Pinchflat: TubeVault takes the best resolution up to the limit you set
(**Maximale Qualität**, measured on the shorter side, so Shorts in portrait come in full
1080×1920) and only then prefers H.264 between formats of that resolution. YouTube offers H.264
up to 1080p; for 1440p and 4K it has only VP9 or AV1, and those are taken then. Nothing is
re-encoded – the file holds YouTube's original streams. Devices that can't play VP9/AV1 directly
(older iPhones, some TVs) get a converted stream while watching.

## Comments

Under **Einstellungen → Kommentare** (settings → comments) TubeVault saves the top comments of
every new video with their replies (100 to 5000) – off by default. It can also be turned on or
off per subscription and in the "add video" dialog; for an existing video, **Kommentare laden**
(load comments) fetches them (needs internet). The video page shows them sorted by top or new,
with pinned comments, replies from the channel and hearts. Instead of profile pictures from
YouTube there are coloured initials, so the page loads nothing from outside, offline too.
Admins can delete a video's saved comments.

## Watch later and history

- **Später ansehen** (watch later) remembers videos with one tap on the video page. The list is
  a playlist like any other – sortable, playable in one go, can be saved to a device and
  listened to as a podcast. Watched videos disappear by themselves (can be turned off under
  **Einstellungen → Wiedergabe**, settings → playback).
- **Verlauf** (history) shows everything you started or watched, by day. Removing entries
  forgets the position too.

Search (**Suche**) covers title, description and channel, finds word beginnings, ignores
accents ("brucke" finds "Brücke") and filters by length, upload date and channel – also without
a search term. Timestamps in descriptions and comments jump to that point in the player.

## SponsorBlock

[SponsorBlock](https://sponsor.ajay.app) is a community database of marked segments in YouTube
videos. Under **Einstellungen → SponsorBlock** (and per subscription) you choose:

- **Aus** (off, the default): no connection to SponsorBlock.
- **Überspringen** (skip): the segments appear as markers on the timeline and are skipped while
  watching; a notice with "back" undoes it. The file stays unchanged, and new markers are
  fetched for fresh videos regularly. Whether to skip automatically or with a button is a
  per-user setting.
- **Herausschneiden** (cut): the segments are removed from the file for good while
  downloading – ideal if you also watch in Jellyfin/Plex. Applies to new downloads only.

Which categories count (sponsor, self-promotion, subscribe reminder, intro, outro, …) is set
there as well. Only the first four characters of a SHA-256 hash of the video ID leave the
server, so SponsorBlock doesn't learn which video you watch.
