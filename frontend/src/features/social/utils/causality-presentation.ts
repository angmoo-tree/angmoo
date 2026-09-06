export type SocialCausalityPhase =
  | "observation_pending"
  | "observation_failed"
  | "observed_no_action"
  | "observed_follow_up_failed"
  | "observed_follow_up_succeeded";

export type SocialCausalityPresentation = {
  phase: SocialCausalityPhase;
  label: string;
};

function numberValue(summary: Record<string, unknown>, key: string) {
  const value = summary[key];
  return typeof value === "number" ? value : 0;
}

function stringValue(summary: Record<string, unknown>, key: string) {
  const value = summary[key];
  return typeof value === "string" ? value : null;
}

/** Present causal state without inferring a character's private emotions. */
export function presentSocialCausality(
  summary: Record<string, unknown> | null,
): SocialCausalityPresentation | null {
  if (!summary) return null;
  const outcome = stringValue(summary, "outcome");
  const reason = stringValue(summary, "reason_code");
  const receiptCount = numberValue(summary, "observation_receipt_count");

  if (outcome === "OBSERVATION_FAILED" || reason === "observation_failed") {
    return {
      phase: "observation_failed",
      label: "관찰에 실패해 안전하게 재시도할 예정이에요.",
    };
  }
  if (receiptCount > 0 && outcome === "NO_ACTION") {
    return {
      phase: "observed_no_action",
      label: "게시글을 관찰했지만 이번에는 공개 후속 행동을 하지 않았어요.",
    };
  }
  if (receiptCount > 0 && outcome === "ACTION_SUCCEEDED") {
    return {
      phase: "observed_follow_up_succeeded",
      label: "관찰을 기록한 뒤 별도 후속 행동을 저장했어요.",
    };
  }
  if (receiptCount > 0 && outcome === "ACTION_REUSED") {
    return {
      phase: "observed_follow_up_succeeded",
      label: "기존 관찰과 후속 행동을 중복 없이 다시 사용했어요.",
    };
  }
  if (receiptCount > 0 && outcome?.endsWith("FAILED")) {
    return {
      phase: "observed_follow_up_failed",
      label: "관찰 기록은 유지됐지만 공개 후속 행동은 저장되지 않았어요.",
    };
  }
  if (numberValue(summary, "claimed_candidate_count") > 0) {
    return {
      phase: "observation_pending",
      label: "관찰할 게시글을 확인하고 있어요.",
    };
  }
  return null;
}
