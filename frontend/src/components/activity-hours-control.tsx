"use client";

const inputClassName =
  "h-14 w-full rounded-full border border-[#e1e5eb] bg-white px-5 text-[16px] font-medium text-[#101828] outline-none focus:border-[#ff6b6b] focus:ring-2 focus:ring-[#ffe2e2]";

export const DEFAULT_ACTIVE_HOURS_START = "14:00";
export const DEFAULT_ACTIVE_HOURS_END = "22:00";
export const DEFAULT_ACTIVITY_INTERVAL_MINUTES = 60;
export const MAX_ACTIVE_HOURS_MINUTES = 17 * 60;
export const ACTIVE_HOURS_LIMIT_MESSAGE =
  "활동 시간은 최대 17시간까지 설정할 수 있습니다.";

export const ACTIVE_HOUR_PRESETS = [
  { key: "morning", label: "오전 중심", start: "06:00", end: "14:00" },
  { key: "afternoon", label: "오후 중심", start: "14:00", end: "22:00" },
  { key: "night", label: "심야 중심", start: "22:00", end: "06:00" },
  { key: "custom", label: "직접 설정", start: "", end: "" },
] as const;

const START_TIME_OPTIONS = buildTimeOptions(false);
const END_TIME_OPTIONS = buildTimeOptions(true);

export function defaultActiveHoursForCurrentKst() {
  const currentHour = Number(
    new Intl.DateTimeFormat("en-US", {
      timeZone: "Asia/Seoul",
      hour: "2-digit",
      hour12: false,
    }).format(new Date()),
  );
  if (currentHour >= 6 && currentHour < 14) {
    return { start: "06:00", end: "14:00" };
  }
  if (currentHour >= 14 && currentHour < 22) {
    return { start: "14:00", end: "22:00" };
  }
  return { start: "22:00", end: "06:00" };
}

export function ActiveHoursControl({
  start,
  end,
  onChange,
  className = "mb-5",
}: {
  start: string;
  end: string;
  onChange: (start: string, end: string) => void;
  className?: string;
}) {
  const validation = getActiveHoursValidation(start, end);
  const selectedPreset =
    ACTIVE_HOUR_PRESETS.find(
      (preset) => preset.key !== "custom" && preset.start === start && preset.end === end,
    )?.key ?? "custom";

  return (
    <div className={className}>
      <input type="hidden" name="active_hours_start" value={start} />
      <input type="hidden" name="active_hours_end" value={end} />
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-[15px] font-extrabold text-[#344054]">활동 시간대</h3>
        <span className="rounded-full bg-[#f2f4f7] px-3 py-1 text-[12px] font-extrabold text-[#667085]">
          {`${start}-${end}`}
        </span>
      </div>
      <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {ACTIVE_HOUR_PRESETS.map((preset) => {
          const selected = selectedPreset === preset.key;
          return (
            <button
              key={preset.key}
              type="button"
              onClick={() => {
                if (preset.key !== "custom") onChange(preset.start, preset.end);
              }}
              className={`h-11 rounded-full border px-3 text-[14px] font-extrabold transition-colors ${
                selected
                  ? "border-[#ff6b6b] bg-[#fff0ef] text-[#ff6b6b]"
                  : "border-[#e1e5eb] bg-white text-[#667085] hover:border-[#ffb5b5]"
              }`}
            >
              {preset.label}
            </button>
          );
        })}
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <TimeSelect
          label="활동 시작"
          value={start}
          options={START_TIME_OPTIONS}
          onChange={(value) => onChange(value, end)}
        />
        <TimeSelect
          label="활동 마감"
          value={end}
          options={END_TIME_OPTIONS}
          onChange={(value) => onChange(start, value)}
        />
      </div>
      <p
        aria-live="polite"
        className={`mt-1 rounded-[18px] px-4 py-3 text-[13px] font-bold leading-5 ${
          validation.valid
            ? "bg-[#f6f7f9] text-[#667085]"
            : "border border-[#ffd7d7] bg-[#fff5f5] text-[#c24141]"
        }`}
      >
        {validation.message}
      </p>
    </div>
  );
}

function TimeSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="mb-4 block">
      <span className="mb-2 block text-[15px] font-bold text-[#344054]">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className={inputClassName}
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </label>
  );
}

function buildTimeOptions(includeEndOfDay: boolean) {
  const options: string[] = [];
  for (let minutes = 0; minutes < 24 * 60; minutes += 30) {
    const hour = Math.floor(minutes / 60);
    const minute = minutes % 60;
    options.push(`${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`);
  }
  if (includeEndOfDay) options.push("24:00");
  return options;
}

export function formatActiveHoursDescription(start: string, end: string) {
  return getActiveHoursValidation(start, end).message;
}

export function getActiveHoursValidation(start: string, end: string): {
  valid: boolean;
  durationMinutes: number | null;
  message: string;
} {
  const duration = activeHoursDurationMinutes(start, end);
  if (duration === null) {
    return {
      valid: false,
      durationMinutes: null,
      message: ACTIVE_HOURS_LIMIT_MESSAGE,
    };
  }
  if (duration <= 0) {
    return {
      valid: false,
      durationMinutes: duration,
      message: "활동 시작과 마감은 서로 달라야 합니다.",
    };
  }
  if (duration > MAX_ACTIVE_HOURS_MINUTES) {
    return {
      valid: false,
      durationMinutes: duration,
      message: `${ACTIVE_HOURS_LIMIT_MESSAGE} 현재 선택은 ${formatActiveHoursDuration(
        duration,
      )}입니다.`,
    };
  }
  if (start < end) {
    return {
      valid: true,
      durationMinutes: duration,
      message: `매일 ${start}부터 ${end} 전까지 활동합니다.`,
    };
  }
  return {
    valid: true,
    durationMinutes: duration,
    message: `매일 ${start}부터 다음 날 ${end} 전까지 활동합니다.`,
  };
}

function formatActiveHoursDuration(durationMinutes: number) {
  const hours = Math.floor(durationMinutes / 60);
  const minutes = durationMinutes % 60;
  if (minutes === 0) return `${hours}시간`;
  if (hours === 0) return `${minutes}분`;
  return `${hours}시간 ${minutes}분`;
}

function parseActiveHour(value: string, allowEndOfDay: boolean) {
  if (allowEndOfDay && value === "24:00") return 24 * 60;
  const match = /^(\d{2}):(\d{2})$/.exec(value);
  if (!match) return null;
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (hour < 0 || hour > 23 || ![0, 30].includes(minute)) return null;
  return hour * 60 + minute;
}

function activeHoursDurationMinutes(start: string, end: string) {
  const startMinutes = parseActiveHour(start, false);
  const endMinutes = parseActiveHour(end, true);
  if (startMinutes === null || endMinutes === null) return null;
  if (startMinutes === endMinutes) return 0;
  return (endMinutes - startMinutes + 24 * 60) % (24 * 60);
}

export function isValidActiveHours(start: string, end: string) {
  const duration = activeHoursDurationMinutes(start, end);
  return duration !== null && duration > 0 && duration <= MAX_ACTIVE_HOURS_MINUTES;
}
