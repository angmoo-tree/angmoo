import { createInstance, type Resource } from "i18next";
import type { UiLanguage } from "@/types/user-environment";

export function resolveUiLanguage(saved: UiLanguage | null | undefined, preferred?: string): UiLanguage {
  if (saved === "ko" || saved === "en") return saved;
  return preferred?.toLowerCase().split("-")[0] === "ko" ? "ko" : "en";
}

export function createUiI18n(resources: Resource, language: UiLanguage = "en") {
  const instance = createInstance();
  void instance.init({ resources, lng: language, supportedLngs: ["ko", "en"], fallbackLng: "en",
    defaultNS: "common", initAsync: false, saveMissing: false, keySeparator: false, nsSeparator: false,
    interpolation: { escapeValue: false }, react: { useSuspense: false } });
  return instance;
}
