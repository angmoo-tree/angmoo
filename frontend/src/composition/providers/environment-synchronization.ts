import { ApiRequestError } from "@/lib/http/api-request";
import type { UserEnvironment } from "@/types/user-environment";

type Detection = { preferred_language: string | null; timezone: string | null };
type Report = Detection & { client_id: string; lease_token: string | null; expected_revision: number; sequence: number };
export type EnvironmentLease = {
  clientId: string; token: string | null; sequence: number;
  lastSuccessful?: { detected: Detection; at: number };
};
type Ports = {
  read: (signal: AbortSignal) => Promise<UserEnvironment>;
  write: (data: Report, signal: AbortSignal) => Promise<UserEnvironment>;
  detect: () => Detection;
  now?: () => number;
  wallNow?: () => number;
  wait?: (milliseconds: number, signal: AbortSignal) => Promise<void>;
};

function delay(milliseconds: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    signal.throwIfAborted();
    const abort = () => { clearTimeout(timer); reject(signal.reason); };
    const timer = setTimeout(() => { signal.removeEventListener("abort", abort); resolve(); }, milliseconds);
    signal.addEventListener("abort", abort, { once: true });
  });
}

/** One owner round. Only a definitely rolled-back typed 503 permits POST retry. */
export async function synchronizeEnvironment(lease: EnvironmentLease, ports: Ports, ownerSignal: AbortSignal) {
  const controller = new AbortController();
  const abort = () => controller.abort(ownerSignal.reason);
  if (ownerSignal.aborted) abort();
  else ownerSignal.addEventListener("abort", abort, { once: true });
  const timer = setTimeout(() => controller.abort(new DOMException("Environment round expired", "TimeoutError")), 8_000);
  const signal = controller.signal;
  const now = ports.now ?? (() => performance.now());
  const deadline = now() + 8_000;
  try {
    for (let attempt = 0; attempt < 3; attempt++) {
      signal.throwIfAborted();
      const current = await ports.read(signal);
      signal.throwIfAborted();
      const detected = ports.detect();
      if (current.synchronization !== "active_owner" && current.synchronization !== "awaiting_detector") {
        throw new Error("environment_synchronization_invalid");
      }
      if (!detected.preferred_language && !detected.timezone) return current;
      // The server owns expiry. Browser clocks and missing timezone suffixes
      // must never turn a live lease into permission to claim it.
      if (current.synchronization === "active_owner") {
        if (!lease.token) return current;
        const last = lease.lastSuccessful;
        if (last && now() - last.at < 60_000 &&
            last.detected.preferred_language === detected.preferred_language &&
            last.detected.timezone === detected.timezone) return current;
      }
      try {
        const result = await ports.write({ client_id: lease.clientId, lease_token: lease.token,
          expected_revision: current.environment_revision, sequence: ++lease.sequence, ...detected }, signal);
        signal.throwIfAborted();
        lease.token = result.lease_token ?? lease.token;
        lease.lastSuccessful = { detected: { ...detected }, at: now() };
        return result;
      } catch (error) {
        signal.throwIfAborted();
        if (error instanceof ApiRequestError && error.status === 409) {
          if (!["environment_detector_owned", "environment_sequence_stale", "environment_revision_conflict"].includes(error.code ?? "")) throw error;
          if (error.code !== "environment_revision_conflict") lease.token = null;
          lease.lastSuccessful = undefined;
          const reconciled = await ports.read(signal);
          signal.throwIfAborted();
          return reconciled;
        }
        if (!(error instanceof ApiRequestError) || error.status !== 503 ||
            error.code !== "environment_temporarily_busy" || attempt === 2) throw error;
        const after = error.retryAfter;
        const requested = after && /^\d+$/.test(after) ? Number(after) * 1_000
          : after ? Date.parse(after) - (ports.wallNow ?? Date.now)() : 1_000;
        const wait = Number.isFinite(requested) ? Math.max(100, requested) : 1_000;
        if (wait >= deadline - now()) throw error;
        await (ports.wait ?? delay)(wait, signal);
        // The next attempt reads current revision and detects current values;
        // no old payload or final permission decision crosses this boundary.
      }
    }
    throw new Error("environment_sync_failed");
  } finally {
    clearTimeout(timer);
    ownerSignal.removeEventListener("abort", abort);
  }
}
