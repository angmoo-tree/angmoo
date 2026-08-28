export function formatHandle(handle?: string | null) {
  return handle ? `@${handle}` : "";
}

export function getProfileInitial(name: string) {
  return name.trim().charAt(0).toUpperCase() || "A";
}

export const OFFICIAL_OPERATOR_DISPLAY_NAME = "운영자";

export function isOfficialOperatorName(name?: string | null) {
  return name?.trim() === OFFICIAL_OPERATOR_DISPLAY_NAME;
}

const PROFILE_COLORS = [
  "bg-[#173B8F] text-white",
  "bg-[#0EA5E9] text-white",
  "bg-[#1E7A6D] text-white",
  "bg-[#7C3AED] text-white",
  "bg-[#F59E0B] text-[#101828]",
  "bg-[#101828] text-white",
];

export function getProfileColor(name: string) {
  if (isOfficialOperatorName(name)) {
    return "bg-[#ff6b6b] text-white";
  }

  const seed = Array.from(name).reduce(
    (sum, character) => sum + character.charCodeAt(0),
    0,
  );
  return PROFILE_COLORS[seed % PROFILE_COLORS.length];
}
