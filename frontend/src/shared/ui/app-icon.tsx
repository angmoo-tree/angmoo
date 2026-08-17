import Link from "next/link";
import type { CSSProperties, ReactNode } from "react";

import styles from "./app-icon.module.css";

type AppIconProps = {
  badge?: ReactNode;
  description?: string;
  disabled?: boolean;
  href?: string;
  label: string;
  visual: ReactNode;
  visualBackground?: string;
};

export function AppIcon({
  badge,
  description,
  disabled = false,
  href,
  label,
  visual,
  visualBackground,
}: AppIconProps) {
  const className = [
    styles.entry,
    href && !disabled ? styles.entryInteractive : "",
    disabled ? styles.entryDisabled : "",
  ]
    .filter(Boolean)
    .join(" ");
  const style = visualBackground
    ? ({ "--app-icon-background": visualBackground } as CSSProperties)
    : undefined;
  const contents = (
    <>
      <span className={styles.visual} aria-hidden="true" style={style}>
        {visual}
        {badge ? <span className={styles.badge}>{badge}</span> : null}
      </span>
      <span className={styles.label}>{label}</span>
    </>
  );

  if (href && !disabled) {
    return (
      <Link
        className={className}
        href={href}
        aria-label={description ?? label}
        role="listitem"
      >
        {contents}
      </Link>
    );
  }

  return (
    <div
      className={className}
      aria-label={description ?? label}
      data-disabled={disabled || undefined}
      role="listitem"
    >
      {contents}
    </div>
  );
}
