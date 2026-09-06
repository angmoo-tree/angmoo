import { StatusChip, type StatusChipTone } from "./status";

export type StatusBadgeTone = "blocked" | "degraded" | "healthy" | "neutral";

type StatusBadgeProps = {
  label: string;
  tone?: StatusBadgeTone;
};

export function StatusBadge({ label, tone = "neutral" }: StatusBadgeProps) {
  const mappedTone: StatusChipTone =
    tone === "blocked" ? "danger" : tone === "healthy" ? "healthy" : tone;
  return <StatusChip label={label} tone={mappedTone} />;
}
