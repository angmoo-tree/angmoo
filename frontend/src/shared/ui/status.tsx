import {
  CheckCircle2,
  CircleDot,
  CircleX,
  Clock3,
  MinusCircle,
  TriangleAlert,
} from "lucide-react";
import type { HTMLAttributes, ReactNode } from "react";

import { classNames } from "./class-names";
import styles from "@/components/ui/semantic-foundation.module.css";

export type BadgeProps = HTMLAttributes<HTMLSpanElement> & {
  children: ReactNode;
};

export function Badge({ children, className, ...props }: BadgeProps) {
  return (
    <span
      {...props}
      data-ui-primitive="badge"
      className={classNames(styles.badge, className)}
    >
      {children}
    </span>
  );
}

export type StatusChipTone =
  | "neutral"
  | "healthy"
  | "running"
  | "waiting"
  | "degraded"
  | "danger"
  | "disabled";

const TONE_CLASS: Record<StatusChipTone, string> = {
  neutral: styles.toneNeutral,
  healthy: styles.toneHealthy,
  running: styles.toneRunning,
  waiting: styles.toneWaiting,
  degraded: styles.toneDegraded,
  danger: styles.toneDanger,
  disabled: styles.toneDisabled,
};

const TONE_ICON: Record<StatusChipTone, typeof CircleDot> = {
  neutral: CircleDot,
  healthy: CheckCircle2,
  running: CircleDot,
  waiting: Clock3,
  degraded: TriangleAlert,
  danger: CircleX,
  disabled: MinusCircle,
};

export type StatusChipProps = HTMLAttributes<HTMLSpanElement> & {
  icon?: ReactNode | false;
  label: string;
  tone?: StatusChipTone;
};

export function StatusChip({
  className,
  icon,
  label,
  tone = "neutral",
  ...props
}: StatusChipProps) {
  const ToneIcon = TONE_ICON[tone];

  return (
    <span
      {...props}
      data-status-tone={tone}
      data-ui-primitive="status-chip"
      className={classNames(styles.statusChip, TONE_CLASS[tone], className)}
    >
      {icon === false ? null : icon ?? <ToneIcon className={styles.statusIcon} aria-hidden="true" />}
      <span>{label}</span>
    </span>
  );
}
