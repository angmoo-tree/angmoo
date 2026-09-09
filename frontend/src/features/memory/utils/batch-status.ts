/** Memory-owned recovery copy; provider payloads and unknown codes stay private. */
export function memoryBatchFailureMessage(code: string | null): string {
  switch (code) {
    case "memory_selection_settings_required":
    case "memory_selection_credential_purpose_invalid":
      return "쪽지용 AI 설정을 확인해 주세요. 정리할 경험은 보관되어 있어요.";
    case "memory_selection_model_unsupported":
    case "memory_selection_model_invalid":
      return "기억 정리에 사용할 수 있는 모델을 선택해 주세요. 경험은 보관되어 있어요.";
    case "memory_selection_output_incomplete":
      return "AI 정리 응답을 정상적으로 완료하지 못했어요. 경험은 보관되어 있으니 다시 시도해 주세요.";
    case "memory_selection_max_tokens":
      return "AI 응답이 최대 출력 길이에 도달해 저장하지 않았어요. 경험은 보관되어 있습니다. 모델·추론 설정을 확인한 뒤 다시 시도해 주세요.";
    case "memory_selection_credential_changed":
      return "정리하는 동안 API key 설정이 바뀌었어요. 현재 설정을 확인한 뒤 다시 시도해 주세요.";
    case "memory_selection_provider_failed":
      return "AI 서비스의 응답을 받지 못했어요. 경험은 보관되어 있으니 잠시 후 다시 시도해 주세요.";
    case "memory_selection_output_invalid":
    case "memory_selection_decisions_incomplete":
      return "AI 정리 결과를 검증하지 못해 기억으로 저장하지 않았어요. 경험은 보관되어 있으니 다시 시도해 주세요.";
    case "memory_selection_scope_changed":
    case "memory_selection_source_changed":
      return "정리하는 동안 설정이나 원본이 바뀌었어요. 현재 상태를 확인한 뒤 다시 시도해 주세요.";
    case "memory_selection_scope_unavailable":
      return "이 캐릭터의 World 참여 상태를 확인해 주세요.";
    default:
      return "기억 정리를 마치지 못했어요. 설정을 확인한 뒤 다시 시도해 주세요.";
  }
}
