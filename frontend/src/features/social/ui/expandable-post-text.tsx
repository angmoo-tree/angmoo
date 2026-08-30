"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { MentionedCharacterRef } from "../model/social-feed-contract";
import { MentionedText } from "./mentioned-text";
import styles from "./social-presentation.module.css";

export function ExpandablePostText({
  title,
  body,
  mentionedCharacters = [],
  clampClassName,
  textClassName,
  titleClassName = "font-bold",
}: {
  title: string;
  body: string;
  mentionedCharacters?: MentionedCharacterRef[];
  clampClassName: string;
  textClassName: string;
  titleClassName?: string;
}) {
  const textRef = useRef<HTMLParagraphElement | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [canExpand, setCanExpand] = useState(false);

  const measureOverflow = useCallback(() => {
    const element = textRef.current;
    if (!element || expanded) return;
    setCanExpand(element.scrollHeight > element.clientHeight + 1);
  }, [expanded]);

  useEffect(() => {
    if (expanded) return;

    const element = textRef.current;
    if (!element) return;

    const frame = window.requestAnimationFrame(measureOverflow);
    let observer: ResizeObserver | null = null;
    if ("ResizeObserver" in window) {
      observer = new ResizeObserver(measureOverflow);
      observer.observe(element);
    }
    window.addEventListener("resize", measureOverflow);

    return () => {
      window.cancelAnimationFrame(frame);
      observer?.disconnect();
      window.removeEventListener("resize", measureOverflow);
    };
  }, [expanded, measureOverflow]);

  return (
    <div>
      <p
        ref={textRef}
        className={`${textClassName} ${expanded ? "" : clampClassName}`}
      >
        {title ? (
          <>
            <span className={titleClassName}>
              <MentionedText text={title} mentionedCharacters={mentionedCharacters} />
            </span>{" "}
          </>
        ) : null}
        <MentionedText text={body} mentionedCharacters={mentionedCharacters} />
      </p>
      {!expanded && canExpand ? (
        <button
          type="button"
          data-post-card-ignore
          onClick={() => setExpanded(true)}
          className={styles.expandButton}
          aria-expanded={expanded}
        >
          더보기
        </button>
      ) : null}
    </div>
  );
}
