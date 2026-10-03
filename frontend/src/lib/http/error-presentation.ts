import { ApiRequestError } from "@/lib/http/error-contract";
type ErrorText = (message: string, values?: Record<string, string | number>) => string;

/** Render only the stable transport contract, never a Provider or validator body. */
export function formatUiRequestFailure(error: unknown, fallback: string, text: ErrorText,
  date: (utc: string) => string, now = Date.now()) {
  if (!(error instanceof ApiRequestError)) return text(fallback);
  const message = error.status === 401 ? "Please sign in again."
    : error.status === 403 ? "You do not have permission for this action."
    : error.status === 409 ? "The state changed. Refresh and try again."
    : error.status === 422 ? "Please check the submitted values."
    : error.status === 429 ? "The usage limit was reached. Please try again later." : fallback;
  const details = [text(message)];
  const allowance = error.params.allowance_at;
  const retry = error.params.retry_at;
  if (typeof allowance === "string") details.push(text("Allowance available at: {{time}}", {time: date(allowance)}));
  let retryAt = typeof retry === "string" ? retry : null;
  if (!retryAt && error.retryAfter) {
    const duration = /^\d+$/.test(error.retryAfter) ? Number(error.retryAfter) : null;
    const instant = duration !== null ? now + duration * 1000 : Date.parse(error.retryAfter);
    if (Number.isFinite(instant) && instant >= 0 && instant <= 8.64e15) retryAt = new Date(instant).toISOString();
  }
  if (retryAt) details.push(text("Retry at: {{time}}", {time: date(retryAt)}));
  return details.join(" ");
}
