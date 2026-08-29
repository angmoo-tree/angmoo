import type { ReactNode } from "react";

import { DeviceShell } from "@/features/device-shell/public";

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
    <header className={styles.header}>
      <div className={styles.identity}>
        <div className={styles.eyebrow}>World App</div>
        <h1 className={styles.title}>{worldName}</h1>
      </div>
      {status}
    </header>
  );

  return (
    <DeviceShell
      ariaLabel={`${worldName} World 앱`}
      header={header}
      navigation={navigation}
      surface="world-app"
      worldId={worldId}
    >
      <div className={styles.content}>{children}</div>
    </DeviceShell>
  );
}
