"use client";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { InlineError } from "@/components/ui/feedback";
import { getCatalog, getGeneration, saveGeneration, getComfySample } from "../api/media-client";
import type { Catalog, GenerationSettings, GenerationWrite, Provider, Workflow, Connection } from "../types/media";
import { ImagePicker } from "./image-picker";
import styles from "./media-settings.module.css";

const labels: Record<string, string> = { "nai-diffusion-4-5-full": "NovelAI V4.5 Full", "krea-v2/turbo": "Krea 2 Turbo", "z-image-turbo": "Z-Image Turbo", "nano-banana-2": "Nano Banana 2", "krea/krea-2-medium-turbo": "Krea 2 Medium Turbo", "google/gemini-3.1-flash-image": "Nano Banana 2", "openai/gpt-image-2.5-flare": "GPT Image 2.5 Flare" };
const novelDefaults = { mode: "opus_free", width: 1024, height: 1024, steps: 28, scale: 5, sampler: "k_euler_ancestral", noise_schedule: "karras", seed: -1, cfg_rescale: 0, decrisper: false, variety_boost: false, reference_strength: 1, reference_fidelity: 1, reference_type: "character&style" };
function initial(saved: GenerationSettings): GenerationWrite {
  const provider = saved.provider ?? "novelai";
  return { expected_revision: saved.revision, installation_expected_revision: saved.installation_revision, provider, model: saved.model ?? "nai-diffusion-4-5-full", auto_enabled: saved.auto_enabled,
    daily_limit: saved.daily_limit, installation_daily_limit: saved.installation_daily_limit, appearance: saved.appearance,
    style: saved.style, negative: saved.negative, reference_enabled: saved.active_profile.reference_initialized === false ? null : saved.active_profile.reference_enabled ?? false,
    reference_asset_id: saved.reference_asset_id, options: saved.active_profile.options ?? novelDefaults };
}

export function GenerationSettingsPanel({ characterId }: { characterId: string }) {
  const [saved, setSaved] = useState<GenerationSettings | null>(null); const [value, setValue] = useState<GenerationWrite | null>(null);
  const [catalog, setCatalog] = useState<Catalog | null>(null); const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false); const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null); const [notice, setNotice] = useState<string | null>(null);
  useEffect(() => { const operation = new AbortController(); Promise.all([getGeneration(characterId, operation.signal), getCatalog(operation.signal)]).then(([settings, models]) => { setSaved(settings); setValue(initial(settings)); setCatalog(models); }).catch(reason => { if (!operation.signal.aborted) setError(reason instanceof Error ? reason.message : "이미지 설정을 불러오지 못했습니다."); }); return () => operation.abort(); }, [characterId]);
  function choose(provider: Provider, model: string, mode = "") {
    if (!value || !saved) return;
    const profile = saved.profiles[`${provider}:${model}:${mode}`];
    const supported = catalog?.models.find(m => m.provider === provider && m.id === model)?.reference_supported ?? false;
    setValue({ ...value, provider, model, auto_enabled: false, reference_enabled: provider === "comfyui" && (!profile || profile.reference_initialized === false) ? null : profile?.reference_enabled ?? (supported && mode !== "opus_free"),
      reference_asset_id: profile ? profile.reference_asset_id ?? null : value.reference_asset_id,
      options: profile?.options ?? (provider === "novelai" ? { ...novelDefaults, mode: mode || "opus_free" } : provider === "comfyui" ? { base_url: "http://127.0.0.1:8188", values: {} } : {}) });
    setKey(""); setNotice(null);
  }
  async function save(check = false, clear = false) {
    if (!value) return; setBusy(true); setError(null); setNotice(null);
    try { const next = await saveGeneration(characterId, { ...value, ...(key ? { api_key: key } : {}), ...(clear ? { clear_api_key: true, auto_enabled: false } : {}) }, check); setSaved(next); setValue(initial(next)); setKey(""); setNotice(check ? "연결과 입력을 확인하고 저장했습니다. 이미지 생성 요청은 보내지 않았습니다." : "이미지 설정을 저장했습니다."); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "이미지 설정을 저장하지 못했습니다."); }
    finally { setBusy(false); }
  }
  if (!value || !catalog) return <section className={styles.panel} aria-label="SNS 이미지 생성 설정"><h3>SNS 이미지 생성</h3>{error ? <InlineError>{error}</InlineError> : <p role="status">설정을 불러오는 중…</p>}</section>;
  const model = catalog.models.find(m => m.provider === value.provider && m.id === value.model);
  const free = value.provider === "novelai" && value.options.mode === "opus_free";
  const profile = saved?.profiles[`${value.provider}:${value.model}:${value.options.mode ?? ""}`];
  const connection = !key && profile && JSON.stringify(profile.options) === JSON.stringify(value.options) ? profile.connection : null;
  const referenceSupported = value.provider === "comfyui" ? Boolean(connection?.reference_supported) : model?.reference_supported;
  const setOption = (name: string, next: unknown) => {
    const options = { ...value.options, [name]: next };
    if (free && ["width", "height"].includes(name)) {
      const other = name === "width" ? "height" : "width";
      options[other] = Math.min(Number(options[other]), Math.floor(1048576 / Math.max(64, Number(next)) / 64) * 64);
    }
    setValue({ ...value, options });
  };
  return <section className={styles.panel} aria-label="SNS 이미지 생성 설정"><h3>SNS 게시글 이미지 생성</h3>
    <p>새 Routine 게시글의 이번 장면을 외형·스타일과 합쳐 이미지 1장을 생성합니다. 기존 게시글은 자동 생성하지 않습니다.</p>
    <div className={styles.row}>
      <label>이미지 서비스<select disabled={busy} value={value.provider} onChange={e => { const provider = e.target.value as Provider; const first = catalog.models.find(m => m.provider === provider); choose(provider, first?.id ?? "workflow", provider === "novelai" ? "opus_free" : ""); }}><option value="novelai">NovelAI</option><option value="comfyui">ComfyUI</option><option value="nanogpt">NanoGPT</option><option value="openrouter">OpenRouter</option></select></label>
      {value.provider !== "comfyui" ? <label>이미지 모델<select disabled={busy} value={value.model} onChange={e => choose(value.provider, e.target.value, value.provider === "novelai" ? String(value.options.mode) : "")}>{catalog.models.filter(m => m.provider === value.provider).map(m => <option key={m.id} value={m.id}>{labels[m.id] ?? m.id}</option>)}</select></label> : <p>workflow에 등록된 모델을 사용합니다.</p>}
    </div>
    {value.provider === "novelai" ? <><label>비용 모드<select disabled={busy} value={String(value.options.mode)} onChange={e => choose("novelai", value.model, e.target.value)}><option value="opus_free">Anlas 사용 안 함 — Opus 전용</option><option value="allow_anlas">Anlas 사용 허용</option></select></label>
      <p className={styles.note}>{free ? "활성 Opus 혜택을 확인해야 합니다. Steps 28 이하·면적 1,048,576픽셀 이하·1장으로 제한하며 참조 이미지를 보내지 않습니다." : "설정에 따른 Anlas 사용을 허용합니다. 참조 이미지 1장당 생성 1장마다 5 Anlas가 추가됩니다. 실제 사용량이 0일 수도 있습니다."}</p>
      <div className={styles.row}>{(["width", "height", "steps", "scale", "cfg_rescale", "seed"] as const).map(name => <label key={name}>{{ width: "가로", height: "세로", steps: "Steps", scale: "CFG scale", cfg_rescale: "CFG rescale", seed: "Seed (-1: 무작위)" }[name]}<input type="number" disabled={busy} value={Number(value.options[name])} min={name === "seed" ? -1 : name === "width" || name === "height" ? 64 : name === "steps" ? 1 : 0} max={name === "steps" ? free ? 28 : 50 : name === "scale" ? 10 : name === "cfg_rescale" ? 1 : undefined} step={name === "width" || name === "height" ? 64 : name === "scale" || name === "cfg_rescale" ? .1 : 1} onChange={e => setOption(name, Number(e.target.value))} /></label>)}</div>
      <div className={styles.row}><label>Sampler<select value={String(value.options.sampler)} onChange={e => setOption("sampler", e.target.value)}>{["k_euler", "k_euler_ancestral", "k_dpmpp_2s_ancestral", "k_dpmpp_2m", "k_dpmpp_sde", "ddim_v3"].map(item => <option key={item}>{item}</option>)}</select></label><label>Noise schedule<select value={String(value.options.noise_schedule)} onChange={e => setOption("noise_schedule", e.target.value)}>{["native", "karras", "exponential", "polyexponential"].map(item => <option key={item}>{item}</option>)}</select></label></div>
      {(["decrisper", "variety_boost"] as const).map(name => <label className={styles.toggle} key={name}><input type="checkbox" checked={Boolean(value.options[name])} onChange={e => setOption(name, e.target.checked)} />{name === "decrisper" ? "Decrisper" : "Variety Boost"}</label>)}<p className={styles.note}>V4.5 Full에는 SMEA 옵션을 적용하지 않습니다. 영어 프롬프트의 로컬 T5 길이 검사를 사용하며 자동 번역하지 않습니다.</p>
    </> : null}
    {value.provider === "nanogpt" || value.provider === "openrouter" ? <>
      <div className={styles.row}>{Object.entries(model?.parameters ?? {}).filter(([name]) => ["resolution", "aspect_ratio", "quality", "background", "seed", "output_compression"].includes(name)).map(([name, parameter]) => <label key={name}>{name}{parameter.values ? <select value={String(value.options[name] ?? "")} onChange={e => { const next = { ...value.options }; if (e.target.value) next[name] = e.target.value; else delete next[name]; setValue({ ...value, options: next }); }}><option value="">서비스 기본값</option>{parameter.values.map(item => <option key={item} value={item}>{item}</option>)}</select> : <input type="number" min={parameter.min ?? 0} max={parameter.max} value={String(value.options[name] ?? "")} onChange={e => { const next = { ...value.options }; if (e.target.value) next[name] = Number(e.target.value); else delete next[name]; setValue({ ...value, options: next }); }} />}</label>)}</div>
      <p className={styles.note}>모델마다 지원하는 입력이 다릅니다. 가격이 확인되지 않은 항목은 무료로 표시하지 않습니다. 다른 서비스나 모델로 자동 전환하지 않습니다.</p>
    </> : null}
    {value.provider === "comfyui" ? <ComfyEditor options={value.options} connection={connection} onChange={options => setValue({ ...value, options, auto_enabled: false })} /> : null}
    <p className={styles.note}>참조 사진과 외형·스타일이 모두 없어도 이번 게시글의 장면으로 생성할 수 있습니다. 참조 필수 workflow는 사진 또는 검증된 텍스트 경로가 필요합니다.</p>
    <label>외형 (선택)<textarea rows={3} maxLength={1200} value={value.appearance} onChange={e => setValue({ ...value, appearance: e.target.value })} /></label>
    <label>스타일 (선택)<textarea rows={2} maxLength={1200} value={value.style} onChange={e => setValue({ ...value, style: e.target.value })} /></label>
    <label>부정 프롬프트<textarea rows={2} maxLength={1800} value={value.negative} onChange={e => setValue({ ...value, negative: e.target.value })} /></label>
    {(value.provider === "nanogpt" || value.provider === "openrouter") && value.negative ? <p className={styles.note}>이 모델 경로에는 부정 프롬프트를 적용하지 않습니다. 입력 내용은 저장되며 긍정 프롬프트에 합치지 않습니다.</p> : null}
    <label className={styles.toggle}><input type="checkbox" disabled={free || !referenceSupported || busy} checked={!free && Boolean(value.reference_enabled)} onChange={e => setValue({ ...value, reference_enabled: e.target.checked })} />참조 이미지 사용</label>
    <p className={styles.note}>{free ? "Opus 무차감 모드에서는 참조를 강제로 제외합니다. 등록한 사진은 유지됩니다." : !referenceSupported ? "참조를 지원하는 모델 또는 검증된 workflow가 필요합니다." : "직접 지정 → 캐릭터 카드 PNG → 프로필 사진 순으로 사용합니다. 사진이 없으면 텍스트 경로를 사용합니다."}</p>
    <ImagePicker scopeKind="character" scopeId={characterId} value={value.reference_asset_id ? { id: value.reference_asset_id, url: `/api/v1/media/assets/${value.reference_asset_id}/content`, allowed: true } : null} onChange={asset => setValue({ ...value, reference_asset_id: asset?.id ?? null })} disabled={busy} onBusyChange={setUploading} />
    {value.provider === "novelai" && !free && value.reference_enabled ? <div className={styles.row}><label>참조 종류<select value={String(value.options.reference_type)} onChange={e => setOption("reference_type", e.target.value)}>{["character", "style", "character&style"].map(item => <option key={item}>{item}</option>)}</select></label>{["reference_strength", "reference_fidelity"].map(name => <label key={name}>{name === "reference_strength" ? "Strength" : "Fidelity"}<input type="number" min={0} max={1} step={.05} value={Number(value.options[name])} onChange={e => setOption(name, Number(e.target.value))} /></label>)}</div> : null}
    <label>이미지 API 키{value.provider === "comfyui" ? " (서버 인증이 있을 때만)" : ""}<input type="password" autoComplete="off" value={key} onChange={e => setKey(e.target.value)} placeholder={saved?.has_api_key ? "선택된 서비스에 저장된 키가 있습니다" : "API 키를 입력해 주세요"} /></label>
    <div className={styles.row}><label>캐릭터 일일 생성 시도 상한<input type="number" min={1} max={10000} value={value.daily_limit ?? ""} onChange={e => setValue({ ...value, daily_limit: e.target.value ? Number(e.target.value) : null })} /></label><label>설치 전체 일일 생성 시도 상한<input type="number" min={1} max={10000} value={value.installation_daily_limit ?? ""} onChange={e => setValue({ ...value, installation_daily_limit: e.target.value ? Number(e.target.value) : null })} /></label></div>
    <label className={styles.toggle}><input type="checkbox" disabled={busy} checked={value.auto_enabled} onChange={e => setValue({ ...value, auto_enabled: e.target.checked })} />새 Routine 게시글 자동 이미지 생성 허용</label>
    <p className={styles.note}>연결·입력·키와 두 상한이 확인되어야 활성화됩니다. 참조 선택과 자동 생성 허용은 별개입니다. 기준 시간대: {catalog.quota_timezone}.</p>
    <p role="status">연결 상태: {connection?.ready ? free ? connection.opus_verified ? "Opus 혜택 확인됨" : "Opus 혜택 미확인" : connection.credential_validation === "not_verified" ? "모델 경로 확인 · 키 인증은 첫 생성에서 확인" : "확인됨" : "미확인"}</p>
    <div className={styles.actions}><Button disabled={busy || uploading} onClick={() => void save(true)}>연결·입력 확인 및 저장</Button><Button variant="secondary" disabled={busy || uploading} onClick={() => void save()}>설정 저장</Button><Button variant="ghost" disabled={busy || !saved?.has_api_key} onClick={() => void save(false, true)}>이미지 키 삭제</Button></div>
    {notice ? <p role="status">{notice}</p> : null}{error ? <InlineError>{error}</InlineError> : null}
  </section>;
}

const roles = ["positive", "negative", "width", "height", "steps", "cfg", "sampler", "scheduler", "seed", "denoise", "model", "vae", "clip_skip", "reference"];
function ComfyEditor({ options, connection, onChange }: { options: Record<string, unknown>; connection?: Connection | null; onChange: (options: Record<string, unknown>) => void }) {
  const [path, setPath] = useState<"workflow" | "text_workflow">("workflow");
  const workflow = options[path] as Workflow | undefined;
  const values = (options.values ?? {}) as Record<string, string | number>;
  const [error, setError] = useState<string | null>(null);
  function importPrompt(raw: string) {
    try { const prompt = JSON.parse(raw) as Workflow["prompt"]; if (!prompt || Array.isArray(prompt) || Object.values(prompt).some(node => !node.class_type || !node.inputs)) throw new Error("API 형식의 workflow JSON이 필요합니다.");
      onChange({ ...options, [path]: { prompt, bindings: workflow?.bindings ?? {}, output_node: workflow?.output_node ?? "", reference_required: path === "workflow" && (workflow?.reference_required ?? false) } }); setError(null);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "JSON을 읽을 수 없습니다."); }
  }
  async function sample(kind: "text" | "reference") {
    try { const example = await getComfySample(kind); const text = kind === "reference" ? await getComfySample("text") : null; onChange({ ...options, [path]: example.workflow, ...(text && path === "workflow" ? { text_workflow: text.workflow } : {}), values: example.values }); setError(`예시를 불러왔습니다. 서버에 ${example.dependencies.nodes.join(", ")} 노드와 ${example.dependencies.models.join(", ")} 모델을 준비하고 모델명을 맞춰 주세요.`); }
    catch (reason) { setError(String(reason)); }
  }
  function binding(role: string, nodeId: string, inputName: string) {
    if (!workflow) return; const bindings = { ...workflow.bindings }; const nextValues = { ...values };
    if (!nodeId || !inputName) { delete bindings[role]; delete nextValues[role]; }
    else { bindings[role] = { node_id: nodeId, input_name: inputName }; const original = workflow.prompt[nodeId].inputs[inputName]; if (!["positive", "negative", "reference"].includes(role) && (typeof original === "number" || typeof original === "string")) nextValues[role] = original; }
    onChange({ ...options, values: nextValues, [path]: { ...workflow, bindings, reference_required: path === "workflow" && Boolean(bindings.reference) } });
  }
  return <div className={styles.panel}><h4>ComfyUI workflow 입력</h4><label>서버 주소<input value={String(options.base_url ?? "http://127.0.0.1:8188")} onChange={e => onChange({ ...options, base_url: e.target.value })} /></label>
    <p className={styles.note}>ComfyUI에서 실행용 API JSON을 저장해 가져옵니다. 내부에서 로컬 모델이나 외부 API 노드를 사용할 수 있습니다. API 키는 ComfyUI 서버에 관리하고 JSON에 비밀을 넣지 마세요.</p>
    <div className={styles.actions}><Button type="button" variant="secondary" aria-pressed={path === "workflow"} onClick={() => setPath("workflow")}>기본 workflow 입력</Button><Button type="button" variant="secondary" aria-pressed={path === "text_workflow"} onClick={() => setPath("text_workflow")}>참조 없는 텍스트 경로 입력</Button></div>
    <p role="status">{path === "workflow" ? "기본 생성 경로의 연결과 값을 설정합니다." : "참조가 없을 때 생성 제출 전에 사용할 텍스트 경로를 설정합니다. 생성 실패 후 자동 전환하지 않습니다."}</p>
    <div className={styles.actions}><Button type="button" variant="ghost" onClick={() => void sample("text")}>텍스트 예시</Button>{path === "workflow" ? <Button type="button" variant="ghost" onClick={() => void sample("reference")}>참조 예시와 텍스트 경로</Button> : null}</div>
    <label>API workflow 파일<input type="file" accept="application/json,.json" onChange={e => { const file = e.target.files?.[0]; if (file) void file.text().then(raw => importPrompt(raw)); }} /></label>
    <label>불러온 API workflow JSON<textarea readOnly rows={6} value={workflow ? JSON.stringify(workflow.prompt, null, 2) : ""} /></label>
    {workflow ? <><label>이미지 출력 노드<select value={workflow.output_node} onChange={e => onChange({ ...options, [path]: { ...workflow, output_node: e.target.value } })}><option value="">출력 노드 선택</option>{Object.entries(workflow.prompt).map(([id, node]) => <option key={id} value={id}>{id} · {node.class_type}</option>)}</select></label>
      {roles.filter(role => path === "workflow" || role !== "reference").map(role => { const selected = workflow.bindings[role]; const node = selected ? workflow.prompt[selected.node_id] : undefined; const choices = selected && node ? connection?.object_info?.[node.class_type]?.input?.required?.[selected.input_name]?.[0] : undefined;
        return <div className={`${styles.row} ${styles.binding}`} key={role}><label>{role} 입력 노드<select value={selected?.node_id ?? ""} onChange={e => { const id = e.target.value; const name = id ? Object.keys(workflow.prompt[id].inputs)[0] ?? "" : ""; binding(role, id, name); }}><option value="">연결 안 함</option>{Object.entries(workflow.prompt).map(([id, item]) => <option key={id} value={id}>{id} · {item.class_type}</option>)}</select></label>{selected && node ? <label>입력 위치<select value={selected.input_name} onChange={e => binding(role, selected.node_id, e.target.value)}>{Object.keys(node.inputs).map(name => <option key={name}>{name}</option>)}</select></label> : null}{selected && !["positive", "negative", "reference"].includes(role) ? <label>{role} 값{Array.isArray(choices) ? <select value={String(values[role] ?? "")} onChange={e => onChange({ ...options, values: { ...values, [role]: e.target.value } })}>{choices.map(choice => <option key={String(choice)}>{String(choice)}</option>)}</select> : <input type={typeof values[role] === "number" ? "number" : "text"} value={values[role] ?? ""} onChange={e => onChange({ ...options, values: { ...values, [role]: typeof values[role] === "number" ? Number(e.target.value) : e.target.value } })} />}</label> : null}</div>;
      })}
      {path === "workflow" && workflow.reference_required ? <p className={styles.note}>참조가 없을 때 사용할 텍스트 경로도 위 버튼에서 입력 연결과 출력 노드를 설정해 주세요.</p> : null}
    </> : null}{error ? <p role="status">{error}</p> : null}
  </div>;
}
