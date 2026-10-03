"use client";

import { useCallback } from "react";
import { useTranslation } from "react-i18next";

export type UiText = (message: string, values?: Record<string, string | number>) => string;

/** Only product-authored messages are passed here; never user/card/source text. */
export function useUiText(namespace: string): UiText {
  const { t } = useTranslation(namespace);
  return useCallback((message, values = {}) => String(t(message, {
    ...values, defaultValue: message, ns: [namespace, "shell"],
    // These are literal examples in the card guide, rather than interpolation.
    user: "{{user}}", char: "{{char}}",
  })), [t, namespace]);
}
