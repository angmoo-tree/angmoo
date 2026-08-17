import type { ReactNode } from "react";

import styles from "./creator-studio-shell.module.css";

type CreatorStudioShellProps = {
  children: ReactNode;
  navigation: ReactNode;
  utility?: ReactNode;
};

export function CreatorStudioShell({
  children,
  navigation,
  utility,
}: CreatorStudioShellProps) {
  return (
    <div className={styles.root} data-product-shell="creator-studio">
      <aside className={styles.navigation} aria-label="Creator Studio 탐색">
        <div className={styles.brandRow}>
          <div>
            <p className={styles.eyebrow}>ANGMOO LOCAL</p>
            <p className={styles.brand}>Creator Studio</p>
          </div>
          {utility}
        </div>
        {navigation}
      </aside>
      <main className={styles.workspace}>{children}</main>
    </div>
  );
}
