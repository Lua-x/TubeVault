import videojs from "video.js";
import type VjsButton from "video.js/dist/types/button";

/**
 * "Auf Fernseher abspielen" in the control bar – through the Remote Playback API that
 * Chrome (Chromecast) and Safari (AirPlay) have built in, so no script from Google is
 * needed. It only shows up while the browser sees a device it could play on. The TV
 * fetches the same address the browser plays, which is why MP4 videos play from a
 * signed link that works without a login cookie.
 */

type Player = ReturnType<typeof videojs>;

interface WebKitVideo extends HTMLVideoElement {
  webkitShowPlaybackTargetPicker?: () => void;
}

interface AvailabilityEvent extends Event {
  availability?: "available" | "not-available";
}

const CAST_ICON =
  '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 8V6a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-6"/><path d="M2 12a9 9 0 0 1 8 8"/><path d="M2 16a5 5 0 0 1 4 4"/><line x1="2" x2="2.01" y1="20" y2="20"/></svg>';
const AIRPLAY_ICON =
  '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 17H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2h-1"/><path d="m12 15 5 6H7Z"/></svg>';

// getComponent() is typed as the plain Component; this one is a Button.
const Button = videojs.getComponent("Button") as unknown as typeof VjsButton;

class CastButton extends Button {
  private watchId: number | null = null;
  private stopWebkit: (() => void) | null = null;
  private readonly onSource = () => this.watch();

  constructor(player: Player, options?: object) {
    super(player, { ...options, controlText: "Auf Fernseher abspielen" });
    this.hide();
    // A new source decides anew whether it can be sent to a TV.
    player.on("loadedmetadata", this.onSource);
  }

  buildCSSClass(): string {
    return `vjs-tubevault-cast ${super.buildCSSClass()}`;
  }

  private media(): WebKitVideo | null {
    return this.player().el().querySelector("video");
  }

  private watch(): void {
    const media = this.media();
    if (!media) return;
    this.unwatch();
    const icon = this.el().querySelector(".vjs-icon-placeholder");
    const remote = media.remote as RemotePlayback | undefined;
    if (remote && typeof remote.watchAvailability === "function") {
      if (icon) icon.innerHTML = media.webkitShowPlaybackTargetPicker ? AIRPLAY_ICON : CAST_ICON;
      const update = () =>
        this.toggleClass("vjs-tubevault-cast-on", remote.state !== "disconnected");
      remote.onconnecting = update;
      remote.onconnect = update;
      remote.ondisconnect = update;
      remote
        .watchAvailability((available) => (available ? this.show() : this.hide()))
        .then((id) => {
          this.watchId = id;
        })
        // Not for this source (e.g. converted HLS) or not supported: no button.
        .catch(() => this.hide());
    } else if (media.webkitShowPlaybackTargetPicker) {
      if (icon) icon.innerHTML = AIRPLAY_ICON;
      const onChange = (event: Event) => {
        if ((event as AvailabilityEvent).availability === "available") this.show();
        else this.hide();
      };
      media.addEventListener("webkitplaybacktargetavailabilitychanged", onChange);
      this.stopWebkit = () =>
        media.removeEventListener("webkitplaybacktargetavailabilitychanged", onChange);
    }
  }

  private unwatch(): void {
    const remote = this.media()?.remote as RemotePlayback | undefined;
    if (this.watchId !== null && remote) {
      void remote.cancelWatchAvailability(this.watchId).catch(() => undefined);
    }
    this.watchId = null;
    this.stopWebkit?.();
    this.stopWebkit = null;
  }

  handleClick(): void {
    const media = this.media();
    if (!media) return;
    const remote = media.remote as RemotePlayback | undefined;
    if (remote && typeof remote.prompt === "function") {
      void remote.prompt().catch(() => undefined);
    } else {
      media.webkitShowPlaybackTargetPicker?.();
    }
  }

  dispose(): void {
    this.unwatch();
    this.player().off("loadedmetadata", this.onSource);
    super.dispose();
  }
}

videojs.registerComponent("TubeVaultCast", CastButton);

/** Adds the button in front of the fullscreen toggle. */
export function addCastButton(player: Player): void {
  const bar = player.getChild("ControlBar");
  if (!bar) return;
  const fullscreen = bar.getChild("FullscreenToggle");
  const index = fullscreen ? bar.children().indexOf(fullscreen) : bar.children().length;
  bar.addChild("TubeVaultCast", {}, index);
}
