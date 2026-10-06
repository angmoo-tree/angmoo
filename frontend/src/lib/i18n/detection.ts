export function detectPreferredLanguage(): string | null {
  let preferred_language: string | null = null;
  try { preferred_language = navigator.languages?.[0] || navigator.language || null; } catch { /* Keep last valid backend value. */ }
  return preferred_language;
}

export function detectUserEnvironment(): { preferred_language: string | null; timezone: string | null } {
  const preferred_language = detectPreferredLanguage();
  let timezone: string | null = null;
  try { timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || null; } catch { /* Detection failure is not UTC detection. */ }
  return { preferred_language, timezone };
}
