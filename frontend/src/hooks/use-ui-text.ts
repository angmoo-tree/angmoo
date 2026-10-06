"use client";

import { useCallback } from "react";
import { useTranslation } from "react-i18next";

export type UiText = (message: string, values?: Record<string, string | number>) => string;

/** Only product-authored messages are passed here; never user/card/source text. */
export function useUiText(namespace: string): UiText {
  // Subscribe to language changes for rendering, but keep the callback stable
  // so data-loading effects do not run again solely because the UI language
  // changed. Translation always reads this app's current i18next instance.
  const { i18n } = useTranslation(namespace);
  return useCallback((message, values = {}) => String(i18n.t(message, {
    ...values, defaultValue: message, ns: [namespace, "shell"],
    // These are literal examples in the card guide, rather than interpolation.
    user: "{{user}}", char: "{{char}}",
  })), [i18n, namespace]);
}
