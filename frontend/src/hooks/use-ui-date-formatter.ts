"use client";
import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useUserEnvironment } from "@/hooks/use-user-environment";
import { formatDate } from "@/utils/profile-presentation";

/** Display UTC instants in the active environment; package zones are metadata. */
export function useUiDateFormatter() {
  const { environment } = useUserEnvironment();
  const { i18n } = useTranslation();
  const timezone = environment?.timezone ?? "UTC";
  const locale = i18n.resolvedLanguage ?? "en";
  return useCallback((value: string, packageTimezone?: string) => {
    // Older presentation callers still pass immutable package metadata.
    // Display uses the active installation environment instead.
    void packageTimezone;
    return formatDate(value, timezone, locale);
  }, [timezone, locale]);
}
