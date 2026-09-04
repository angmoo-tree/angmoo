import type { ReactNode } from "react";

import { DeviceShell } from "@/features/device-shell/ui/device-shell";
import { LocalDeviceNavigation } from "@/features/device-shell/ui/local-device-navigation";

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
    <header className={styles.header}>
      <div>
        <div className={styles.eyebrow}>Local Device</div>
        <h1 className={styles.title}>{title}</h1>
      </div>
      {status}
    </header>
  );

  return (
    <DeviceShell
      ariaLabel={`${title} Device Home`}
      header={header}
      navigation={<LocalDeviceNavigation />}
      surface="device-home"
    >
      <div className={styles.content}>
        <div className={styles.grid} role="list">
          {children}
        </div>
      </div>
    </DeviceShell>
  );
}
