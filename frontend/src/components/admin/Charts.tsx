import { useRef, useState, type FocusEvent, type PointerEvent, type ReactNode } from "react";

import { cn } from "@/lib/cn";
import { formatBytes } from "@/lib/format";
import type { ChannelStorage, DayCount } from "@/lib/types";

interface TipState {
  x: number;
  y: number;
  content: ReactNode;
}

/** One floating tooltip per chart; values lead, labels follow. */
function useTooltip() {
  const frame = useRef<HTMLDivElement>(null);
  const [tip, setTip] = useState<TipState | null>(null);

  const place = (target: Element, clientX: number | null, content: ReactNode) => {
    const box = frame.current?.getBoundingClientRect();
    const rect = target.getBoundingClientRect();
    if (!box) return;
    const x = (clientX ?? rect.left + rect.width / 2) - box.left;
    setTip({ x: Math.min(Math.max(x, 70), box.width - 70), y: rect.top - box.top, content });
  };

  const handlers = (content: ReactNode) => ({
    onPointerMove: (event: PointerEvent<HTMLElement>) =>
      place(event.currentTarget, event.clientX, content),
    onPointerLeave: () => setTip(null),
    onFocus: (event: FocusEvent<HTMLElement>) => place(event.currentTarget, null, content),
    onBlur: () => setTip(null),
  });

  const layer = tip ? (
    <div
      role="tooltip"
      className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded-xl bg-[rgb(28_28_30/0.92)] px-3 py-2 text-[12px] whitespace-nowrap text-white shadow-[0_8px_24px_rgb(0_0_0/0.3)] backdrop-blur-xl"
      style={{ left: tip.x, top: tip.y - 8 }}
    >
      {tip.content}
    </div>
  ) : null;

  return { frame, handlers, layer };
}

function TipValue({ value, label }: { value: string; label: string }) {
  return (
    <>
      <span className="block text-[13px] font-semibold">{value}</span>
      <span className="block text-white/65">{label}</span>
    </>
  );
}

/** Storage per channel: horizontal bars, value at each tip (so every value is visible). */
export function StorageBars({ data }: { data: ChannelStorage[] }) {
  const { frame, handlers, layer } = useTooltip();
  const max = Math.max(1, ...data.map((d) => d.size));
  if (data.length === 0) {
    return <p className="text-[14px] text-secondary">Noch keine Videos.</p>;
  }
  return (
    <div ref={frame} className="relative">
      <ul className="flex flex-col gap-2.5">
        {data.map((channel) => (
          <li
            key={channel.channel_id ?? channel.name}
            tabIndex={0}
            className="grid grid-cols-[minmax(0,9rem)_1fr] items-center gap-3 rounded-md outline-offset-4 sm:grid-cols-[minmax(0,12rem)_1fr]"
            {...handlers(
              <TipValue
                value={formatBytes(channel.size)}
                label={`${channel.name} · ${channel.videos} ${channel.videos === 1 ? "Video" : "Videos"}`}
              />,
            )}
          >
            <span className="truncate text-[13px] text-primary">{channel.name}</span>
            <span className="flex min-w-0 items-center gap-2">
              <span
                className="h-3 shrink-0 rounded-r-[4px] bg-accent transition-opacity duration-150 hover:opacity-80"
                style={{ width: `max(3px, ${(channel.size / max) * 68}%)` }}
              />
              <span className="shrink-0 text-[12px] text-secondary tabular-nums">
                {formatBytes(channel.size)}
              </span>
            </span>
          </li>
        ))}
      </ul>
      {layer}
    </div>
  );
}

const dayFormat = new Intl.DateTimeFormat("de-DE", { day: "numeric", month: "short" });
const dayLabel = (iso: string) => dayFormat.format(new Date(`${iso}T12:00:00`));

/** Finished downloads per day: columns from one baseline, details on hover/focus. */
export function DownloadColumns({ data }: { data: DayCount[] }) {
  const { frame, handlers, layer } = useTooltip();
  const [table, setTable] = useState(false);
  const max = Math.max(1, ...data.map((d) => d.completed));
  const total = data.reduce((sum, d) => sum + d.completed, 0);
  const peak = data.reduce<DayCount | undefined>(
    (best, d) => (!best || d.completed > best.completed ? d : best),
    undefined,
  );

  if (total === 0) {
    return <p className="text-[14px] text-secondary">In den letzten 30 Tagen keine Downloads.</p>;
  }
  return (
    <div>
      <div ref={frame} className="relative">
        <div className="flex items-end justify-between text-[11px] text-tertiary tabular-nums">
          <span>{max}</span>
        </div>
        <div className="relative mt-1 flex h-32 items-end gap-[2px] border-b border-separator">
          {data.map((day) => (
            <button
              key={day.date}
              type="button"
              aria-label={`${dayLabel(day.date)}: ${day.completed} geladen, ${day.failed} fehlgeschlagen`}
              className="group flex h-full min-w-0 flex-1 cursor-default items-end justify-center outline-offset-2"
              {...handlers(
                <TipValue
                  value={`${day.completed} geladen`}
                  label={`${dayLabel(day.date)}${day.failed ? ` · ${day.failed} fehlgeschlagen` : ""}`}
                />,
              )}
            >
              <span
                className={cn(
                  "w-full max-w-6 rounded-t-[4px] bg-accent transition-opacity duration-150 group-hover:opacity-80",
                  day.completed === 0 && "bg-transparent",
                )}
                style={{
                  height: day.completed ? `${Math.max(4, (day.completed / max) * 100)}%` : 0,
                }}
              />
            </button>
          ))}
        </div>
        <div className="mt-1.5 flex justify-between text-[11px] text-tertiary">
          <span>{data[0] ? dayLabel(data[0].date) : ""}</span>
          <span>Heute</span>
        </div>
        {layer}
      </div>
      <div className="mt-3 flex items-center justify-between gap-4 text-[13px] text-secondary">
        <span>
          {total} in 30 Tagen
          {peak && peak.completed > 0
            ? ` · meiste am ${dayLabel(peak.date)} (${peak.completed})`
            : ""}
        </span>
        <button
          type="button"
          onClick={() => setTable((v) => !v)}
          className="font-medium text-accent hover:underline"
        >
          {table ? "Diagramm" : "Als Tabelle"}
        </button>
      </div>
      {table && (
        <table className="mt-3 w-full text-[13px]">
          <thead className="text-left text-secondary">
            <tr>
              <th className="py-1 font-medium">Tag</th>
              <th className="py-1 text-right font-medium">Geladen</th>
              <th className="py-1 text-right font-medium">Fehlgeschlagen</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-separator tabular-nums">
            {data
              .filter((d) => d.completed || d.failed)
              .reverse()
              .map((d) => (
                <tr key={d.date}>
                  <td className="py-1.5">{dayLabel(d.date)}</td>
                  <td className="py-1.5 text-right">{d.completed}</td>
                  <td className="py-1.5 text-right">{d.failed}</td>
                </tr>
              ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
