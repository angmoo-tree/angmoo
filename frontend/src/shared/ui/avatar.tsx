"use client";

import { useState, type HTMLAttributes } from "react";

import { classNames } from "./class-names";
import styles from "./semantic-foundation.module.css";

export type AvatarProps = Omit<HTMLAttributes<HTMLSpanElement>, "children"> & {
  alt?: string;
  decorative?: boolean;
  fallback: string;
  fallbackClassName?: string;
  imageClassName?: string;
  src?: string | null;
};

export function Avatar({
  alt = "",
  className,
  decorative = false,
  fallback,
  fallbackClassName,
  imageClassName,
  src,
  ...props
}: AvatarProps) {
  const [failedSource, setFailedSource] = useState<string | null>(null);

  const label = decorative ? undefined : alt || `${fallback} 프로필`;

  return (
    <span
      {...props}
      aria-hidden={decorative || undefined}
      aria-label={label}
      role={decorative ? undefined : "img"}
      data-ui-primitive="avatar"
      className={classNames(styles.avatar, className)}
    >
      {src && failedSource !== src ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={src}
          alt=""
          className={classNames(styles.avatarImage, imageClassName)}
          onError={() => setFailedSource(src)}
        />
      ) : (
        <span
          className={classNames(styles.avatarFallback, fallbackClassName)}
          aria-hidden="true"
        >
          {fallback}
        </span>
      )}
    </span>
  );
}
