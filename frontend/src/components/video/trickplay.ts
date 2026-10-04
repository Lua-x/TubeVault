import type videojs from "video.js";

import { apiUrl } from "@/lib/base";
import type { Trickplay } from "@/lib/types";

/**
 * A small picture above the progress line while hovering or dragging it – cut out of the
 * preview sheets the server made (app/services/analysis.py), so no video is decoded here.
 */

type Player = ReturnType<typeof videojs>;

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

export function addTrickplay(player: Player, videoId: number, info: Trickplay): () => void {
  const root = player.el() as HTMLElement;
  const control = root.querySelector<HTMLElement>(".vjs-progress-control");
  const holder = root.querySelector<HTMLElement>(".vjs-progress-holder");
  if (!control || !holder || info.count < 1) return () => undefined;

  const preview = document.createElement("div");
  preview.className = "vjs-tubevault-trickplay";
  preview.setAttribute("aria-hidden", "true");
  preview.style.width = `${info.width}px`;
  preview.style.height = `${info.height}px`;
  control.appendChild(preview);
  const perSheet = info.columns * info.rows;
  let dragging = false;

  const show = (clientX: number) => {
    const bar = holder.getBoundingClientRect();
    const duration = player.duration() || 0;
    if (!bar.width || !duration) return;
    const time = clamp((clientX - bar.left) / bar.width, 0, 1) * duration;
    const index = clamp(Math.floor(time / info.interval), 0, info.count - 1);
    const sheet = Math.floor(index / perSheet) + 1;
    const cell = index % perSheet;
    const url = apiUrl(`videos/${videoId}/trickplay/${sheet}.jpg?v=${info.version}`);
    preview.style.backgroundImage = `url("${url}")`;
    preview.style.backgroundPosition = `-${(cell % info.columns) * info.width}px -${
      Math.floor(cell / info.columns) * info.height
    }px`;
    const area = control.getBoundingClientRect();
    const x = clamp(clientX - area.left - info.width / 2, 0, Math.max(0, area.width - info.width));
    preview.style.transform = `translateX(${x}px)`;
    preview.classList.add("is-visible");
  };
  const hide = () => {
    if (!dragging) preview.classList.remove("is-visible");
  };

  const onMove = (event: MouseEvent) => show(event.clientX);
  const onDown = () => {
    dragging = true;
  };
  const onUp = () => {
    dragging = false;
    preview.classList.remove("is-visible");
  };
  // While dragging, the pointer may leave the bar – keep following it.
  const onDocumentMove = (event: MouseEvent) => {
    if (dragging) show(event.clientX);
  };
  const onTouch = (event: TouchEvent) => {
    const touch = event.touches[0];
    if (touch) show(touch.clientX);
  };

  control.addEventListener("mousemove", onMove);
  control.addEventListener("mouseleave", hide);
  control.addEventListener("mousedown", onDown);
  document.addEventListener("mousemove", onDocumentMove);
  document.addEventListener("mouseup", onUp);
  control.addEventListener("touchmove", onTouch, { passive: true });
  control.addEventListener("touchend", onUp);
  control.addEventListener("touchcancel", onUp);

  return () => {
    control.removeEventListener("mousemove", onMove);
    control.removeEventListener("mouseleave", hide);
    control.removeEventListener("mousedown", onDown);
    document.removeEventListener("mousemove", onDocumentMove);
    document.removeEventListener("mouseup", onUp);
    control.removeEventListener("touchmove", onTouch);
    control.removeEventListener("touchend", onUp);
    control.removeEventListener("touchcancel", onUp);
    preview.remove();
  };
}
