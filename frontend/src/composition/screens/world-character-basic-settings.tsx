"use client";
import { useEffect, useEffectEvent, useState } from "react";
import { BasicActivitySettingsCard } from "@/features/characters/components/basic-activity-settings-card";
import { WorldCredentialCard } from "@/features/characters/components/world-credential-card";
import { WorldImageGenerationCard } from "@/features/media/components/world-image-policy-controls";
export function WorldCharacterBasicSettings({ worldId, actorId, onBusyChange }: {
    worldId: string;
    actorId: string;
    onBusyChange?: (busy: boolean) => void;
}) {
    const [revision, setRevision] = useState(0);
    const [activityBusy, setActivityBusy] = useState(false), [snsBusy, setSnsBusy] = useState(false), [imageBusy, setImageBusy] = useState(false);
    const notifyBusy = useEffectEvent((value: boolean) => onBusyChange?.(value));
    useEffect(() => { notifyBusy(activityBusy || snsBusy || imageBusy); }, [activityBusy, snsBusy, imageBusy]);
    return <div className="grid min-w-0 gap-6">
    <BasicActivitySettingsCard key={`${worldId}:${actorId}`} worldId={worldId} actorId={actorId} revision={revision} onEditorState={value => setActivityBusy(value.busy)}/>
    <WorldCredentialCard worldId={worldId} actorId={actorId} purpose="sns" onSaved={() => setRevision(value => value + 1)} onBusyChange={setSnsBusy}/>
    <WorldImageGenerationCard worldId={worldId} actorId={actorId} onBusyChange={setImageBusy}/>
  </div>;
}
