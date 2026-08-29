import type { ReactNode } from "react";

import styles from "./relationship-graph-frame.module.css";

export function RelationshipGraphFrame({ children }: { children: ReactNode }) {
  return (
    <main
      aria-label="Angmoo Relationship Graph"
      className={styles.root}
      data-main-landmark-owner="relationship-graph"
      data-product-shell="relationship-graph"
      data-product-surface="relationship-graph"
    >
      {children}
    </main>
  );
}
