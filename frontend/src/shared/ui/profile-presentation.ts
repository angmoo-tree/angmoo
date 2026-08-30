export function formatHandle(handle?: string | null) {
  return handle ? `@${handle}` : "";
}

export function getProfileInitial(name: string) {
  return name.trim().charAt(0).toUpperCase() || "A";
}

export const OFFICIAL_OPERATOR_DISPLAY_NAME = "운영자";

export function isOfficialOperatorName(name?: string | null) {
  return name?.trim() === OFFICIAL_OPERATOR_DISPLAY_NAME;
}

const PROFILE_COLORS = [
  "bg-brand-soft text-text-strong",
  "bg-state-running-surface text-state-running",
  "bg-state-success-surface text-state-success",
  "bg-state-degraded-surface text-state-degraded",
  "bg-state-warning-surface text-state-warning",
  "bg-surface-muted text-text-strong",
];

export function getProfileColor(name: string) {
  if (isOfficialOperatorName(name)) {
    return "bg-brand-soft text-text-strong";
  }

  const seed = Array.from(name).reduce(
    (sum, character) => sum + character.charCodeAt(0),
    0,
  );
  return PROFILE_COLORS[seed % PROFILE_COLORS.length];
}

const API_TIMEZONE_OFFSET_PATTERN = /(?:Z|[+-]\d{2}:?\d{2})$/i;

export function parseApiInstant(value: string) {
  const normalized = API_TIMEZONE_OFFSET_PATTERN.test(value)
    ? value
    : `${value}Z`;
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function apiInstantTimestamp(value: string | null) {
  if (!value) return Number.NaN;
  return parseApiInstant(value)?.getTime() ?? Number.NaN;
}

export function formatDate(value: string, timeZone = "Asia/Seoul") {
  const date = parseApiInstant(value);
  if (!date) return "-";
  const parts = new Intl.DateTimeFormat("ko-KR", {
    timeZone,
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((item) => item.type === type)?.value ?? "";
  return `${part("month")}.${part("day")} ${part("hour")}:${part("minute")}`;
}
