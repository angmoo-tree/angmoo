import type { ReactNode } from "react";

import styles from "./device-frame.module.css";

type DeviceFrameProps = {
  ariaLabel: string;
  children: ReactNode;
  footer?: ReactNode;
  header?: ReactNode;
};

export function DeviceFrame({
  ariaLabel,
  children,
  footer,
  header,
}: DeviceFrameProps) {
  return (
    <section
      className={styles.frame}
      aria-label={ariaLabel}
      data-product-shell="device"
      data-tauri-drag-region="deep"
    >
      <div className={styles.screen}>
        {header ? <header className={styles.header}>{header}</header> : null}
        <div className={styles.content}>{children}</div>
        {footer ? <footer className={styles.footer}>{footer}</footer> : null}
      </div>
    </section>
  );
}
