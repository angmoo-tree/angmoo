"use client";
import { AgentCreateClient } from "@/features/characters/components/agent-create-client";
import { WorldCharacterBasicSettings } from "./world-character-basic-settings";
export function AgentCreationScreen() {
    return <AgentCreateClient renderActivitySettings={({ worldId, actorId, onBusyChange }) => <WorldCharacterBasicSettings worldId={worldId} actorId={actorId} onBusyChange={onBusyChange}/>}/>;
}
