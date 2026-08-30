export const CHARACTERS_CHANGED_EVENT = "angmoo:agents-changed";
export const CHARACTER_AUTONOMY_MUTATION_EVENT =
  "angmoo:agent-autonomy-mutation";

const AUTONOMY_MUTATION_KEY = "angmoo.agentAutonomyMutation";
const FIRST_CHARACTER_WELCOME_KEY = "angmoo.firstAgentWelcomePromptPending";

import type { CharacterAutonomyMutationState } from "./character-dashboard-contract";

export type CharacterAutonomyMutationEventDetail = {
  characterId: string;
  state: CharacterAutonomyMutationState | null;
};

export function getCharacterAutonomyMutationStates() {
  if (typeof window === "undefined") return {};
  const raw = window.sessionStorage.getItem(AUTONOMY_MUTATION_KEY);
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return {};
    return Object.fromEntries(
      Object.entries(parsed).filter(
        (entry): entry is [string, CharacterAutonomyMutationState] =>
          entry[1] === "activating" || entry[1] === "deactivating",
      ),
    );
  } catch {
    return {};
  }
}

export function setCharacterAutonomyMutationState(
  characterId: string,
  state: CharacterAutonomyMutationState,
) {
  const mutations = getCharacterAutonomyMutationStates();
  mutations[characterId] = state;
  writeMutations(mutations);
  notifyMutation(characterId, state);
}

export function clearCharacterAutonomyMutationState(characterId: string) {
  const mutations = getCharacterAutonomyMutationStates();
  delete mutations[characterId];
  writeMutations(mutations);
  notifyMutation(characterId, null);
}

export function hasFirstCharacterWelcomePending() {
  if (typeof window === "undefined") return false;
  return window.sessionStorage.getItem(FIRST_CHARACTER_WELCOME_KEY) === "1";
}

export function clearFirstCharacterWelcomePending() {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(FIRST_CHARACTER_WELCOME_KEY);
}

export function notifyCharactersChanged() {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(CHARACTERS_CHANGED_EVENT));
}

function writeMutations(
  mutations: Record<string, CharacterAutonomyMutationState>,
) {
  if (typeof window === "undefined") return;
  if (Object.keys(mutations).length === 0) {
    window.sessionStorage.removeItem(AUTONOMY_MUTATION_KEY);
    return;
  }
  window.sessionStorage.setItem(AUTONOMY_MUTATION_KEY, JSON.stringify(mutations));
}

function notifyMutation(
  characterId: string,
  state: CharacterAutonomyMutationState | null,
) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent<CharacterAutonomyMutationEventDetail>(
      CHARACTER_AUTONOMY_MUTATION_EVENT,
      { detail: { characterId, state } },
    ),
  );
}
