"use client";
import { useProductLeaveGuard } from "@/hooks/use-product-leave-guard";
import { useUiText } from "@/hooks/use-ui-text";
import { useUiErrorText } from "@/hooks/use-ui-error-text";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/hooks/use-auth";
import { captureAuthRequestScope, isCurrentAuthRequestScope } from "@/lib/auth/browser-session";
import { DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT } from "@/lib/runtime/runtime-config";
import { Button } from "@/components/ui/button";
import { InlineError } from "@/components/ui/feedback";
import { getCatalog, getGeneration, getGenerationProviderKey, saveGeneration } from "../api/media-client";
import type { Catalog, GenerationSettings, GenerationWrite, Provider } from "../types/media";
import { ComfyEditor, newComfyOptions } from "./comfy-editor";
import { comfyFailure } from "../utils/comfy-errors";
import { ImagePicker } from "./image-picker";
import styles from "./media-settings.module.css";
import { NovelOptionsEditor, NovelReferenceEditor, novelDefaults } from "./novel-options-editor";

import { useActiveScopedRead } from "@/hooks/use-active-scoped-read";
import { imageUsesServiceKey } from "../utils/image-key-presentation";

const labels: Record<string, string> = { "nai-diffusion-4-5-full": "NovelAI V4.5 Full", "krea-v2/turbo": "Krea 2 Turbo", "z-image-turbo": "Z-Image Turbo", "nano-banana-2": "Nano Banana 2", "krea/krea-2-medium-turbo": "Krea 2 Medium Turbo", "google/gemini-3.1-flash-image": "Nano Banana 2", "openai/gpt-image-2.5-flare": "GPT Image 2.5 Flare" };

function initial(saved: GenerationSettings): GenerationWrite {
  const provider = saved.provider ?? "novelai";
  return { expected_revision: saved.revision, provider, model: saved.model ?? "nai-diffusion-4-5-full", auto_enabled: saved.auto_enabled,
    daily_limit: saved.daily_limit, appearance: saved.appearance,
    style: saved.style, negative: saved.negative, reference_enabled: saved.active_profile.reference_initialized === false ? null : saved.active_profile.reference_enabled ?? false,
    reference_asset_id: saved.reference_asset_id, options: saved.active_profile.options ?? novelDefaults };
}

export function GenerationSettingsPanel({ characterId }: { characterId: string }) {
  const { user, sessionRevision } = useAuth();
  const [runtimeRevision, setRuntimeRevision] = useState(0);
  useEffect(() => {
    const changed = () => setRuntimeRevision(value => value + 1);
    window.addEventListener(DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT, changed);
    return () => window.removeEventListener(DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT, changed);
  }, []);
  return <ScopedGenerationSettings key={`${characterId}:${user?.id ?? ""}:${sessionRevision}:${runtimeRevision}`} characterId={characterId} />;
}
function ScopedGenerationSettings({ characterId }: { characterId: string }) {
  const uiText = useUiText("media");
  const errorText = useUiErrorText("media");
  const [saved, setSaved] = useState<GenerationSettings | null>(null); const [value, setValue] = useState<GenerationWrite | null>(null);
  const [catalog, setCatalog] = useState<Catalog | null>(null); const [key, setKey] = useState("");
  const provider = value?.provider;
  const readProviderKey = useCallback((signal: AbortSignal) => getGenerationProviderKey(characterId, provider ?? "novelai", signal), [characterId, provider]);
  const providerKey = useActiveScopedRead({ scopeKey: `${characterId}:${provider ?? ""}:image-key`, active: Boolean(provider), read: readProviderKey });
  const [partnerKey, setPartnerKey] = useState("");
  const [busy, setBusy] = useState(false); const [uploading, setUploading] = useState(false);
  const [comfyValid, setComfyValid] = useState(false);
  const [comfyReferenceSupported, setComfyReferenceSupported] = useState(false);
  const [error, setError] = useState<string | null>(null); const [notice, setNotice] = useState<string | null>(null);
  const writeRequest = useRef<AbortController | null>(null);
  useEffect(() => {
    const operation = new AbortController(), authScope = captureAuthRequestScope();
    Promise.all([getGeneration(characterId, operation.signal), getCatalog(operation.signal)]).then(([settings, models]) => {
      if (operation.signal.aborted || !isCurrentAuthRequestScope(authScope)) return;
      setSaved(settings); setValue(initial(settings)); setCatalog(models);
    }).catch(reason => { if (!operation.signal.aborted && isCurrentAuthRequestScope(authScope)) setError(errorText(reason, "이미지 설정을 불러오지 못했습니다.")); });
    return () => { operation.abort(); writeRequest.current?.abort(); };
  }, [characterId, errorText]);
  useProductLeaveGuard(Boolean(key || partnerKey || busy || uploading || (saved && value && JSON.stringify(initial(saved)) !== JSON.stringify(value))));
  function choose(provider: Provider, model: string, mode = "") {
    if (!value || !saved) return;
    const profile = saved.profiles[`${provider}:${model}:${mode}`];
    const supported = catalog?.models.find(m => m.provider === provider && m.id === model)?.reference_supported ?? false;
    setValue({ ...value, provider, model, auto_enabled: false, reference_enabled: provider === "comfyui" && (!profile || profile.reference_initialized === false) ? null : profile?.reference_enabled ?? (supported && mode !== "opus_free"),
      reference_asset_id: profile ? profile.reference_asset_id ?? null : value.reference_asset_id,
      options: profile?.options ?? (provider === "novelai" ? { ...novelDefaults, mode: mode || "opus_free" } : provider === "comfyui" ? newComfyOptions : {}) });
    if (provider !== value.provider) { setKey(""); setPartnerKey(""); }
    setNotice(null);
    setComfyReferenceSupported(false);
  }
  async function save(check = false, clear = false, clearPartner = false) {
    if (!value || busy || providerKey.loading || providerKey.error || !providerKey.data) return;
    const operation = new AbortController(), authScope = captureAuthRequestScope();
    writeRequest.current = operation; setBusy(true); setError(null); setNotice(null);
    try {
      const next = await saveGeneration(characterId, { ...value,
        ...(imageUsesServiceKey(value) && key ? { api_key: key } : {}),
        ...(partnerKey && !clearPartner ? { partner_api_key: partnerKey } : {}),
        ...(clear ? { clear_api_key: true, auto_enabled: false } : {}),
        ...(clearPartner ? { clear_partner_api_key: true, auto_enabled: false } : {}) }, check, operation.signal);
      if (operation.signal.aborted || !isCurrentAuthRequestScope(authScope)) return;
      setSaved(next); setValue(initial(next)); setKey(""); setPartnerKey(""); providerKey.refresh();
      setNotice(clearPartner ? uiText("Comfy 계정 키를 삭제했습니다.") : check ? uiText("연결과 입력을 확인하고 저장했습니다. 이미지 생성 요청은 보내지 않았습니다.") : uiText("이미지 설정을 저장했습니다."));
    } catch (reason) { if (!operation.signal.aborted && isCurrentAuthRequestScope(authScope)) setError(comfyFailure(reason, uiText, errorText(reason, "이미지 설정을 저장하지 못했습니다."))); }
    finally { if (!operation.signal.aborted && isCurrentAuthRequestScope(authScope)) setBusy(false); }
  }
  if (!value || !catalog) return <section className={styles.panel} aria-label={uiText("SNS 이미지 생성 설정")}><h3>{uiText("SNS 이미지 생성")}</h3>{error ? <InlineError>{error}</InlineError> : <p role="status">{uiText("설정을 불러오는 중…")}</p>}</section>;
  const model = catalog.models.find(m => m.provider === value.provider && m.id === value.model);
  const free = value.provider === "novelai" && value.options.mode === "opus_free";
  const profile = saved?.profiles[`${value.provider}:${value.model}:${value.options.mode ?? ""}`];
  const connection = !key && !partnerKey && profile && JSON.stringify(profile.options) === JSON.stringify(value.options) ? profile.connection : null;
  const referenceSupported = value.provider === "comfyui" ? comfyReferenceSupported : model?.reference_supported;
  const promptUnverified = value.provider === "novelai" && model?.prompt_validation?.exact_verified === false;
  const promptUnavailable = value.provider === "novelai" && model?.prompt_validation?.generation_available === false;
  return <section className={styles.panel} aria-label={uiText("SNS 이미지 생성 설정")}><h3>{uiText("SNS 게시글 이미지 생성")}</h3>
    <p>{uiText("새 Routine 게시글의 이번 장면을 외형·스타일과 합쳐 이미지 1장을 생성합니다. 기존 게시글은 자동 생성하지 않습니다.")}</p>
    <div className={styles.row}>
      <label>{uiText("이미지 서비스")}<select disabled={busy} value={value.provider} onChange={e => { const provider = e.target.value as Provider; const first = catalog.models.find(m => m.provider === provider); choose(provider, first?.id ?? "workflow", provider === "novelai" ? "opus_free" : ""); }}><option value="novelai">NovelAI</option><option value="comfyui">ComfyUI</option><option value="nanogpt">NanoGPT</option><option value="openrouter">OpenRouter</option></select></label>
      {value.provider !== "comfyui" ? <label>{uiText("이미지 모델")}<select disabled={busy} value={value.model} onChange={e => choose(value.provider, e.target.value, value.provider === "novelai" ? String(value.options.mode) : "")}>{catalog.models.filter(m => m.provider === value.provider).map(m => <option key={m.id} value={m.id}>{labels[m.id] ?? m.id}</option>)}</select></label> : <p>{uiText("workflow에 등록된 모델을 사용합니다.")}</p>}
    </div>
    {imageUsesServiceKey(value) ? <>
      <p role="status">{uiText(providerKey.loading ? "이 서비스의 API 키 상태를 확인하고 있어요." : providerKey.error ? "이 서비스의 API 키 상태를 확인하지 못했어요." : providerKey.data?.has_key ? "이 서비스의 API 키가 저장되어 있어요." : "이 서비스의 API 키를 등록해 주세요.")}</p>
      <label>{uiText("이미지 API 키")}<input type="password" autoComplete="new-password" value={key} onChange={e => setKey(e.target.value)} placeholder={providerKey.data?.has_key ? uiText("선택된 서비스에 저장된 키가 있습니다") : uiText("API 키를 입력해 주세요")} /></label>
    </> : <p>{uiText("ComfyUI는 서버 인증 키 없이 연결해요. Partner 노드에는 별도의 Comfy 계정 키를 사용해요.")}</p>}

    {value.provider === "comfyui" ? <>
      <label className={styles.toggle}><input type="checkbox" checked={Boolean(value.options.partner_auth)} disabled={busy} onChange={e => setValue({ ...value, options: { ...value.options, partner_auth: e.target.checked } })} />{uiText("Comfy Partner 계정 인증 사용")}</label>
      <label>{uiText("Comfy 계정 API 키")}<input type="password" autoComplete="off" value={partnerKey} onChange={e => setPartnerKey(e.target.value)} placeholder={providerKey.data?.provider === "comfyui" && providerKey.data.has_key ? uiText("Comfy 계정 키가 저장되어 있습니다") : uiText("Partner 노드를 사용할 계정 키")} /></label>
      <p className={styles.note}>{uiText("Partner 노드에서 Comfy Credits를 사용할 계정 키입니다. workflow JSON에는 키를 넣지 않습니다.")}</p>
      <Button type="button" variant="ghost" disabled={busy || !(providerKey.data?.provider === "comfyui" && providerKey.data.has_key)} onClick={() => void save(false, false, true)}>{uiText("Comfy 계정 키 삭제")}</Button>
    </> : null}
    {value.provider === "novelai" ? <NovelOptionsEditor options={value.options} disabled={busy} onChange={options => setValue({ ...value, options })} onModeChange={mode => choose("novelai", value.model, mode)} /> : null}
    {value.provider === "nanogpt" || value.provider === "openrouter" ? <>
      <div className={styles.row}>{Object.entries(model?.parameters ?? {}).filter(([name]) => ["resolution", "aspect_ratio", "quality", "background", "seed", "output_compression"].includes(name)).map(([name, parameter]) => <label key={name}>{name}{parameter.values ? <select value={String(value.options[name] ?? "")} onChange={e => { const next = { ...value.options }; if (e.target.value) next[name] = e.target.value; else delete next[name]; setValue({ ...value, options: next }); }}><option value="">{uiText("서비스 기본값")}</option>{parameter.values.map(item => <option key={item} value={item}>{item}</option>)}</select> : <input type="number" min={parameter.min ?? 0} max={parameter.max} value={String(value.options[name] ?? "")} onChange={e => { const next = { ...value.options }; if (e.target.value) next[name] = Number(e.target.value); else delete next[name]; setValue({ ...value, options: next }); }} />}</label>)}</div>
      <p className={styles.note}>{uiText("모델마다 지원하는 입력이 다릅니다. 가격이 확인되지 않은 항목은 무료로 표시하지 않습니다. 다른 서비스나 모델로 자동 전환하지 않습니다.")}</p>
    </> : null}
    {value.provider === "comfyui" ? <ComfyEditor key={`${characterId}:${value.provider}:${value.model}`} scopeKey={`${characterId}:${value.provider}:${value.model}`} options={value.options} connection={connection} onValidityChange={setComfyValid} onReferenceSupportChange={setComfyReferenceSupported} disabled={busy} onChange={options => setValue({ ...value, options, auto_enabled: false })} /> : null}
    <p className={styles.note}>{uiText("참조 사진과 외형·스타일이 모두 없어도 이번 게시글의 장면으로 생성할 수 있습니다. 참조 필수 workflow는 사진 또는 검증된 텍스트 경로가 필요합니다.")}</p>
    <label>{uiText("외형 (선택)")}<textarea rows={3} maxLength={1200} value={value.appearance} onChange={e => setValue({ ...value, appearance: e.target.value })} /></label>
    <label>{uiText("스타일 (선택)")}<textarea rows={2} maxLength={1200} value={value.style} onChange={e => setValue({ ...value, style: e.target.value })} /></label>
    <label>{uiText("부정 프롬프트")}<textarea rows={2} maxLength={1800} value={value.negative} onChange={e => setValue({ ...value, negative: e.target.value })} /></label>
    {(value.provider === "nanogpt" || value.provider === "openrouter") && value.negative ? <p className={styles.note}>{uiText("이 모델 경로에는 부정 프롬프트를 적용하지 않습니다. 입력 내용은 저장되며 긍정 프롬프트에 합치지 않습니다.")}</p> : null}
    <label className={styles.toggle}><input type="checkbox" disabled={free || !referenceSupported || busy} checked={!free && Boolean(value.reference_enabled ?? (value.provider === "comfyui" && referenceSupported))} onChange={e => setValue({ ...value, reference_enabled: e.target.checked })} />{uiText("참조 이미지 사용")}</label>
    <p className={styles.note}>{free ? uiText("Opus 무차감 모드에서는 참조를 강제로 제외합니다. 등록한 사진은 유지됩니다.") : !referenceSupported ? uiText("참조를 지원하는 모델 또는 검증된 workflow가 필요합니다.") : uiText("직접 지정 → 캐릭터 카드 PNG → 프로필 사진 순으로 사용합니다. 사진이 없으면 텍스트 경로를 사용합니다.")}</p>
    <ImagePicker scopeKind="character" scopeId={characterId} value={value.reference_asset_id ? { id: value.reference_asset_id, url: `/api/v1/media/assets/${value.reference_asset_id}/content`, allowed: true } : null} onChange={asset => setValue({ ...value, reference_asset_id: asset?.id ?? null })} disabled={busy} onBusyChange={setUploading} />
    {value.provider === "novelai" && !free && value.reference_enabled ? <NovelReferenceEditor options={value.options} disabled={busy} onChange={options => setValue({ ...value, options })} /> : null}
    <div className={styles.row}><label>{uiText("캐릭터 일일 생성 시도 상한")}<input type="number" min={1} max={10000} value={value.daily_limit ?? ""} onChange={e => setValue({ ...value, daily_limit: e.target.value ? Number(e.target.value) : null })} /></label></div>
    {saved?.reference_state ? <div aria-label={uiText("저장된 참조 적용 상태")}><p role="status">{uiText("저장된 참조 선호:")}{saved.reference_state.preferred ? "ON" : "OFF"} {uiText("· 실제 출처:")}{{ override: uiText("사용자 지정 이미지"), card: uiText("캐릭터 카드 이미지"), profile: uiText("프로필 이미지"), none: uiText("없음") }[saved.reference_state.source]}</p>
      <p className={styles.note}>{saved.reference_state.status === "available" ? uiText("저장된 설정의 참조 출처입니다. 실제 생성에는 생성 활성화와 입력 검증도 필요합니다.") : saved.reference_state.status === "forced_off" ? saved.reference_state.reason === "opus_free" ? uiText("Opus 전용 Anlas 사용 안 함 모드에서는 참조를 보내지 않습니다.") : uiText("선택한 모델은 참조 이미지를 지원하지 않습니다.") : saved.reference_state.status === "off" ? uiText("참조 사용이 꺼져 있습니다.") : saved.reference_state.status === "invalid" ? uiText("참조 이미지를 확인할 수 없습니다. 이미지를 교체하거나 설정을 확인해 주세요.") : saved.reference_state.generation_path === "unavailable" ? uiText("참조 선호는 ON이지만 사용할 이미지와 텍스트 경로가 없습니다.") : uiText("참조 선호는 ON이지만 사용할 이미지가 없어 텍스트 경로를 사용합니다.")}</p>
      {saved.reference_state.scene_only ? <p className={styles.note}>{uiText("저장된 참조 사진과 외형·스타일이 없어 이번 게시글의 장면만으로 생성합니다.")}</p> : null}
      {saved.reference_state.generation_path === "unavailable" ? <InlineError>{saved.reference_state.status === "invalid" ? uiText("참조 이미지를 확인해야 생성할 수 있습니다.") : uiText("참조 이미지나 검증된 텍스트 workflow가 필요합니다.")}</InlineError> : null}</div> : null}
    {promptUnavailable ? <p role="status" className={styles.note}>{uiText("NovelAI 입력 검사에 필요한 파일을 확인할 수 없어 생성이 비활성화되어 있습니다. 설정은 저장할 수 있습니다.")}</p> : promptUnverified ? <p role="status" className={styles.note}>{uiText("프롬프트 길이는 로컬 예비 검사로 확인합니다. 실제 서비스와의 정확한 일치는 미확인입니다. 계정·비용 조건과 입력 검사를 통과하면 생성할 수 있습니다.")}</p> : null}
    <label className={styles.toggle}><input type="checkbox" disabled={busy || (!value.auto_enabled && promptUnavailable)} checked={value.auto_enabled} onChange={e => setValue({ ...value, auto_enabled: e.target.checked })} />{uiText("새 Routine 게시글 자동 이미지 생성 허용")}</label>
    <p className={styles.note}>{uiText("연결·입력·키와 두 상한이 확인되어야 활성화됩니다. 참조 선택과 자동 생성 허용은 별개입니다. 기준 시간대:")}{catalog.quota_timezone}.</p>
    <p role="status">{uiText("연결 상태:")}{promptUnavailable ? uiText("입력 검사 준비 필요 · 생성 비활성화") : connection?.ready ? free ? connection.opus_verified ? uiText("Opus 혜택 확인됨") : uiText("Opus 혜택 미확인") : connection.credential_validation === "not_verified" ? uiText("모델 경로 확인 · 키 인증은 첫 생성에서 확인") : uiText("확인됨") : uiText("미확인")}</p>
    {providerKey.error ? <InlineError>{uiText("이 서비스의 API 키 상태를 확인하지 못했어요.")}<Button variant="secondary" onClick={providerKey.refresh}>{uiText("다시 시도")}</Button></InlineError> : null}
    <div className={styles.actions}><Button disabled={busy || uploading || providerKey.loading || Boolean(providerKey.error) || !providerKey.data || (value.provider === "comfyui" && !comfyValid)} onClick={() => void save(true)}>{uiText("연결·입력 확인 및 저장")}</Button><Button variant="secondary" disabled={busy || uploading || providerKey.loading || Boolean(providerKey.error) || !providerKey.data || (value.provider === "comfyui" && !comfyValid)} onClick={() => void save()}>{uiText("설정 저장")}</Button>{imageUsesServiceKey(value) ? <Button variant="ghost" disabled={busy || !providerKey.data?.has_key} onClick={() => void save(false, true)}>{uiText("이미지 키 삭제")}</Button> : null}</div>
    {notice ? <p role="status">{notice}</p> : null}{error ? <InlineError>{error}</InlineError> : null}
  </section>;
}
