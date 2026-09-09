/** UI selection keys are decoded before sending model IDs to the API. */
export const GENERATION_PROFILES = [
  { value: "gemini-3.5-flash-lite:high", model: "gemini-3.5-flash-lite", thinking: "high", label: "Gemini 3.5 Flash-Lite (high)" },
  { value: "gemini-3.5-flash-lite:medium", model: "gemini-3.5-flash-lite", thinking: "medium", label: "Gemini 3.5 Flash-Lite (medium)" },
  { value: "gemini-3.1-flash-lite:high", model: "gemini-3.1-flash-lite", thinking: "high", label: "Gemini 3.1 Flash-Lite (high)" },
  { value: "gemini-3.1-flash-lite:medium", model: "gemini-3.1-flash-lite", thinking: "medium", label: "Gemini 3.1 Flash-Lite (medium)" },
] as const;

export type GenerationProfileValue = (typeof GENERATION_PROFILES)[number]["value"];
export const DEFAULT_GENERATION_PROFILE = "gemini-3.1-flash-lite:high";
export const THINKING_HELP = "high와 medium은 AI가 생각하는 깊이 설정입니다. 실제 처리 시간과 토큰 사용량은 내용에 따라 달라집니다.";

export function generationProfileValue(model: string | null | undefined, thinking = "high"): GenerationProfileValue | "" {
  return GENERATION_PROFILES.find((p) => p.value === model || (p.model === model && p.thinking === thinking))?.value ?? "";
}

export function generationProfileLabel(model: string | null | undefined, thinking = "high"): string {
  const value = generationProfileValue(model, thinking);
  return GENERATION_PROFILES.find((p) => p.value === value)?.label ?? "지원 모델을 다시 선택해 주세요";
}

export function decodeGenerationProfile(value: string) {
  const profile = GENERATION_PROFILES.find((p) => p.value === value);
  if (!profile) throw new Error("지원 모델과 추론 수준을 다시 선택해 주세요.");
  return { model: profile.model, thinking_level: profile.thinking };
}

export function generationProfilePayload<T extends object>(data: T, field: "model" | "default_model" | "selected_model"): object {
  if (!(field in data)) return { ...data };
  const value = (data as Record<string, unknown>)[field];
  if (value === undefined || value === null) return { ...data };
  const pair = decodeGenerationProfile(String(value));
  const thinkingField = field === "model" ? "thinking_level" : field.replace("model", "thinking_level");
  return { ...data, [field]: pair.model, [thinkingField]: pair.thinking_level };
}
