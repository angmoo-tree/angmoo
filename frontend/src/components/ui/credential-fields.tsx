"use client";
import { useEffect, useEffectEvent, useRef, useState, type ReactNode } from "react";
import { Button } from "./button";
import { Field, Input, Select } from "./form-controls";
import { InlineError } from "./feedback";
import { useProductLeaveGuard } from "@/hooks/use-product-leave-guard";

export type SecretMetadata = { provider: string; model: string; thinking_level: string | null; has_key: boolean; has_partner_key?: boolean; fingerprint: string | null; revision: number; configuration_revision?: number | null };
export type SecretProfile = { label: string; provider: string; model: string; thinking_level: string | null };
export type SecretWrite = SecretProfile & { api_key?: string; expected_revision: number; expected_configuration_revision?: number };
type Props = {
  children?: ReactNode;
  onProfileChange?: (value: SecretProfile) => void;
  onSaved?: (value: SecretMetadata) => void;
  onMetadata?: (value: SecretMetadata) => void;
  onDirtyChange?: (value: boolean) => void;
  scopeKey: string; profiles: readonly SecretProfile[]; read: (signal: AbortSignal) => Promise<SecretMetadata>;
  save: (data: SecretWrite, signal: AbortSignal) => Promise<SecretMetadata>;
  remove: (revision: number, signal: AbortSignal) => Promise<SecretMetadata>;
  text: { model: string; key: string; stored: string; missing: string; save: string; remove: string; confirm: string; failed: string; saved: string; keep: string; unsupported: string; reload?: string };
};
const profileKey = (p: SecretProfile | SecretMetadata) => `${p.provider}:${p.model}:${p.thinking_level ?? ""}`;

/** Write-only input. The caller supplies the authorized owner transport. */
export function CredentialFields(props: Props) {
  return <ScopedCredentialFields key={props.scopeKey} {...props} />;
}

function ScopedCredentialFields({ scopeKey, profiles, read, save, remove, text, onMetadata, onProfileChange, onSaved, onDirtyChange, children }: Props) {
  const [metadata, setMetadata] = useState<SecretMetadata | null>(null);
  const [selected, setSelected] = useState("");
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const [notice, setNotice] = useState(false);
  const request = useRef<AbortController | null>(null);
  const readCurrent = useEffectEvent((signal: AbortSignal) => read(signal));
  const notifyRead = useEffectEvent((value: SecretMetadata) => onMetadata?.(value));
  const dirty = Boolean(key) || (metadata !== null && selected !== profileKey(metadata)) || busy;
  const notifyDirty = useEffectEvent((value: boolean) => onDirtyChange?.(value));
  useEffect(() => { notifyDirty(dirty); }, [dirty]);
  useProductLeaveGuard(Boolean(key) || (metadata !== null && selected !== profileKey(metadata)) || busy);
  useEffect(() => {
    const controller = new AbortController(); request.current = controller;
    readCurrent(controller.signal).then(value => { if (!controller.signal.aborted) { setMetadata(value); setSelected(profileKey(value)); notifyRead(value); } })
      .catch(() => { if (!controller.signal.aborted) setFailed(true); });
    return () => { controller.abort(); request.current?.abort(); };
  }, [scopeKey]);
  async function submit(deleting = false) {
    if (!metadata || busy || (deleting && !window.confirm(text.confirm))) return;
    const controller = new AbortController(); request.current = controller; setBusy(true); setFailed(false); setNotice(false);
    try {
      const profile = profiles.find(p => profileKey(p) === selected) ?? metadata;
      const value = deleting ? await remove(metadata.revision, controller.signal) : await save({ ...profile,
        label: "label" in profile ? profile.label : "", expected_revision: metadata.revision,
        expected_configuration_revision: metadata.configuration_revision ?? undefined,
        ...(key.trim() ? { api_key: key } : {}) }, controller.signal);
      if (!controller.signal.aborted) { setMetadata(value); setSelected(profileKey(value)); setKey(""); setNotice(true); onMetadata?.(value); onSaved?.(value); }
    } catch { if (!controller.signal.aborted) setFailed(true); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  return <div>
    {metadata ? <>
      <p role="status">{metadata.has_key ? text.stored : text.missing}{metadata.fingerprint ? ` · ${metadata.fingerprint}` : ""}</p>
      <Field label={text.model}>{props => profiles.length === 1 ? <p {...props} className="min-h-11 py-3">{profiles[0].label}</p> : <Select {...props} value={selected} disabled={busy} onChange={event => { setSelected(event.target.value); const profile = profiles.find(p => profileKey(p) === event.target.value); if (profile) onProfileChange?.(profile); }}>
        {!profiles.some(p => profileKey(p) === selected) ? <option value={selected}>{text.unsupported}: {metadata.model}</option> : null}
        {profiles.map(p => <option key={profileKey(p)} value={profileKey(p)}>{p.label}</option>)}
      </Select>}</Field>
      <Field label={text.key} helperText={text.keep}>{props => <Input {...props} type="password" autoComplete="new-password" maxLength={4096}
        value={key} disabled={busy} onChange={event => setKey(event.target.value)} />}</Field>
      {children}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-control)", marginTop: "var(--spacing-phone)" }}>
        <Button type="button" loading={busy} onClick={() => void submit()}>{text.save}</Button>
        <Button type="button" variant="secondary" disabled={busy || !metadata.has_key} onClick={() => void submit(true)}>{text.remove}</Button>
      </div>
    </> : null}
    {failed ? <InlineError>{text.failed}<Button variant="secondary" onClick={() => {
      const controller = new AbortController(); request.current?.abort(); request.current = controller;
      void read(controller.signal).then(value => { if (!controller.signal.aborted) { setMetadata(value); setFailed(false); onMetadata?.(value); } }).catch(() => { if (!controller.signal.aborted) setFailed(true); });
    }}>{text.reload ?? text.model}</Button></InlineError> : null}
    {notice ? <p role="status">{text.saved}</p> : null}
  </div>;
}
