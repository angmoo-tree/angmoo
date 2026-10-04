import { apiRequest as sendRequest, type RequestOptions, type RequestValidationFailure } from "@/lib/http/api-request";

// This feature preserves the validation messages accepted by its existing API.
// Legacy mixed-field responses remain compatible without a cross-feature import.
function getValidationMessage(detail: unknown[]): string | RequestValidationFailure | null {
  const first = detail.find((item) => item && typeof item === "object");
  if (!first || typeof first !== "object") return null;
  const loc = "loc" in first && Array.isArray(first.loc) ? first.loc : [];
  if (loc.includes("handle")) {
    return { code: "handle_format_invalid", message: "Handles can contain only lowercase letters, numbers, and underscores." };
  }
  const field = typeof loc.at(-1) === "string" ? loc.at(-1) : null;
  const type = "type" in first && typeof first.type === "string" ? first.type : "";
  const msg = "msg" in first && typeof first.msg === "string" ? first.msg : "";
  if (field === "activity_interval_minutes") {
    if (type.includes("greater") || msg.includes("greater than or equal")) {
      return { code: "activity_interval_too_small", message: "Set the target activity interval to at least 30 minutes.", params: { minimum: 30 } };
    }
    if (type.includes("less") || msg.includes("less than or equal")) {
      return { code: "activity_interval_too_large", message: "Set the target activity interval to no more than 1440 minutes.", params: { maximum: 1440 } };
    }
    return { code: "activity_interval_invalid", message: "Check the target activity interval." };
  }
  if (field === "max_comments_per_day") {
    return { code: "reply_limit_invalid", message: "Set the daily reply limit between 0 and 60.", params: { minimum: 0, maximum: 60 } };
  }
  if (field === "max_posts_per_day") {
    return { code: "post_limit_invalid", message: "Set the daily post limit between 0 and 30.", params: { minimum: 0, maximum: 30 } };
  }
  if ("msg" in first && typeof first.msg === "string") {
    return "Please check the submitted values.";
  }
  return null;
}

export function apiRequest<T>(path: string, options: RequestOptions = {}) {
  return sendRequest<T>(path, options, getValidationMessage);
}
