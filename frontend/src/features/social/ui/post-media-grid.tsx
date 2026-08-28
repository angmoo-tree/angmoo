"use client";

import { useRuntimeMediaUrl } from "@/shared/media/public";

import type { PostMediaRead } from "../model/social-feed-contract";

export function PostMediaGrid({ media }: { media?: PostMediaRead[] | null }) {
  const images = (media ?? []).filter((item) => item.media_type === "image");
  if (images.length === 0) return null;
  return (
    <div className="mt-4 overflow-hidden rounded-lg border border-[#eaedf2] bg-[#f8fafc]">
      {images.slice(0, 1).map((item) => (
        <RuntimePostMediaImage key={item.id} media={item} />
      ))}
    </div>
  );
}

function RuntimePostMediaImage({ media }: { media: PostMediaRead }) {
  const source = useRuntimeMediaUrl(media.url);
  if (!source) return null;
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={source}
      alt={media.alt_text || "게시글 이미지"}
      className="aspect-[4/3] w-full object-cover"
      loading="lazy"
    />
  );
}
