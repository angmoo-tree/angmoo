"use client";

import { useRuntimeMediaUrl } from "@/hooks/use-runtime-media-url";

type PostMediaRead = { id: number; media_type: string; url: string; alt_text: string };
import styles from "./post-media-grid.module.css";

export function PostMediaGrid({ media }: { media?: PostMediaRead[] | null }) {
  const images = (media ?? []).filter((item) => item.media_type === "image");
  if (images.length === 0) return null;
  const visibleImages = images.slice(0, 4);
  const layoutClassName =
    images.length === 1
      ? styles.mediaGridOne
      : images.length === 2
        ? `${styles.mediaGridMultiple} ${styles.mediaGridTwo}`
        : images.length === 3
          ? `${styles.mediaGridMultiple} ${styles.mediaGridThree}`
          : styles.mediaGridMultiple;
  return (
    <div className={`${styles.mediaGrid} ${layoutClassName}`}>
      {visibleImages.map((item, index) => (
        <RuntimePostMediaImage
          extraCount={index === 3 ? images.length - visibleImages.length : 0}
          fallbackAlt={`게시글 첨부 이미지 ${index + 1}`}
          key={item.id}
          media={item}
        />
      ))}
    </div>
  );
}

function RuntimePostMediaImage({
  extraCount,
  fallbackAlt,
  media,
}: {
  extraCount: number;
  fallbackAlt: string;
  media: PostMediaRead;
}) {
  const source = useRuntimeMediaUrl(media.url);
  if (!source) return null;
  return (
    <div className={styles.mediaFrame}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={source}
        alt={media.alt_text.trim() || fallbackAlt}
        className={styles.mediaImage}
        loading="lazy"
      />
      {extraCount > 0 ? (
        <span className={styles.mediaMore} aria-label={`추가 이미지 ${extraCount}개`}>
          +{extraCount}
        </span>
      ) : null}
    </div>
  );
}
