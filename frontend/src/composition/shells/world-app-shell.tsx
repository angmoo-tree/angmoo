"use client";

import { useUiText } from "@/hooks/use-ui-text";
import type { ReactNode } from "react";

import { DeviceShell } from "@/components/layout/device-shell";

import styles from "./world-app-shell.module.css";

type WorldAppShellProps = {
  children: ReactNode;
  headerMode?: "shell" | "content";
  navigation: ReactNode;
  status?: ReactNode;
  worldId: string;
  worldName: string;
};

export function WorldAppShell({
  children,
  headerMode = "shell",
  navigation,
  status,
  worldId,
  worldName,
}: WorldAppShellProps) {
  const uiText = useUiText("shell");
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
      ariaLabel={uiText("{{value0}} World 앱", {value0: worldName})}
      header={headerMode === "content" ? undefined : header}
      navigation={navigation}
      surface="world-app"
      worldId={worldId}
    >
      <div className={styles.content}>{children}</div>
    </DeviceShell>
  );
}
