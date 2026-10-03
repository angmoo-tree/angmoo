"use client";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

export function useUiNumberFormatter() {
  const { i18n } = useTranslation();
  return useMemo(() => new Intl.NumberFormat(i18n.resolvedLanguage ?? "en").format,
    [i18n.resolvedLanguage]);
}
