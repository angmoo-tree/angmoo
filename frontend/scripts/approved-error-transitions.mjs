// Exact approved message transitions from 77aa85f7/b9e6142e.
// Historical source/request/session baselines stay immutable. These fixtures
// permit only the accepted typed/i18n error changes, never arbitrary failures.
const messages = new Map([
  ["401:Not authenticated", "Please sign in again."],
  ["401:fixture failure", "Please sign in again."],
  ["401:fixture", "Please sign in again."],
  ["401:{broken", "Please sign in again."],
  ["422:핸들은 영문 소문자, 숫자, 밑줄(_)만 사용할 수 있습니다.", "Handles can contain only lowercase letters, numbers, and underscores."],
  ["422:목표 활동 간격은 최소 30분 이상으로 설정해주세요.", "Set the target activity interval to at least 30 minutes."],
  ["422:목표 활동 간격은 하루 1440분 이하로 설정해주세요.", "Set the target activity interval to no more than 1440 minutes."],
  ["422:목표 활동 간격 값을 확인해주세요.", "Check the target activity interval."],
  ["422:하루 리플 작성 상한은 0개 이상 60개 이하로 설정해주세요.", "Set the daily reply limit between 0 and 60."],
  ["422:하루 글 쓰기 상한은 0개 이상 30개 이하로 설정해주세요.", "Set the daily post limit between 0 and 30."],
  ["422:fixture failure", "Please check the submitted values."],
  ["422:", "Please check the submitted values."],
  ["422:server message", "Please check the submitted values."],
  ["422:server detail", "Please check the submitted values."],
  ["422:second", "Please check the submitted values."],
  ["422:http_422", "Please check the submitted values."],
  ["422:Request failed with 422", "Please check the submitted values."],
  ["503:fixture failure", "The request could not be completed. Please try again."],
  ["503:요청 처리 중 서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요.", "The request could not be completed. Please try again."],
  ["503:offline", "The request could not be completed. Please try again."],
  ["503:http_503", "The request could not be completed. Please try again."],
]);

export function approvedErrorMessage(historicalMessage, status) {
  return messages.get(`${status}:${historicalMessage}`) ?? historicalMessage;
}
