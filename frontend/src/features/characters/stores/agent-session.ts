import type { AgentAutonomyMutationState, AgentAutonomyMutationEventDetail } from "@/features/characters/types/agents";

const FIRST_AGENT_WELCOME_PROMPT_KEY = "angmoo.firstAgentWelcomePromptPending";

export const AGENTS_CHANGED_EVENT = "angmoo:agents-changed";

export const AGENT_AUTONOMY_MUTATION_EVENT = "angmoo:agent-autonomy-mutation";

const AGENT_AUTONOMY_MUTATION_KEY = "angmoo.agentAutonomyMutation";

export function markFirstAgentWelcomePromptPending() {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(FIRST_AGENT_WELCOME_PROMPT_KEY, "1");
}

export function hasFirstAgentWelcomePromptPending() {
  if (typeof window === "undefined") return false;
  return window.sessionStorage.getItem(FIRST_AGENT_WELCOME_PROMPT_KEY) === "1";
}

export function clearFirstAgentWelcomePromptPending() {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(FIRST_AGENT_WELCOME_PROMPT_KEY);
}

export function notifyAgentsChanged() {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(AGENTS_CHANGED_EVENT));
}

function readAgentAutonomyMutations(): Record<string, AgentAutonomyMutationState> {
  if (typeof window === "undefined") return {};
  const raw = window.sessionStorage.getItem(AGENT_AUTONOMY_MUTATION_KEY);
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return {};
    return Object.fromEntries(
      Object.entries(parsed).filter(
        (entry): entry is [string, AgentAutonomyMutationState] =>
          entry[1] === "activating" || entry[1] === "deactivating",
      ),
    );
  } catch {
    return {};
  }
}

function writeAgentAutonomyMutations(
  mutations: Record<string, AgentAutonomyMutationState>,
) {
  if (typeof window === "undefined") return;
  if (Object.keys(mutations).length === 0) {
    window.sessionStorage.removeItem(AGENT_AUTONOMY_MUTATION_KEY);
    return;
  }
  window.sessionStorage.setItem(
    AGENT_AUTONOMY_MUTATION_KEY,
    JSON.stringify(mutations),
  );
}

function notifyAgentAutonomyMutation(
  characterId: string,
  state: AgentAutonomyMutationState | null,
) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent<AgentAutonomyMutationEventDetail>(
      AGENT_AUTONOMY_MUTATION_EVENT,
      {
        detail: { characterId, state },
      },
    ),
  );
}

export function getAgentAutonomyMutationStates() {
  return readAgentAutonomyMutations();
}

export function getAgentAutonomyMutationState(characterId: string) {
  return readAgentAutonomyMutations()[characterId] ?? null;
}

export function setAgentAutonomyMutationState(
  characterId: string,
  state: AgentAutonomyMutationState,
) {
  const mutations = readAgentAutonomyMutations();
  mutations[characterId] = state;
  writeAgentAutonomyMutations(mutations);
  notifyAgentAutonomyMutation(characterId, state);
}

export function clearAgentAutonomyMutationState(characterId: string) {
  const mutations = readAgentAutonomyMutations();
  delete mutations[characterId];
  writeAgentAutonomyMutations(mutations);
  notifyAgentAutonomyMutation(characterId, null);
}
