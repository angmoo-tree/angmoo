"use client";
import { useEffect, useEffectEvent, useRef, useState, type ReactNode } from "react";
import { Button } from "./button";
import { Field, Input, Select } from "./form-controls";
import { InlineError } from "./feedback";
import { useProductLeaveGuard } from "@/hooks/use-product-leave-guard";
import { useAuthRuntimeIdentity } from "@/hooks/use-auth-runtime-identity";
import { captureAuthRequestScope, isCurrentAuthRequestScope } from "@/lib/auth/browser-session";

import { credentialFailure, profileKey, sameCredential, type CredentialFailure, type SecretMetadata, type SecretKeyMetadata, type SecretProfile, type SecretWrite, type SecretDelete, type CredentialMetadataState } from "./credential-state";
export type { SecretMetadata, SecretKeyMetadata, SecretProfile, SecretWrite, SecretDelete, CredentialMetadataState } from "./credential-state";

type Props = {
  initialMetadata?: SecretMetadata;
  refreshRevision?: number;
  externalBusy?: boolean;
  showSecretFields?: (profile: SecretProfile | SecretMetadata) => boolean;
  readSelectedKey?: (provider: string, signal: AbortSignal) => Promise<SecretKeyMetadata>;
  onSelectedKey?: (value: SecretKeyMetadata | null) => void;
  children?: ReactNode;
  onProfileChange?: (value: SecretProfile) => void;
  onSaved?: (value: SecretMetadata) => void;
  onMetadata?: (value: SecretMetadata) => void;
  onMetadataState?: (value: CredentialMetadataState) => void;
  onDirtyChange?: (value: boolean) => void;
  onBusyChange?: (value: boolean) => void;
  scopeKey: string; profiles: readonly SecretProfile[]; read: (signal: AbortSignal) => Promise<SecretMetadata>;
  save: (data: SecretWrite, signal: AbortSignal) => Promise<SecretMetadata>;
  remove: (snapshot: SecretDelete, signal: AbortSignal) => Promise<SecretMetadata>;
  text: { model: string; key: string; stored: string; missing: string; save: string; remove: string; confirm: string; failed: string; saved: string; keep: string; unsupported: string; loading?: string; reload: string; review: string; loadFailed: string; keyLoadFailed: string; saveFailed: string; deleteFailed: string; conflict: string; unknown: string };
};
/** Write-only input. The caller supplies the authorized owner transport. */
export function CredentialFields(props: Props) {
  const identity = useAuthRuntimeIdentity(props.scopeKey);
  return <ScopedCredentialFields key={identity} {...props} />;
}

function ScopedCredentialFields({ scopeKey, profiles, read, save, remove, text, onMetadata, onMetadataState, onProfileChange, onSaved, onDirtyChange, onBusyChange, children, initialMetadata, showSecretFields, readSelectedKey, onSelectedKey, refreshRevision = 0, externalBusy = false }: Props) {
  const [metadata, setMetadata] = useState<SecretMetadata | null>(initialMetadata ?? null);
  const [candidate, setCandidate] = useState<SecretMetadata | null>(null);
  const [selected, setSelected] = useState(initialMetadata ? profileKey(initialMetadata) : "");
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [loadedRevision, setLoadedRevision] = useState<number | null>(null);
  const [failure, setFailure] = useState<CredentialFailure | null>(null);
  const [notice, setNotice] = useState(false);
  const [selectedKey, setSelectedKey] = useState<SecretKeyMetadata | null>(null);
  const [keyError, setKeyError] = useState(false);
  const [keyRefresh, setKeyRefresh] = useState(0);
  const [readNonce, setReadNonce] = useState(0);
  const deferredRead = useRef(false);
  const request = useRef<AbortController | null>(null);
  const readRequest = useRef<AbortController | null>(null);
  const notifyMetadataState = useEffectEvent((value: CredentialMetadataState) => onMetadataState?.(value));
  const readCurrent = useEffectEvent((signal: AbortSignal) => read(signal));
  const readKey = useEffectEvent((provider: string, signal: AbortSignal) => readSelectedKey!(provider, signal));
  const notifyKey = useEffectEvent((value: SecretKeyMetadata | null) => onSelectedKey?.(value));
  const selectedProfile = profiles.find(profile => profileKey(profile) === selected) ?? metadata;
  const provider = selectedProfile?.provider;
  const hasSelectedRead = Boolean(readSelectedKey);
  const secretVisible = Boolean(selectedProfile && (showSecretFields?.(selectedProfile) ?? true));
  const keyView = readSelectedKey ? selectedKey?.provider === provider ? selectedKey : null : metadata;
  const edited = Boolean(key) || (metadata !== null && selected !== profileKey(metadata));
  const blocked = busy || externalBusy || refreshing || loadedRevision !== refreshRevision;
  function acceptMetadata(value: SecretMetadata, acknowledge = false) {
    if (metadata && (value.revision < metadata.revision || (value.configuration_revision ?? 0) < (metadata.configuration_revision ?? 0))) return;
    onMetadataState?.({ status: "ready", metadata: value });
    if (metadata && edited && !sameCredential(metadata, value) && !acknowledge) {
      setCandidate(value); setFailure("conflict"); setNotice(false); return;
    }
    setMetadata(value); setCandidate(null);
    if (!edited) setSelected(profileKey(value));
    // A read never proves that an earlier write with a missing response succeeded.
    setFailure(current => current === "unknown" ? current : null);
    onMetadata?.(value);
  }
  const reconcile = useEffectEvent(acceptMetadata);
  useEffect(() => {
    if (!initialMetadata) return;
    let live = true;
    queueMicrotask(() => { if (live) reconcile(initialMetadata); });
    return () => { live = false; };
  }, [initialMetadata]);
  useEffect(() => {
    if (request.current) { deferredRead.current = true; return; }
    const controller = new AbortController(); readRequest.current?.abort(); readRequest.current = controller;
    const scope = captureAuthRequestScope();
    queueMicrotask(() => {
      if (!controller.signal.aborted && isCurrentAuthRequestScope(scope)) {
        setRefreshing(true); notifyMetadataState({ status: "loading" });
      }
    });
    void readCurrent(controller.signal).then(value => {
      if (controller.signal.aborted || !isCurrentAuthRequestScope(scope)) return;
      reconcile(value); setLoadedRevision(refreshRevision);
    }).catch(() => {
      if (!controller.signal.aborted && isCurrentAuthRequestScope(scope)) { setFailure("loadFailed"); notifyMetadataState({ status: "error" }); }
    }).finally(() => { if (!controller.signal.aborted && isCurrentAuthRequestScope(scope)) setRefreshing(false); });
    return () => controller.abort();
  }, [scopeKey, refreshRevision, readNonce]);
  useEffect(() => () => { request.current?.abort(); readRequest.current?.abort(); }, []);
  useEffect(() => {
    if (!hasSelectedRead || !provider) return;
    const controller = new AbortController();
    const scope = captureAuthRequestScope();
    queueMicrotask(() => { if (!controller.signal.aborted) { setSelectedKey(null); setKeyError(false); notifyKey(null); } });
    void readKey(provider, controller.signal).then(value => {
      if (controller.signal.aborted || !isCurrentAuthRequestScope(scope) || value.provider !== provider) return;
      setSelectedKey(value); notifyKey(value);
    }).catch(() => { if (!controller.signal.aborted && isCurrentAuthRequestScope(scope)) setKeyError(true); });
    return () => controller.abort();
  }, [provider, hasSelectedRead, scopeKey, keyRefresh]);
  const notifyDirty = useEffectEvent((value: boolean) => onDirtyChange?.(value));
  useEffect(() => { notifyDirty(edited || busy); }, [edited, busy]);
  const notifyBusy = useEffectEvent((value: boolean) => onBusyChange?.(value));
  useEffect(() => { notifyBusy(busy); }, [busy]);
  useProductLeaveGuard(edited || busy);

  async function reload() {
    if (busy || refreshing) return;
    const controller = new AbortController(); readRequest.current?.abort(); readRequest.current = controller;
    const scope = captureAuthRequestScope(); setRefreshing(true); onMetadataState?.({ status: "loading" }); setKeyRefresh(value => value + 1);
    try {
      const value = await read(controller.signal);
      if (!controller.signal.aborted && isCurrentAuthRequestScope(scope)) { acceptMetadata(value); setLoadedRevision(refreshRevision); }
    } catch { if (!controller.signal.aborted && isCurrentAuthRequestScope(scope)) { setFailure("loadFailed"); onMetadataState?.({ status: "error" }); } }
    finally { if (!controller.signal.aborted && isCurrentAuthRequestScope(scope)) setRefreshing(false); }
  }
  async function submit(deleting = false) {
    if (!metadata || blocked || candidate || failure === "conflict" || (readSelectedKey && !keyView) || (deleting && !window.confirm(text.confirm))) return;
    readRequest.current?.abort();
    const controller = new AbortController(); request.current = controller; setRefreshing(false); setBusy(true); setFailure(null); setNotice(false);
    const scope = captureAuthRequestScope();
    try {
      const profile = profiles.find(p => profileKey(p) === selected) ?? metadata;
      const snapshot = { provider: profile.provider, expected_revision: metadata.revision, expected_configuration_revision: metadata.configuration_revision ?? undefined, expected_key_revision: selectedKey?.key_revision ?? metadata.key_revision ?? undefined };
      const value = deleting ? await remove(snapshot, controller.signal) : await save({ ...profile,
        label: "label" in profile ? profile.label : "", ...snapshot,
        ...(secretVisible && key.trim() ? { api_key: key } : {}) }, controller.signal);
      if (!controller.signal.aborted && isCurrentAuthRequestScope(scope)) {
        setMetadata(value); setCandidate(null); setSelected(profileKey(value)); setKey(""); setNotice(true);
        setSelectedKey(null); setKeyRefresh(value => value + 1); onMetadata?.(value); onMetadataState?.({ status: "ready", metadata: value }); onSaved?.(value);
      }
    } catch (error) { if (!controller.signal.aborted && isCurrentAuthRequestScope(scope)) { const kind = credentialFailure(error, deleting); setFailure(kind); if (kind === "conflict" || kind === "unknown") deferredRead.current = true; } }
    finally { if (!controller.signal.aborted && isCurrentAuthRequestScope(scope)) { request.current = null; setBusy(false); if (deferredRead.current) { deferredRead.current = false; setReadNonce(value => value + 1); } } }
  }
  return <div>
    {metadata ? <>
      {secretVisible ? <p role="status">{keyView ? keyView.has_key ? text.stored : text.missing : keyError ? text.keyLoadFailed : text.loading ?? text.loadFailed}{keyView?.fingerprint ? ` · ${keyView.fingerprint}` : ""}</p> : null}
      <Field label={text.model}>{props => profiles.length === 1 ? <p {...props} className="min-h-11 py-3">{profiles[0].label}</p> : <Select {...props} value={selected} disabled={busy} onChange={event => { const profile = profiles.find(p => profileKey(p) === event.target.value); if (profile?.provider !== provider) setKey(""); setSelected(event.target.value); setNotice(false); if (profile) onProfileChange?.(profile); }}>
        {!profiles.some(p => profileKey(p) === selected) ? <option value={selected}>{text.unsupported}: {metadata.model}</option> : null}
        {profiles.map(p => <option key={profileKey(p)} value={profileKey(p)}>{p.label}</option>)}
      </Select>}</Field>
      {secretVisible ? <Field label={text.key} helperText={text.keep}>{props => <Input {...props} type="password" autoComplete="new-password" maxLength={4096}
        value={key} disabled={busy} onChange={event => { setKey(event.target.value); setNotice(false); }} />}</Field> : null}
      {children}
      {keyError ? <InlineError>{text.keyLoadFailed}<Button variant="secondary" disabled={busy} onClick={() => setKeyRefresh(value => value + 1)}>{text.reload}</Button></InlineError> : null}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-control)", marginTop: "var(--spacing-phone)" }}>
        <Button type="button" loading={busy} disabled={blocked || Boolean(candidate) || failure === "conflict" || Boolean(readSelectedKey && !keyView)} onClick={() => void submit()}>{text.save}</Button>
        {secretVisible ? <Button type="button" variant="secondary" disabled={blocked || Boolean(candidate) || failure === "conflict" || !keyView?.has_key} onClick={() => void submit(true)}>{text.remove}</Button> : null}
      </div>
    </> : null}
    {failure ? <InlineError>{text[failure]}<Button variant="secondary" disabled={busy || externalBusy || refreshing} onClick={() => void reload()}>{text.reload}</Button></InlineError> : null}
    {candidate ? <div><p>{text.unsupported}: {candidate.model} · {candidate.thinking_level ?? ""} · {candidate.has_key ? text.stored : text.missing}</p>
      <Button variant="secondary" disabled={blocked} onClick={() => { acceptMetadata(candidate, true); }}>{text.review}</Button></div> : null}
    {notice ? <p role="status">{text.saved}</p> : null}
  </div>;
}
