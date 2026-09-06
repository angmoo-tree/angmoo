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
    >
      <div className={styles.screen}>
        <div
          aria-hidden="true"
          className={styles.titlebarInset}
          data-device-titlebar-inset="true"
        />
        {header ? <div className={styles.header}>{header}</div> : null}
        <div className={styles.content} data-device-scroll-owner="true">
          {children}
        </div>
        {footer ? <footer className={styles.footer}>{footer}</footer> : null}
      </div>
    </section>
  );
}
