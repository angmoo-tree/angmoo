"use client";

import { useEffect, useEffectEvent, useState } from "react";
import type { CredentialMetadataState } from "@/components/ui/credential-fields";
import { WorldCredentialCard } from "@/features/characters/components/world-credential-card";
import { WorldVisionControls } from "@/features/media/components/world-image-policy-controls";

/** Screen-local coordination; the credential owner supplies saved-key availability. */
export function WorldCharacterVisionSettings({ worldId, actorId, refreshRevision, externalBusy, onChanged, onBusyChange }: {
  worldId: string; actorId: string; refreshRevision: number; externalBusy: boolean;
  onChanged: () => void; onBusyChange: (busy: boolean) => void;
}) {
  const [metadata, setMetadata] = useState<CredentialMetadataState>({ status: "loading" });
  const [keyRevision, setKeyRevision] = useState(0);
  const [keyBusy, setKeyBusy] = useState(false), [policyBusy, setPolicyBusy] = useState(false);
  const notifyBusy = useEffectEvent(onBusyChange);
  useEffect(() => { notifyBusy(keyBusy || policyBusy); return () => notifyBusy(false); }, [keyBusy, policyBusy]);
  const keyStatus = metadata.status === "ready" ? metadata.metadata.has_key ? "saved" : "missing" : metadata.status;
  return <WorldCredentialCard worldId={worldId} actorId={actorId} purpose="vision"
    refreshRevision={keyRevision} externalBusy={externalBusy || policyBusy}
    onMetadataState={setMetadata} onBusyChange={setKeyBusy} onSaved={onChanged}>
    <WorldVisionControls worldId={worldId} actorId={actorId} keyStatus={keyStatus}
      onReloadKey={() => setKeyRevision(value => value + 1)} refreshRevision={refreshRevision}
      externalBusy={externalBusy || keyBusy} onChanged={onChanged} onBusyChange={setPolicyBusy} />
  </WorldCredentialCard>;
}
