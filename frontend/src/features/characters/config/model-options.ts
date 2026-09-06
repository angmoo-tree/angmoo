
export const GOOGLE_GEMINI_MODELS = [
  { value: "gemma-4-26b-a4b-it", label: "Gemma 4 26B" },
  { value: "gemini-3.1-flash-lite", label: "Gemini 3.1 Flash-Lite" },
  { value: "gemma-4-31b-it", label: "Gemma 4 31B" },
] as const;

export const DEFAULT_GOOGLE_GEMINI_MODEL = "gemini-3.1-flash-lite";

export const USER_IMAGE_MODELS = [
  {
    value: "replicate-zimage-turbo-lora",
    label: "Replicate · Z-Image Turbo LoRA",
    note: "새 장면 생성 · H100 시간 과금 · 약 $0.001/장",
    priceNote: "테스트 기준 약 $0.0009~$0.0012 수준이며 실행시간에 따라 달라집니다.",
    officialUrl: "https://replicate.com/prunaai/z-image-turbo-lora",
  },
  {
    value: "replicate-p-image-edit",
    label: "Replicate · P-Image-Edit",
    note: "참조 이미지 편집 · Replicate 표기 $0.01/장",
    priceNote: "Angmoo 자체 가격이 아닌 Replicate 모델 페이지 표기 기준입니다.",
    officialUrl: "https://replicate.com/prunaai/p-image-edit",
  },
] as const;

export const DEFAULT_USER_IMAGE_MODEL = "replicate-zimage-turbo-lora";

export const REPLICATE_API_TOKEN_GUIDE_URL =
  "https://replicate.com/docs/topics/security/api-tokens";

export const REPLICATE_API_TOKEN_URL =
  "https://replicate.com/account/api-tokens";

export const REPLICATE_PRICING_URL = "https://replicate.com/pricing";

export type GoogleGeminiModel = (typeof GOOGLE_GEMINI_MODELS)[number]["value"];

export type PollinationsImageModel = (typeof USER_IMAGE_MODELS)[number]["value"];

export function getGoogleGeminiModelNote(model: GoogleGeminiModel) {
  if (model === "gemma-4-31b-it" || model === "gemma-4-26b-a4b-it") {
    return "Gemma 4는 추론형 모델이라 응답이 더 느리거나 불안정할 수 있습니다.";
  }
  return null;
}
