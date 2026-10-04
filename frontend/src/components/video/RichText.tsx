import { Fragment, useMemo } from "react";

import { tokenize } from "@/lib/richText";

interface RichTextProps {
  text: string;
  /** Timestamps longer than the video stay plain text. */
  duration?: number | null;
  onSeek?: (seconds: number) => void;
}

/** Text with clickable links and – when a player is around – timestamps. */
export function RichText({ text, duration = null, onSeek }: RichTextProps) {
  const tokens = useMemo(() => tokenize(text, duration), [text, duration]);
  return tokens.map((token, index) => {
    if (token.kind === "link") {
      return (
        <a
          key={index}
          href={token.text}
          target="_blank"
          rel="noreferrer noopener"
          // Underlined: in running text, color alone doesn't set a link apart.
          className="break-words text-accent underline decoration-accent/40 underline-offset-2 hover:decoration-accent"
        >
          {token.text}
        </a>
      );
    }
    if (token.kind === "time" && onSeek) {
      return (
        <button
          key={index}
          type="button"
          onClick={() => onSeek(token.seconds)}
          className="font-medium text-accent tabular-nums hover:underline"
        >
          {token.text}
        </button>
      );
    }
    return <Fragment key={index}>{token.text}</Fragment>;
  });
}
