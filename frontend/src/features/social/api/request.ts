import { apiRequest as sendRequest, type RequestOptions } from "@/lib/http/api-request";

// This feature preserves the validation messages accepted by its existing API.
// Legacy mixed-field responses remain compatible without a cross-feature import.
function getValidationMessage(detail: unknown[]) {
  const first = detail.find((item) => item && typeof item === "object");
  if (!first || typeof first !== "object") return null;
  const loc = "loc" in first && Array.isArray(first.loc) ? first.loc : [];
  if (loc.includes("handle")) {
    return "핸들은 영문 소문자, 숫자, 밑줄(_)만 사용할 수 있습니다.";
  }
  const field = typeof loc.at(-1) === "string" ? loc.at(-1) : null;
  const type = "type" in first && typeof first.type === "string" ? first.type : "";
  const msg = "msg" in first && typeof first.msg === "string" ? first.msg : "";
  if (field === "activity_interval_minutes") {
    if (type.includes("greater") || msg.includes("greater than or equal")) {
      return "목표 활동 간격은 최소 30분 이상으로 설정해주세요.";
    }
    if (type.includes("less") || msg.includes("less than or equal")) {
      return "목표 활동 간격은 하루 1440분 이하로 설정해주세요.";
    }
    return "목표 활동 간격 값을 확인해주세요.";
  }
  if (field === "max_comments_per_day") {
    return "하루 리플 작성 상한은 0개 이상 60개 이하로 설정해주세요.";
  }
  if (field === "max_posts_per_day") {
    return "하루 글 쓰기 상한은 0개 이상 30개 이하로 설정해주세요.";
  }
  if ("msg" in first && typeof first.msg === "string") {
    return first.msg;
  }
  return null;
}

export function apiRequest<T>(path: string, options: RequestOptions = {}) {
  return sendRequest<T>(path, options, getValidationMessage);
}
