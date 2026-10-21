"use client";
import { useUiText } from "@/hooks/use-ui-text";


import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useElementVisibility } from "@/hooks/use-element-visibility";
import { useRuntimeMediaResource } from "@/hooks/use-runtime-media-url";

type PostMediaRead = { id: number; media_type: string; url: string; alt_text: string; width?: number | null; height?: number | null };
import styles from "./post-media-grid.module.css";

export function PostMediaGrid({ media, deferred = false }: { media?: PostMediaRead[] | null; deferred?: boolean }) {
  const uiText = useUiText("shell");
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
          fallbackAlt={uiText("게시글 첨부 이미지 {{value0}}", {value0: index + 1})}
          key={item.id}
          media={item}
          deferred={deferred}
        />
      ))}
    </div>
  );
}

function RuntimePostMediaImage({
  extraCount,
  fallbackAlt,
  media,
  deferred,
}: {
  extraCount: number;
  fallbackAlt: string;
  media: PostMediaRead;
  deferred: boolean;
}) {
  const uiText = useUiText("shell");
  const { ref: nearRef, visible: nearVisible } = useElementVisibility<HTMLDivElement>({ margin: 600, once: true, identity: media.url });
  const resource = useRuntimeMediaResource(media.url, !deferred || nearVisible);
  const [failedImage, setFailedImage] = useState<string | null>(null);
  const failed = resource.error || failedImage === `${resource.url}:${resource.attempt}`;
  const width = media.width && media.width > 0 ? media.width : undefined;
  const height = media.height && media.height > 0 ? media.height : undefined;
  return (
    <div ref={nearRef} className={styles.mediaFrame} style={{ aspectRatio: width && height ? `${width} / ${height}` : "4 / 3" }}>
      {failed ? <Button variant="ghost" onClick={event => { event.stopPropagation(); setFailedImage(null); resource.retry(); }}>{uiText("이미지 다시 불러오기")}</Button> : null}
      {resource.url && !failed ? (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        key={resource.attempt}
        src={resource.url}
        width={width} height={height}
        onError={() => setFailedImage(`${resource.url}:${resource.attempt}`)}
        alt={media.alt_text.trim() || fallbackAlt}
        className={styles.mediaImage}
        loading={deferred ? "lazy" : "eager"}
      />) : null}
      {extraCount > 0 ? (
        <span className={styles.mediaMore} aria-label={uiText("추가 이미지 {{value0}}개", {value0: extraCount})}>
          +{extraCount}
        </span>
      ) : null}
    </div>
  );
}
