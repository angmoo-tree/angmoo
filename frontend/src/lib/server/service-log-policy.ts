import "server-only";

// LOCAL: server process policy only. No browser configuration, timer, database
// capture or console monkey patch. An absent policy retains existing behavior.
type Policy = { profile_version: string; service: string; launch_id: string; requested_mode: string;
  started_at_utc: string; duration_seconds: number; detailed_until_utc: string | null; remaining_seconds: number };
const VERSION = "angmoo-service-log.v1";
const FIELDS = ["profile_version", "service", "launch_id", "requested_mode", "started_at_utc", "duration_seconds", "detailed_until_utc", "remaining_seconds"].sort();

export function decodeServiceLogPolicy(raw: string, launch: string | undefined): Policy {
  if (raw.length > 4096) throw new Error("policy_size");
  const value = JSON.parse(raw);
  if (!value || typeof value !== "object" || Object.keys(value).sort().join() !== FIELDS.join() ||
      value.profile_version !== VERSION || value.service !== "frontend" || !launch || !/^[0-9a-f]{32}$/.test(launch) || value.launch_id !== launch)
    throw new Error("policy_schema");
  const seconds = value.duration_seconds, remaining = value.remaining_seconds;
  if (!Number.isInteger(seconds) || seconds < 0 || seconds > 3600 || typeof remaining !== "number" || !Number.isFinite(remaining) || remaining < 0 || remaining > seconds)
    throw new Error("policy_duration");
  const started = Date.parse(value.started_at_utc);
  if (!Number.isFinite(started) || typeof value.started_at_utc !== "string" || !/(Z|[+-]\d\d:\d\d)$/.test(value.started_at_utc)) throw new Error("policy_clock");
  if (value.requested_mode === "basic") {
    if (seconds || remaining || value.detailed_until_utc !== null) throw new Error("policy_basic");
  } else if (value.requested_mode === "detailed") {
    if (seconds < 60 || seconds % 60 || typeof value.detailed_until_utc !== "string" || !/(Z|[+-]\d\d:\d\d)$/.test(value.detailed_until_utc) || Date.parse(value.detailed_until_utc) - started !== seconds * 1000)
      throw new Error("policy_clock");
  } else throw new Error("policy_mode");
  return value;
}

export function servicePolicyClock(value: Policy, monotonic = () => performance.now(), wall = () => Date.now()) {
  const deadline = monotonic() + value.remaining_seconds * 1000;
  const expiry = value.detailed_until_utc ? Date.parse(value.detailed_until_utc) : 0;
  let expired = value.requested_mode !== "detailed";
  return () => {
    expired = expired || monotonic() >= deadline || wall() >= expiry;
    return !expired;
  };
}

let clock: (() => boolean) | undefined;
export function detailedServiceLogs() {
  const raw = process.env.ANGMOO_SERVICE_LOG_POLICY;
  if (raw === undefined) return true;
  if (!clock) {
    let value: Policy;
    try { value = decodeServiceLogPolicy(raw, process.env.ANGMOO_LAUNCH_ID); }
    catch {
      value = { profile_version: VERSION, service: "frontend", launch_id: /^[0-9a-f]{32}$/.test(process.env.ANGMOO_LAUNCH_ID ?? "") ? process.env.ANGMOO_LAUNCH_ID! : "",
        requested_mode: "basic", started_at_utc: "", duration_seconds: 0, detailed_until_utc: null, remaining_seconds: 0 };
      console.warn(JSON.stringify({ event: "service_log_policy_invalid", service: "frontend", fallback: "basic" }));
    }
    clock = servicePolicyClock(value);
    console.info(JSON.stringify({ event: "service_log_policy_applied", profile_version: VERSION,
      service: "frontend", launch_id: value.launch_id, effective_mode: clock() ? "detailed" : "basic", detailed_until_utc: value.detailed_until_utc }));
  }
  return clock();
}
