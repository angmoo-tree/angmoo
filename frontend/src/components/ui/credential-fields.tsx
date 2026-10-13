"use client";
import { useEffect, useEffectEvent, useRef, useState, type ReactNode } from "react";
import { Button } from "./button";
import { Field, Input, Select } from "./form-controls";
import { InlineError } from "./feedback";
import { useProductLeaveGuard } from "@/hooks/use-product-leave-guard";
import { useAuthRuntimeIdentity } from "@/hooks/use-auth-runtime-identity";
import { captureAuthRequestScope, isCurrentAuthRequestScope } from "@/lib/auth/browser-session";

export type SecretMetadata = { provider: string; model: string; thinking_level: string | null; has_key: boolean; has_partner_key?: boolean; fingerprint: string | null; revision: number; configuration_revision?: number | null; key_revision?: number | null };
export type SecretKeyMetadata = { provider: string; has_key: boolean; fingerprint: string | null; key_revision: number };
export type SecretProfile = { label: string; provider: string; model: string; thinking_level: string | null };
export type SecretWrite = SecretProfile & { api_key?: string; expected_revision: number; expected_configuration_revision?: number; expected_key_revision?: number };
type Props = {
  initialMetadata?: SecretMetadata;
  showSecretFields?: (profile: SecretProfile | SecretMetadata) => boolean;
  readSelectedKey?: (provider: string, signal: AbortSignal) => Promise<SecretKeyMetadata>;
  onSelectedKey?: (value: SecretKeyMetadata | null) => void;
  children?: ReactNode;
  onProfileChange?: (value: SecretProfile) => void;
  onSaved?: (value: SecretMetadata) => void;
  onMetadata?: (value: SecretMetadata) => void;
  onDirtyChange?: (value: boolean) => void;
  onBusyChange?: (value: boolean) => void;
  scopeKey: string; profiles: readonly SecretProfile[]; read: (signal: AbortSignal) => Promise<SecretMetadata>;
  save: (data: SecretWrite, signal: AbortSignal) => Promise<SecretMetadata>;
  remove: (revision: number, signal: AbortSignal) => Promise<SecretMetadata>;
  text: { model: string; key: string; stored: string; missing: string; save: string; remove: string; confirm: string; failed: string; saved: string; keep: string; unsupported: string; loading?: string; reload?: string };
};
const profileKey = (p: SecretProfile | SecretMetadata) => `${p.provider}:${p.model}:${p.thinking_level ?? ""}`;

/** Write-only input. The caller supplies the authorized owner transport. */
export function CredentialFields(props: Props) {
  const identity = useAuthRuntimeIdentity(props.scopeKey);
  return <ScopedCredentialFields key={identity} {...props} />;
}

function ScopedCredentialFields({ scopeKey, profiles, read, save, remove, text, onMetadata, onProfileChange, onSaved, onDirtyChange, onBusyChange, children, initialMetadata, showSecretFields, readSelectedKey, onSelectedKey }: Props) {
  const [metadata, setMetadata] = useState<SecretMetadata | null>(initialMetadata ?? null);
  const [selected, setSelected] = useState(initialMetadata ? profileKey(initialMetadata) : "");
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const [notice, setNotice] = useState(false);
  const [selectedKey, setSelectedKey] = useState<SecretKeyMetadata | null>(null);
  const [keyError, setKeyError] = useState(false);
  const [keyRefresh, setKeyRefresh] = useState(0);
  const initial = useRef(initialMetadata);
  const request = useRef<AbortController | null>(null);
  const readCurrent = useEffectEvent((signal: AbortSignal) => read(signal));
  const notifyRead = useEffectEvent((value: SecretMetadata) => onMetadata?.(value));
  const readKey = useEffectEvent((provider: string, signal: AbortSignal) => readSelectedKey!(provider, signal));
  const notifyKey = useEffectEvent((value: SecretKeyMetadata | null) => onSelectedKey?.(value));
  const selectedProfile = profiles.find(profile => profileKey(profile) === selected) ?? metadata;
  const provider = selectedProfile?.provider;
  const hasSelectedRead = Boolean(readSelectedKey);
  const secretVisible = Boolean(selectedProfile && (showSecretFields?.(selectedProfile) ?? true));
  const keyView = readSelectedKey ? selectedKey?.provider === provider ? selectedKey : null : metadata;
  useEffect(() => {
    if (!hasSelectedRead || !provider) return;
    const controller = new AbortController();
    const authScope = captureAuthRequestScope();
    queueMicrotask(() => { if (!controller.signal.aborted) { setSelectedKey(null); setKeyError(false); notifyKey(null); } });
    void readKey(provider, controller.signal).then(value => {
      if (controller.signal.aborted || !isCurrentAuthRequestScope(authScope) || value.provider !== provider) return;
      setSelectedKey(value); notifyKey(value);
    }).catch(() => { if (!controller.signal.aborted && isCurrentAuthRequestScope(authScope)) setKeyError(true); });
    return () => controller.abort();
  }, [provider, hasSelectedRead, scopeKey, keyRefresh]);
  const dirty = Boolean(key) || (metadata !== null && selected !== profileKey(metadata)) || busy;
  useEffect(() => {
    if (!initialMetadata || dirty || !metadata || initialMetadata.revision < metadata.revision ||
        JSON.stringify(initialMetadata) === JSON.stringify(metadata)) return;
    let live = true;
    queueMicrotask(() => { if (live) { setMetadata(initialMetadata); setSelected(profileKey(initialMetadata)); } });
    return () => { live = false; };
  }, [initialMetadata, dirty, metadata]);
  const notifyDirty = useEffectEvent((value: boolean) => onDirtyChange?.(value));
  useEffect(() => { notifyDirty(dirty); }, [dirty]);
  const notifyBusy = useEffectEvent((value: boolean) => onBusyChange?.(value));
  useEffect(() => { notifyBusy(busy); }, [busy]);
  useProductLeaveGuard(Boolean(key) || (metadata !== null && selected !== profileKey(metadata)) || busy);
  useEffect(() => {
    if (initial.current) { notifyRead(initial.current); return () => request.current?.abort(); }
    const controller = new AbortController(); request.current = controller;
    const authScope = captureAuthRequestScope();
    readCurrent(controller.signal).then(value => { if (!controller.signal.aborted && isCurrentAuthRequestScope(authScope)) { setMetadata(value); setSelected(profileKey(value)); notifyRead(value); } })
      .catch(() => { if (!controller.signal.aborted && isCurrentAuthRequestScope(authScope)) setFailed(true); });
    return () => { controller.abort(); request.current?.abort(); };
  }, [scopeKey]);
  async function submit(deleting = false) {
    if (!metadata || busy || (readSelectedKey && !keyView) || (deleting && !window.confirm(text.confirm))) return;
    const controller = new AbortController(); request.current = controller; setBusy(true); setFailed(false); setNotice(false);
    const authScope = captureAuthRequestScope();
    try {
      const profile = profiles.find(p => profileKey(p) === selected) ?? metadata;
      const value = deleting ? await remove(metadata.revision, controller.signal) : await save({ ...profile,
        label: "label" in profile ? profile.label : "", expected_revision: metadata.revision,
        expected_configuration_revision: metadata.configuration_revision ?? undefined,
        expected_key_revision: selectedKey?.key_revision,
        ...(secretVisible && key.trim() ? { api_key: key } : {}) }, controller.signal);
      if (!controller.signal.aborted && isCurrentAuthRequestScope(authScope)) { setMetadata(value); setSelected(profileKey(value)); setKey(""); setNotice(true); setKeyRefresh(value => value + 1); onMetadata?.(value); onSaved?.(value); }
    } catch { if (!controller.signal.aborted && isCurrentAuthRequestScope(authScope)) setFailed(true); }
    finally { if (!controller.signal.aborted && isCurrentAuthRequestScope(authScope)) setBusy(false); }
  }
  return <div>
    {metadata ? <>
      {secretVisible ? <p role="status">{keyView ? keyView.has_key ? text.stored : text.missing : keyError ? text.failed : text.loading ?? text.model}{keyView?.fingerprint ? ` · ${keyView.fingerprint}` : ""}</p> : null}
      <Field label={text.model}>{props => profiles.length === 1 ? <p {...props} className="min-h-11 py-3">{profiles[0].label}</p> : <Select {...props} value={selected} disabled={busy} onChange={event => { const profile = profiles.find(p => profileKey(p) === event.target.value); if (profile?.provider !== provider) setKey(""); setSelected(event.target.value); if (profile) onProfileChange?.(profile); }}>
        {!profiles.some(p => profileKey(p) === selected) ? <option value={selected}>{text.unsupported}: {metadata.model}</option> : null}
        {profiles.map(p => <option key={profileKey(p)} value={profileKey(p)}>{p.label}</option>)}
      </Select>}</Field>
      {secretVisible ? <Field label={text.key} helperText={text.keep}>{props => <Input {...props} type="password" autoComplete="new-password" maxLength={4096}
        value={key} disabled={busy} onChange={event => setKey(event.target.value)} />}</Field> : null}
      {children}
      {keyError ? <InlineError>{text.failed}<Button variant="secondary" onClick={() => setKeyRefresh(value => value + 1)}>{text.reload ?? text.model}</Button></InlineError> : null}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-control)", marginTop: "var(--spacing-phone)" }}>
        <Button type="button" loading={busy} disabled={Boolean(readSelectedKey && !keyView)} onClick={() => void submit()}>{text.save}</Button>
        {secretVisible ? <Button type="button" variant="secondary" disabled={busy || !keyView?.has_key} onClick={() => void submit(true)}>{text.remove}</Button> : null}
      </div>
    </> : null}
    {failed ? <InlineError>{text.failed}<Button variant="secondary" onClick={() => {
      const controller = new AbortController(); request.current?.abort(); request.current = controller;
      const authScope = captureAuthRequestScope();
      setKeyRefresh(value => value + 1);
      void read(controller.signal).then(value => { if (!controller.signal.aborted && isCurrentAuthRequestScope(authScope)) { setMetadata(value); setFailed(false); onMetadata?.(value); } }).catch(() => { if (!controller.signal.aborted && isCurrentAuthRequestScope(authScope)) setFailed(true); });
    }}>{text.reload ?? text.model}</Button></InlineError> : null}
    {notice ? <p role="status">{text.saved}</p> : null}
  </div>;
}
