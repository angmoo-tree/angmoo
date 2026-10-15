import styles from "./count-badge.module.css";

/** Numeric presentation only; the parent owns meaning and the accessible name. */
export function CountBadge({ count, stale = false }: { count: number | null; stale?: boolean }) {
  if (count === null || count <= 0) return null;
  return <span className={styles.badge} data-count-badge data-stale={stale || undefined} aria-hidden="true">{count > 99 ? "99+" : count}</span>;
}
