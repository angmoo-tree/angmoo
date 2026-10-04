import type { ReactNode } from "react";

import styles from "./feed-header.module.css";

type FeedHeaderProps = {
  title: string;
  center: ReactNode;
  right: ReactNode;
  compactOnDesktop?: boolean;
  desktopAction?: ReactNode;
};

/** Presentation only: the screen owns identity, destinations and actions. */
export function FeedHeader({ title, center, right, compactOnDesktop = false, desktopAction }: FeedHeaderProps) {
  return (
    <header className={`${styles.row} ${compactOnDesktop ? styles.desktopCompact : ""}`} data-feed-header>
      <div className={styles.inner}>
        <h1 className={styles.title}>{title}</h1>
        <div className={styles.center} data-feed-header-center>{center}</div>
        <div className={styles.right} data-feed-header-right>{right}</div>
      </div>
      {desktopAction}
    </header>
  );
}
