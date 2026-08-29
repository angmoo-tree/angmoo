import {
  CheckCircle2,
  CircleAlert,
  Info,
  TriangleAlert,
} from "lucide-react";
import type { HTMLAttributes, ReactNode } from "react";

import { classNames } from "./class-names";
import styles from "./semantic-foundation.module.css";

export type ToastTone = "neutral" | "success" | "danger";

export type ToastProps = HTMLAttributes<HTMLDivElement> & {
  children: ReactNode;
  tone?: ToastTone;
};

export function Toast({ children, className, tone = "neutral", ...props }: ToastProps) {
  const Icon = tone === "success" ? CheckCircle2 : tone === "danger" ? CircleAlert : Info;
  return (
    <div
      {...props}
      role="status"
      aria-live="polite"
      data-ui-primitive="toast"
      className={classNames(
        styles.toast,
        tone === "success" && styles.toastSuccess,
        tone === "danger" && styles.toastDanger,
        className,
      )}
    >
      <Icon className={styles.feedbackIcon} aria-hidden="true" />
      <div>{children}</div>
    </div>
  );
}

export type InlineErrorProps = HTMLAttributes<HTMLDivElement> & {
  children: ReactNode;
};

export function InlineError({ children, className, ...props }: InlineErrorProps) {
  return (
    <div
      {...props}
      role="alert"
      data-ui-primitive="inline-error"
      className={classNames(styles.inlineError, className)}
    >
      <CircleAlert className={styles.feedbackIcon} aria-hidden="true" />
      <div>{children}</div>
    </div>
  );
}

export type EmptyStateProps = HTMLAttributes<HTMLDivElement> & {
  action?: ReactNode;
  description: string;
  icon?: ReactNode;
  title: string;
};

export function EmptyState({
  action,
  className,
  description,
  icon,
  title,
  ...props
}: EmptyStateProps) {
  return (
    <section
      {...props}
      data-ui-primitive="empty-state"
      className={classNames(styles.emptyState, className)}
    >
      {icon}
      <h3 className={styles.feedbackTitle}>{title}</h3>
      <p className={styles.feedbackDescription}>{description}</p>
      {action}
    </section>
  );
}

export type DegradedPanelProps = HTMLAttributes<HTMLDivElement> & {
  action?: ReactNode;
  description: string;
  title: string;
};

export function DegradedPanel({
  action,
  className,
  description,
  title,
  ...props
}: DegradedPanelProps) {
  return (
    <section
      {...props}
      aria-live="polite"
      data-ui-primitive="degraded-panel"
      className={classNames(styles.degradedPanel, className)}
    >
      <TriangleAlert className={styles.feedbackIcon} aria-hidden="true" />
      <h3 className={styles.feedbackTitle}>{title}</h3>
      <p className={styles.feedbackDescription}>{description}</p>
      {action}
    </section>
  );
}
