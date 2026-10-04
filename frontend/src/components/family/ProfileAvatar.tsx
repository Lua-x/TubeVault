import { cn } from "@/lib/cn";
import { profileColor } from "@/lib/profileColor";

/** The round initial of a profile, in its own color. */
export function ProfileAvatar({
  id,
  name,
  className,
}: {
  id: number;
  name: string;
  className?: string;
}) {
  return (
    <span
      aria-hidden
      className={cn(
        "flex shrink-0 items-center justify-center rounded-full font-semibold text-white uppercase",
        className,
      )}
      style={{ backgroundColor: profileColor(id) }}
    >
      {name.slice(0, 1)}
    </span>
  );
}
