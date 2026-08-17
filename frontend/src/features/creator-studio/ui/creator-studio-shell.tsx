import type { ReactNode } from "react";

import styles from "./creator-studio-shell.module.css";

type CreatorStudioShellProps = {
  children: ReactNode;
  navigation: ReactNode;
};

export function CreatorStudioShell({
  children,
  navigation,
}: CreatorStudioShellProps) {
  return (
    <div className={styles.root} data-product-shell="creator-studio">
      <aside className={styles.navigation} aria-label="Creator Studio 탐색">
        <p className={styles.brand}>Creator Studio</p>
        {navigation}
      </aside>
      <main className={styles.workspace}>{children}</main>
    </div>
  );
}
