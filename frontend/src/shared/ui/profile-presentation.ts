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
  "bg-[#173B8F] text-white",
  "bg-[#0EA5E9] text-white",
  "bg-[#1E7A6D] text-white",
  "bg-[#7C3AED] text-white",
  "bg-[#F59E0B] text-[#101828]",
  "bg-[#101828] text-white",
];

export function getProfileColor(name: string) {
  if (isOfficialOperatorName(name)) {
    return "bg-[#ff6b6b] text-white";
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
