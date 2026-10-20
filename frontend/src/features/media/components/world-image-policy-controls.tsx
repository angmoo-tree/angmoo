"use client";
import { useEffect, useEffectEvent, useRef, useState } from "react";
import { ImagePlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/form-controls";
import { SettingsCard } from "@/components/ui/settings-card";
import { CredentialFields, type SecretKeyMetadata, type SecretMetadata, type SecretProfile } from "@/components/ui/credential-fields";
import { ApiRequestError } from "@/lib/http/error-contract";
import { mergeEditedValue } from "@/lib/state/edited-fields";
import { useProductLeaveGuard } from "@/hooks/use-product-leave-guard";
import { useAuthRuntimeIdentity } from "@/hooks/use-auth-runtime-identity";
import { useUiText } from "@/hooks/use-ui-text";
import { useUiErrorText } from "@/hooks/use-ui-error-text";
import { useUiDateFormatter } from "@/hooks/use-ui-date-formatter";
import { getCatalog } from "../api/media-client";
import { getWorldImagePolicy, patchWorldImagePolicy, checkWorldImagePolicy, imageCredentialTransport, type WorldImagePolicy, type WorldImageSettings } from "../api/world-image-policy";
import type { Catalog } from "../types/media";
import { ImagePicker } from "./image-picker";
import { ComfyEditor, newComfyOptions } from "./comfy-editor";
import { comfyFailure } from "../utils/comfy-errors";
import { NovelOptionsEditor, NovelReferenceEditor, novelDefaults } from "./novel-options-editor";

type Changes = Parameters<typeof patchWorldImagePolicy>[3];
type PolicyCoordination = { refreshRevision?: number; externalBusy?: boolean; onChanged?: () => void; onBusyChange?: (busy: boolean) => void };
function usePolicy(worldId: string, actorId: string, refreshRevision = 0, onChanged?: () => void, purpose: "image" | "vision" = "image") {
  const t = useUiText("media"), errorText = useUiErrorText("media");
  const [read, setRead] = useState<WorldImagePolicy | null>(null), [error, setError] = useState<string | null>(null), [busy, setBusy] = useState(false), [reload, setReload] = useState(0);
  const [conflicts, setConflicts] = useState<string[]>([]);
  const active = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController(); active.current = controller;
    void getWorldImagePolicy(worldId, actorId, controller.signal).then(value => { if (!controller.signal.aborted && value.world_id === worldId && value.world_character_id === actorId) { setRead(value); setError(null); } }).catch(reason => { if (!controller.signal.aborted) setError(errorText(reason, "이미지 설정을 불러오지 못했어요.")); });
    return () => { controller.abort(); active.current?.abort(); };
  }, [worldId, actorId, reload, refreshRevision, errorText]);
  async function save(changes: Changes, baseline: WorldImagePolicy, check = false) {
    if (busy) return null;
    const controller = new AbortController(); active.current?.abort(); active.current = controller; setBusy(true);
    try {
      const latest = await getWorldImagePolicy(worldId, actorId, controller.signal);
      const merged: Changes = {}, paths: string[] = [];
      for (const key of Object.keys(changes) as (keyof Changes)[]) {
        const result = mergeEditedValue<unknown>(baseline[key], latest[key], changes[key], key);
        Object.assign(merged, { [key]: result.value }); paths.push(...result.conflicts);
      }
      if (paths.length) { setRead(latest); setConflicts(paths); return null; }
      const result = await (check ? checkWorldImagePolicy : patchWorldImagePolicy)(worldId, actorId, latest.revision, merged, controller.signal);
      if (controller.signal.aborted || result.world_id !== worldId || result.world_character_id !== actorId) return null;
      setRead(result); setError(null); setConflicts([]); onChanged?.(); return result;
    } catch (reason) { if (!controller.signal.aborted) setError(purpose === "vision" && reason instanceof ApiRequestError && reason.code === "world_credential_key_required" ? t("이미지 인식을 켜려면 먼저 인식용 API 키를 저장해 주세요.") : comfyFailure(reason, t, errorText(reason, "저장하지 못했어요. 입력을 보존했으니 최신 설정을 확인해주세요."))); return null; }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  return { read, error, busy, conflicts, save, refresh: () => setReload(value => value + 1), reviewed: () => setConflicts([]) };
}

function ConflictReview({ policy, onReview }: { policy: ReturnType<typeof usePolicy>; onReview: () => void }) {
  const t = useUiText("media");
  if (!policy.conflicts.length) return policy.error ? <p role="alert">{policy.error}</p> : null;
  const labels: Record<string, string> = { generation_limit: t("캐릭터 일일 생성 상한"), vision_limit: t("캐릭터 일일 인식 상한"), generation_enabled: t("새 게시글 자동 이미지 생성"), vision_enabled: t("SNS·Chat 이미지 인식 사용"), generation_settings: t("이미지 설정") };
  return <div role="alert"><p>{t("다른 곳에서 같은 항목을 변경했어요. 최신 값을 확인한 뒤 저장해주세요.")}</p>
    <dl>{policy.conflicts.map(path => { const field = path.split(".")[0] as keyof WorldImagePolicy; return <div key={path}><dt>{labels[field] ?? field}</dt><dd className="break-words whitespace-pre-wrap">{JSON.stringify(policy.read?.[field], null, 2)}</dd></div>; })}</dl>
    <Button variant="secondary" onClick={() => { onReview(); policy.reviewed(); }}>{t("최신 값을 확인했어요. 내 입력 유지")}</Button>
  </div>;
}

type VisionProps = { worldId: string; actorId: string; keyStatus: "loading" | "error" | "missing" | "saved"; onReloadKey: () => void } & PolicyCoordination;
export function WorldVisionControls(props: VisionProps) {
  const identity = useAuthRuntimeIdentity(`${props.worldId}:${props.actorId}:vision`);
  return <ScopedVisionControls key={identity} {...props} />;
}
function ScopedVisionControls({ worldId, actorId, keyStatus, onReloadKey, refreshRevision, externalBusy, onChanged, onBusyChange }: VisionProps) {
  const t = useUiText("media"), policy = usePolicy(worldId, actorId, refreshRevision, onChanged, "vision");
  const notifyBusy = useEffectEvent((value: boolean) => onBusyChange?.(value));
  useEffect(() => { notifyBusy(policy.busy); return () => notifyBusy(false); }, [policy.busy]);
  const formatDate = useUiDateFormatter();
  const [draft, setDraft] = useState<{ cap: number | null; enabled: boolean; baseline: WorldImagePolicy } | null>(null);
  const value = draft ?? (policy.read ? { cap: policy.read.vision_limit, enabled: policy.read.vision_enabled, baseline: policy.read } : null);
  useProductLeaveGuard(Boolean(draft) || policy.busy);
  if (!value) return <p role="status">{t(policy.error ? "이미지 설정을 불러오지 못했어요." : "설정 확인 중")}</p>;
  return <>
    <Field label={t("캐릭터 일일 인식 상한")}>{props => <Input {...props} type="number" min={1} max={10000} value={value.cap ?? ""} onChange={event => setDraft({ ...value, cap: event.target.value ? Number(event.target.value) : null })} />}</Field>
    <label className="flex min-h-11 items-center gap-3"><input type="checkbox" className="accent-action-primary" checked={value.enabled} disabled={!value.enabled && keyStatus !== "saved"} onChange={event => setDraft({ ...value, enabled: event.target.checked })} />{t("SNS·Chat 이미지 인식 사용")}</label>
    {keyStatus !== "saved" ? <p role={keyStatus === "error" ? "alert" : "status"}>{t(keyStatus === "loading" ? "인식용 키 상태를 확인하고 있어요." : keyStatus === "error" ? "인식용 키 상태를 확인하지 못했어요." : "이미지 인식을 켜려면 먼저 인식용 API 키를 저장해 주세요.")}{keyStatus === "error" ? <Button variant="secondary" onClick={onReloadKey}>{t("다시 불러오기")}</Button> : null}</p> : null}
    <p>{t("오늘 인식 {{used}} / {{limit}}회", { used: policy.read?.vision_usage ?? 0, limit: value.cap ?? "—" })}</p>
    {!value.cap ? <p>{t("상한을 설정해야 사용할 수 있어요.")}</p> : null}
    <p className="text-sm text-text-secondary">{t("다음 한도 초기화:")} {policy.read?.reset_at ? formatDate(policy.read.reset_at, policy.read.timezone) : "—"} · {policy.read?.timezone}</p>
    <ConflictReview policy={policy} onReview={() => { if (draft && policy.read) setDraft({ ...draft, baseline: policy.read }); }} />
    <div className="flex flex-wrap gap-2"><Button loading={policy.busy} disabled={externalBusy || (value.enabled && keyStatus !== "saved") || !draft || !value.cap || value.cap < 1 || value.cap > 10000 || policy.conflicts.length > 0} onClick={async () => { if (await policy.save({ vision_limit: value.cap, vision_enabled: value.enabled }, value.baseline)) setDraft(null); }}>{t("인식 설정 저장")}</Button><Button variant="ghost" disabled={policy.busy} onClick={policy.refresh}>{t("상태 새로고침")}</Button></div>
  </>;
}

import { imageUsesServiceKey } from "../utils/image-key-presentation";

const emptySettings = (): WorldImageSettings => ({ appearance: "", style: "", negative: "", reference_enabled: false, reference_asset_id: null, profiles: {} });
const modelLabels: Record<string, string> = { "nai-diffusion-4-5-full": "NovelAI V4.5 Full", "krea-v2/turbo": "Krea 2 Turbo", "z-image-turbo": "Z-Image Turbo", "nano-banana-2": "Nano Banana 2", "krea/krea-2-medium-turbo": "Krea 2 Medium Turbo", "google/gemini-3.1-flash-image": "Nano Banana 2", "openai/gpt-image-2.5-flare": "GPT Image 2.5 Flare" };
type GenerationProps = { worldId: string; actorId: string } & PolicyCoordination;
export function WorldImageGenerationCard(props: GenerationProps) {
  const identity = useAuthRuntimeIdentity(`${props.worldId}:${props.actorId}:image`);
  return <ScopedGenerationCard key={identity} {...props} />;
}
function ScopedGenerationCard({ worldId, actorId, onBusyChange, refreshRevision, externalBusy, onChanged }: GenerationProps) {
  const t = useUiText("media"), policy = usePolicy(worldId, actorId, refreshRevision, onChanged);
  const formatDate = useUiDateFormatter();
  const [catalog, setCatalog] = useState<Catalog | null>(null), [credential, setCredential] = useState<SecretMetadata | null>(null), [preview, setPreview] = useState<SecretProfile | null>(null);
  const [providerKey, setProviderKey] = useState<SecretKeyMetadata | null>(null);
  const [draft, setDraft] = useState<{ settings: WorldImageSettings; cap: number | null; enabled: boolean; baseline: WorldImagePolicy } | null>(null);
  const [uploading, setUploading] = useState(false), [partnerKey, setPartnerKey] = useState(""), [clearPartner, setClearPartner] = useState(false), [checked, setChecked] = useState(false);
  const [comfyValid, setComfyValid] = useState(false);
  const [credentialBusy, setCredentialBusy] = useState(false);
  const notifyBusy = useEffectEvent((value: boolean) => onBusyChange?.(value));
  useEffect(() => { notifyBusy(policy.busy || uploading || credentialBusy); }, [policy.busy, uploading, credentialBusy]);
  useEffect(() => () => notifyBusy(false), []);
  const [comfyReferenceSupported, setComfyReferenceSupported] = useState(false);
  useEffect(() => { const controller = new AbortController(); void getCatalog(controller.signal).then(value => { if (!controller.signal.aborted) setCatalog(value); }).catch(() => undefined); return () => controller.abort(); }, []);
  const value = draft ?? (policy.read ? { settings: { ...emptySettings(), ...policy.read.generation_settings }, cap: policy.read.generation_limit, enabled: policy.read.generation_enabled, baseline: policy.read } : null);
  const chosen = preview ?? credential;
  const profile = chosen ? `${chosen.provider}:${chosen.model}` : "";
  const options: Record<string, unknown> = value?.settings.profiles[profile]?.options ?? (chosen?.provider === "novelai" ? novelDefaults : chosen?.provider === "comfyui" ? newComfyOptions : {});
  const model = catalog?.models.find(item => `${item.provider}:${item.id}` === profile);
  const connection = value?.settings.profiles[profile]?.connection;
  const free = chosen?.provider === "novelai" && (options.mode ?? "opus_free") === "opus_free";
  const referenceSupported = chosen?.provider === "comfyui" ? comfyReferenceSupported : model?.reference_supported;
  const pendingProfile = chosen && credential && (chosen.provider !== credential.provider || chosen.model !== credential.model);
  useProductLeaveGuard(Boolean(draft) || Boolean(partnerKey) || clearPartner || uploading || policy.busy);
  const changeOptions = (next: Record<string, unknown>) => { if (value) { setChecked(false); setDraft({ ...value, settings: { ...value.settings, profiles: { ...value.settings.profiles, [profile]: { ...value.settings.profiles[profile], options: next } } } }); } };
  function changeNovelMode(mode: string) {
    if (!value) return;
    const currentMode = String(options.mode ?? "opus_free"), archived = value.settings.profiles[`${profile}:${mode}`];
    setChecked(false);
    setDraft({ ...value, settings: { ...value.settings, profiles: { ...value.settings.profiles,
      [`${profile}:${currentMode}`]: { options: { ...options }, connection: null },
      [profile]: { options: { ...novelDefaults, ...archived?.options, mode }, connection: null } } } });
  }
  async function save(check = false) {
    if (!value || pendingProfile) return;
    const result = await policy.save({ generation_limit: value.cap, generation_enabled: value.enabled, generation_settings: value.settings }, value.baseline, check);
    if (result) { setDraft(null); setChecked(check); }
  }
  return <SettingsCard elevated title={t("SNS 게시글 이미지 생성")} description={t("게시글에 사용할 이미지, 참조 사진과 일일 상한을 설정해요.")} icon={<ImagePlus size={20} />}>
    {catalog ? <CredentialFields scopeKey={`${worldId}:${actorId}:image`} profiles={[...catalog.models.map(item => ({ provider: item.provider, model: item.id, thinking_level: null, label: `${item.provider} · ${modelLabels[item.id] ?? item.id}` })), { provider: "comfyui", model: "workflow", thinking_level: null, label: "ComfyUI · workflow" }]}
      {...imageCredentialTransport(worldId, actorId, { ...(chosen?.provider === "comfyui" ? { ...(partnerKey ? { partner_api_key: partnerKey } : {}), ...(clearPartner ? { clear_partner_key: true } : {}) } : {}) })}
      refreshRevision={policy.read?.revision ?? 0} externalBusy={externalBusy || policy.busy || uploading}
      showSecretFields={imageUsesServiceKey} onSelectedKey={setProviderKey} onBusyChange={setCredentialBusy}
      onMetadata={setCredential} onProfileChange={next => { setPreview(next); setPartnerKey(""); setClearPartner(false); setChecked(false); }}
      onSaved={next => { setPreview({ ...next, label: "" }); setPartnerKey(""); setClearPartner(false); setChecked(false); policy.refresh(); onChanged?.(); }}
      text={{ loadFailed: t("설정을 불러오지 못했어요."), keyLoadFailed: t("키 상태를 불러오지 못했어요."), saveFailed: t("설정을 저장하지 못했어요. 입력을 확인해 주세요."), deleteFailed: t("키를 삭제하지 못했어요."), conflict: t("설정이 변경됐어요. 최신 내용을 확인해 주세요."), unknown: t("요청 결과를 확인하지 못했어요. 다시 저장하기 전에 현재 상태를 확인해 주세요."), review: t("최신 값을 확인했어요. 내 입력 유지"), model: t("이미지 서비스·모델"), key: t("새 이미지 API key"), stored: t("이 서비스의 API 키가 저장되어 있어요."), missing: t("이 서비스의 API 키를 등록해 주세요."), loading: t("이 서비스의 API 키 상태를 확인하고 있어요."), save: t(chosen?.provider === "comfyui" ? "서비스 설정 저장" : "키와 모델 저장"), remove: t("이미지 키 삭제"), confirm: t("이미지 API key를 삭제할까요?"), failed: t(chosen?.provider === "comfyui" ? "서비스 설정을 저장하지 못했어요." : "이 서비스의 API 키 상태를 확인하지 못했어요."), saved: t(chosen?.provider === "comfyui" ? "서비스 설정을 저장했어요." : "키와 모델을 저장했어요."), keep: t("비워 두면 저장된 키를 유지해요."), unsupported: t("현재 저장된 모델"), reload: t("최신 설정 확인") }}>
      {chosen?.provider === "comfyui" ? <><Field label={t("Comfy 계정 API 키")} helperText={providerKey?.provider === "comfyui" && providerKey.has_key ? t("Comfy 계정 키가 저장되어 있습니다") : t("Partner 노드를 사용할 계정 키")}>{props => <Input {...props} type="password" autoComplete="new-password" maxLength={4096} value={partnerKey} disabled={clearPartner} onChange={event => setPartnerKey(event.target.value)} />}</Field><label className="flex min-h-11 items-center gap-3"><input type="checkbox" className="accent-action-primary" checked={clearPartner} disabled={!credential?.has_partner_key} onChange={event => setClearPartner(event.target.checked)} />{t("Comfy 계정 키 삭제")}</label><p className="text-sm text-text-secondary">{t("Partner 노드에서 Comfy Credits를 사용할 계정 키입니다. workflow JSON에는 키를 넣지 않습니다.")}</p></> : null}
    </CredentialFields> : <p>{t("이미지 모델 목록 확인 중")}</p>}
    <p className="text-sm text-text-secondary">{t(chosen?.provider === "comfyui" ? "ComfyUI는 서버 인증 키 없이 연결해요. Partner 노드에는 별도의 Comfy 계정 키를 사용해요." : "서비스를 바꿔도 등록한 키는 보관하며, 다시 선택하면 해당 서비스의 키를 사용해요.")}</p>
    {value ? <>
      {pendingProfile ? <p role="status">{t(chosen?.provider === "comfyui" ? "먼저 서비스 설정을 저장한 뒤 이미지 설정을 저장해주세요." : "먼저 키와 모델을 저장한 뒤 이미지 설정을 저장해주세요.")}</p> : null}
      <div className="grid gap-4 sm:grid-cols-2"><Field label={t("캐릭터 일일 생성 상한")}>{props => <Input {...props} type="number" min={1} max={10000} value={value.cap ?? ""} onChange={event => setDraft({ ...value, cap: event.target.value ? Number(event.target.value) : null })} />}</Field><p className="self-end">{t("오늘 생성 {{used}} / {{limit}}회", { used: policy.read?.generation_usage ?? 0, limit: value.cap ?? "—" })}</p></div>
      {!value.cap ? <p>{t("상한을 설정해야 사용할 수 있어요.")}</p> : null}
      {chosen?.provider === "novelai" ? <NovelOptionsEditor options={options} disabled={policy.busy} onChange={changeOptions} onModeChange={changeNovelMode} /> : null}
      <div className="grid gap-4 sm:grid-cols-2">{Object.entries(model?.parameters ?? {}).map(([name, parameter]) => <Field key={name} label={name}>{props => parameter.values ? <Select {...props} value={String(options[name] ?? "")} onChange={event => { const next = { ...options }; if (event.target.value) next[name] = event.target.value; else delete next[name]; changeOptions(next); }}><option value="">{t("서비스 기본값")}</option>{parameter.values.map(item => <option key={item} value={item}>{item}</option>)}</Select> : <Input {...props} type={parameter.type === "integer" || parameter.type === "number" ? "number" : "text"} min={parameter.min} max={parameter.max} value={String(options[name] ?? "")} onChange={event => { const next = { ...options }; if (event.target.value) next[name] = parameter.type === "integer" || parameter.type === "number" ? Number(event.target.value) : event.target.value; else delete next[name]; changeOptions(next); }} />}</Field>)}</div>
      {chosen?.provider === "comfyui" ? <><ComfyEditor key={`${worldId}:${actorId}:${profile}`} scopeKey={`${worldId}:${actorId}:${profile}`} options={options} connection={connection} onChange={changeOptions} onValidityChange={setComfyValid} onReferenceSupportChange={setComfyReferenceSupported} disabled={policy.busy} /><label className="flex min-h-11 items-center gap-3"><input type="checkbox" className="accent-action-primary" checked={Boolean(options.partner_auth)} onChange={event => changeOptions({ ...options, partner_auth: event.target.checked })} />{t("Comfy Partner 계정 인증 사용")}</label></> : null}
      {([['appearance', '외형 (선택)'], ['style', '스타일 (선택)'], ['negative', '부정 프롬프트']] as const).map(([key, label]) => <Field key={key} label={t(label)}>{props => <Textarea {...props} rows={3} maxLength={key === "negative" ? 1800 : 1200} value={value.settings[key]} onChange={event => setDraft({ ...value, settings: { ...value.settings, [key]: event.target.value } })} />}</Field>)}
      {(chosen?.provider === "nanogpt" || chosen?.provider === "openrouter") && value.settings.negative ? <p className="text-sm text-text-secondary">{t("이 모델 경로에는 부정 프롬프트를 적용하지 않습니다. 입력 내용은 저장되며 긍정 프롬프트에 합치지 않습니다.")}</p> : null}
      <label className="flex min-h-11 items-center gap-3"><input type="checkbox" className="accent-action-primary" disabled={free || !referenceSupported || policy.busy} checked={!free && value.settings.reference_enabled} onChange={event => setDraft({ ...value, settings: { ...value.settings, reference_enabled: event.target.checked } })} />{t("참조 이미지 사용")}</label>
      <ImagePicker scopeKind="world_character" scopeId={actorId} value={value.settings.reference_asset_id ? { id: value.settings.reference_asset_id, url: value.settings.reference_url ?? `/api/v1/media/assets/${value.settings.reference_asset_id}/content`, allowed: true } : null} onBusyChange={setUploading} disabled={policy.busy} onChange={asset => setDraft({ ...value, settings: { ...value.settings, reference_asset_id: asset?.id ?? null, reference_url: asset?.url ?? null } })} />
      <p className="text-sm text-text-secondary">{free ? t("Opus 무차감 모드에서는 참조를 강제로 제외합니다. 등록한 사진은 유지됩니다.") : !referenceSupported ? t("참조를 지원하는 모델 또는 검증된 workflow가 필요합니다.") : t("직접 지정한 사진, 캐릭터 카드, 프로필 사진 순으로 참조해요. 사진이 없으면 텍스트 경로를 사용해요.")}</p>
      {chosen?.provider === "novelai" && !free && value.settings.reference_enabled ? <NovelReferenceEditor options={options} disabled={policy.busy} onChange={changeOptions} /> : null}
      <label className="flex min-h-11 items-center gap-3"><input type="checkbox" className="accent-action-primary" checked={value.enabled} disabled={model?.prompt_validation?.generation_available === false} onChange={event => setDraft({ ...value, enabled: event.target.checked })} />{t("새 게시글 자동 이미지 생성")}</label>
      <p role="status">{t("연결 상태:")} {connection?.ready ? connection.opus_verified ? t("Opus 혜택 확인됨") : t("모델 경로 확인 · 키 인증은 첫 생성에서 확인") : t("미확인")}</p>
      {model?.prompt_validation?.generation_available === false ? <p>{t("NovelAI 입력 검사에 필요한 파일을 확인할 수 없어 생성이 비활성화되어 있습니다. 설정은 저장할 수 있습니다.")}</p> : null}
      <ConflictReview policy={policy} onReview={() => { if (draft && policy.read) setDraft({ ...draft, baseline: policy.read }); }} />
      <div className="flex flex-wrap gap-2"><Button loading={policy.busy} disabled={externalBusy || credentialBusy || (chosen?.provider === "comfyui" && !comfyValid) || uploading || !value.cap || value.cap < 1 || value.cap > 10000 || Boolean(pendingProfile) || policy.conflicts.length > 0} onClick={() => void save(true)}>{t("연결·입력 확인 및 저장")}</Button><Button variant="secondary" disabled={externalBusy || credentialBusy || (chosen?.provider === "comfyui" && !comfyValid) || policy.busy || !draft || uploading || !value.cap || value.cap < 1 || value.cap > 10000 || Boolean(pendingProfile) || policy.conflicts.length > 0} onClick={() => void save()}>{t("이미지 설정 저장")}</Button><Button variant="ghost" disabled={policy.busy} onClick={policy.refresh}>{t("상태 새로고침")}</Button></div>
      {checked ? <p role="status">{t("연결과 입력을 확인하고 저장했습니다. 이미지 생성 요청은 보내지 않았습니다.")}</p> : null}
      <p className="text-sm text-text-secondary">{t("다음 한도 초기화:")} {policy.read?.reset_at ? formatDate(policy.read.reset_at) : "—"} · {policy.read?.timezone}</p>
    </> : <p>{t(policy.error ? "이미지 설정을 불러오지 못했어요." : "설정 확인 중")}</p>}
  </SettingsCard>;
}
