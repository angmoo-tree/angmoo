"use client";
import { useCallback } from "react";
import { useUiText } from "@/hooks/use-ui-text";
import { useUiDateFormatter } from "@/hooks/use-ui-date-formatter";
import { formatUiRequestFailure } from "@/lib/http/error-presentation";

export function useUiErrorText(namespace: string) {
  const text = useUiText(namespace), date = useUiDateFormatter();
  return useCallback((error: unknown, fallback: string) => formatUiRequestFailure(error, fallback, text, date), [text, date]);
}
