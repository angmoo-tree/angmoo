export const PERSONA_LIMITS = {
  one_liner: 500,
  personality: 6000,
  speech_style: 4000,
  worldview: 8000,
  character_background: 8000,
  topic_preferences: 3000,
  safety_rules: 4000,
} as const;

export function normalizePersonaText(value: string): string {
  return value.replace(/\r\n?/g, "\n").normalize("NFC");
}

export function personaTextLength(value: string): number {
  return Array.from(normalizePersonaText(value)).length;
}

export function personaLengthError(value: string, limit: number): { code: "persona_length_exceeded"; limit: number; excess: number } | undefined {
  const excess = personaTextLength(value) - limit;
  return excess > 0 ? { code: "persona_length_exceeded", limit, excess } : undefined;
}
