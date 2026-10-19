"use client";
import { useRef, useState } from "react";
import type { ActivityActivation } from "@/features/characters/types/activity-activation";
import { BasicActivitySettingsCard } from "@/features/characters/components/basic-activity-settings-card";
import { WorldCredentialCard } from "@/features/characters/components/world-credential-card";
import { WorldImageGenerationCard } from "@/features/media/components/world-image-policy-controls";
export function WorldCharacterBasicSettings({ worldId, actorId, onBusyChange, showActivation = true, onActivationChange }: {
    worldId: string;
    actorId: string;
    onBusyChange?: (busy: boolean) => void;
    showActivation?: boolean;
    onActivationChange?: (value: ActivityActivation | null) => void;
}) {
    const [revision, setRevision] = useState(0);
    const [credentialRevision, setCredentialRevision] = useState(0);
    const [activityBusy, setActivityBusy] = useState(false);
    const busy = useRef({ activity: false, sns: false, image: false });
    function notifyBusy(kind: keyof typeof busy.current, value: boolean) {
      busy.current[kind] = value; onBusyChange?.(Object.values(busy.current).some(Boolean));
    }
    return <div className="grid min-w-0 gap-6">
    <BasicActivitySettingsCard key={`${worldId}:${actorId}`} worldId={worldId} actorId={actorId} revision={revision} onMutation={() => setCredentialRevision(value => value + 1)} showActivation={showActivation} onActivationChange={onActivationChange} onEditorState={value => { setActivityBusy(value.busy); notifyBusy("activity", value.busy); }}/>
    <WorldCredentialCard worldId={worldId} actorId={actorId} purpose="sns" refreshRevision={credentialRevision} externalBusy={activityBusy} onSaved={() => setRevision(value => value + 1)} onBusyChange={value => notifyBusy("sns", value)}/>
    <WorldImageGenerationCard worldId={worldId} actorId={actorId} onBusyChange={value => notifyBusy("image", value)}/>
  </div>;
}
