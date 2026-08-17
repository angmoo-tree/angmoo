import type { ReactNode } from "react";

import { DeviceFrame } from "@/shared/ui/public";

import styles from "./device-home-shell.module.css";

type DeviceHomeShellProps = {
  children: ReactNode;
  status?: ReactNode;
  title?: string;
};

export function DeviceHomeShell({
  children,
  status,
  title = "Angmoo",
}: DeviceHomeShellProps) {
  const header = (
    <div className={styles.header}>
      <div>
        <div className={styles.eyebrow}>Local Device</div>
        <h1 className={styles.title}>{title}</h1>
      </div>
      {status}
    </div>
  );

  return (
    <main className={styles.root} data-product-surface="device-home">
      <DeviceFrame ariaLabel={`${title} Device Home`} header={header}>
        <div className={styles.content}>
          <div className={styles.grid} role="list">
            {children}
          </div>
        </div>
      </DeviceFrame>
    </main>
  );
}
