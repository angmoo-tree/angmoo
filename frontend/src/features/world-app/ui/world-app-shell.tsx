import type { ReactNode } from "react";

import { DeviceFrame } from "@/shared/ui/public";

import styles from "./world-app-shell.module.css";

type WorldAppShellProps = {
  children: ReactNode;
  navigation: ReactNode;
  status?: ReactNode;
  worldId: string;
  worldName: string;
};

export function WorldAppShell({
  children,
  navigation,
  status,
  worldId,
  worldName,
}: WorldAppShellProps) {
  const header = (
    <div className={styles.header}>
      <div className={styles.identity}>
        <div className={styles.eyebrow}>World App</div>
        <h1 className={styles.title}>{worldName}</h1>
      </div>
      {status}
    </div>
  );

  return (
    <main className={styles.root} data-product-surface="world-app" data-world-id={worldId}>
      <DeviceFrame
        ariaLabel={`${worldName} World 앱`}
        header={header}
        footer={<div className={styles.footer}>{navigation}</div>}
      >
        <div className={styles.content}>{children}</div>
      </DeviceFrame>
    </main>
  );
}
