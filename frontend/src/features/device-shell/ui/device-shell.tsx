import type { ReactNode } from "react";

import { DeviceFrame } from "@/shared/ui/public";

import styles from "./device-shell.module.css";

export type DeviceShellProps = {
  ariaLabel: string;
  children: ReactNode;
  header?: ReactNode;
  navigation?: ReactNode;
  surface: string;
  worldId?: string;
};

export function DeviceShell({
  ariaLabel,
  children,
  header,
  navigation,
  surface,
  worldId,
}: DeviceShellProps) {
  return (
    <main
      className={styles.root}
      data-device-shell="phone"
      data-main-landmark-owner="device-shell"
      data-product-surface={surface}
      data-world-id={worldId}
    >
      <DeviceFrame ariaLabel={ariaLabel} footer={navigation} header={header}>
        <div className={styles.content}>{children}</div>
      </DeviceFrame>
    </main>
  );
}
