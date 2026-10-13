"use client";
import { AgentCreateClient, type CreationActivitySettingsProps } from "@/features/characters/components/agent-create-client";
import { WorldCharacterBasicSettings } from "./world-character-basic-settings";
export function AgentCreationScreen() {
    return <AgentCreateClient ActivitySettings={CreationActivitySettings}/>;
}

function CreationActivitySettings({ worldId, actorId, onBusyChange, onActivationChange }: CreationActivitySettingsProps) {
    return <WorldCharacterBasicSettings worldId={worldId} actorId={actorId} onBusyChange={onBusyChange} showActivation={false} onActivationChange={onActivationChange}/>;
}
