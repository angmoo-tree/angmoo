import type { AgentDetailRead, AgentTypeCounts } from "@/features/characters/types/agents";

export function getAgentTypeCounts(agents: AgentDetailRead[]): AgentTypeCounts {
  return agents.reduce<AgentTypeCounts>(
    (counts, agent) => {
      if (agent.character.execution_mode === "local") {
        counts.local += 1;
      } else {
        counts.llm += 1;
      }
      return counts;
    },
    { llm: 0, local: 0 },
  );
}
