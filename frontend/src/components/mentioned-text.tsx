import Link from "next/link";
import type { ReactNode } from "react";

import type { MentionedCharacterRef } from "@/lib/community";

const MENTION_RE =
  /(?<![A-Za-z0-9_.])@([a-z0-9_]{2,40})(?=$|[^A-Za-z0-9_.]|\.(?=$|[^A-Za-z0-9_]))/g;

export function MentionedText({
  text,
  mentionedCharacters,
}: {
  text: string;
  mentionedCharacters?: MentionedCharacterRef[];
}) {
  const mentions = new Map(
    (mentionedCharacters ?? []).map((character) => [
      character.handle,
      character,
    ]),
  );
  if (!text || mentions.size === 0) return <>{text}</>;

  const parts: ReactNode[] = [];
  let cursor = 0;
  for (const match of text.matchAll(MENTION_RE)) {
    const index = match.index ?? 0;
    const handle = match[1];
    const character = mentions.get(handle);
    if (!character) continue;
    if (index > cursor) {
      parts.push(text.slice(cursor, index));
    }
    const label = match[0];
    parts.push(
      <Link
        key={`${character.character_id}:${index}`}
        href={`/profiles/characters/${character.character_id}`}
        className="font-extrabold text-[#ff6b6b] underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#ff6b6b]/30"
      >
        {label}
      </Link>,
    );
    cursor = index + label.length;
  }
  if (cursor < text.length) {
    parts.push(text.slice(cursor));
  }
  return <>{parts}</>;
}
