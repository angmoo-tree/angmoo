"use client";
import { useEffect, useId, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { InlineError } from "@/components/ui/feedback";
import { useProductLeaveGuard } from "@/hooks/use-product-leave-guard";
import { useUiText } from "@/hooks/use-ui-text";
import { useAuthRuntimeIdentity } from "@/hooks/use-auth-runtime-identity";
import { analyzeComfyWorkflow, getComfyApiSample } from "../api/media-client";
import type { Connection, WorkflowInput, WorkflowAnalysis, VersionedWorkflow, OutputPolicy } from "../types/media";
import { comfyFailure } from "../utils/comfy-errors";
import { replaceComfyGraph, retainedComfyContract, serializeComfyGraph } from "../utils/comfy-editor-draft";
import styles from "./media-settings.module.css";

type Path = "workflow" | "text_workflow";
type Options = Record<string, unknown>;
const paths: Path[] = ["workflow", "text_workflow"];
const integers = new Set(["width", "height", "steps", "seed", "clip_skip"]);
const numeric = new Set([...integers, "cfg", "denoise"]);
const automatic = new Set(["positive", "negative", "reference"]);
export const newComfyOptions = { options_schema_version: 2, clip_skip_value_mode: "skip_count", base_url: "http://127.0.0.1:8188", values: { seed: -1, clip_skip: 1 } };
const workflowAt = (options: Options, path: Path) => options[path] as WorkflowInput | undefined;
const modeOf = (workflow?: WorkflowInput) => workflow && "input_mode" in workflow ? workflow.input_mode : "node_bindings";
const sourceOf = (workflow?: WorkflowInput) => workflow ? JSON.stringify(workflow.prompt, null, 2) : "";

type ComfyEditorProps = {
  options: Options; connection?: Connection | null; onChange: (next: Options) => void;
  onValidityChange?: (valid: boolean) => void; onReferenceSupportChange?: (supported: boolean) => void; disabled?: boolean;scopeKey?:string;
};
export function ComfyEditor(props:ComfyEditorProps){
  const identity=useAuthRuntimeIdentity(props.scopeKey??"comfy-editor");
  return <ScopedComfyEditor key={identity} {...props}/>;
}
function ScopedComfyEditor({ options, connection, onChange, onValidityChange, onReferenceSupportChange, disabled = false }:ComfyEditorProps) {
  const t = useUiText("media"), id = useId();
  const [path, setPath] = useState<Path>("workflow");
  const [raw, setRaw] = useState<Record<Path, string>>(() => ({ workflow: sourceOf(workflowAt(options, "workflow")), text_workflow: sourceOf(workflowAt(options, "text_workflow")) }));
  const acceptedRaw = useRef(raw);
  const [analyses, setAnalyses] = useState<Partial<Record<Path, WorkflowAnalysis>>>({});
  const [errors, setErrors] = useState<Partial<Record<Path, unknown>>>({});
  const [downloadError,setDownloadError]=useState<unknown>(null);
  const intents=useRef<Partial<Record<Path,"replace">>>({});
  const readRevision=useRef(0),analysisController=useRef<AbortController|null>(null),sampleController=useRef<AbortController|null>(null);
  const [operationRevision,setOperationRevision]=useState(0);
  const [readable,setReadable]=useState<Record<Path,boolean>>({workflow:true,text_workflow:true});
  const downloads=useRef(new Set<AbortController>()),urls=useRef(new Set<string>());
  const [valid, setValid] = useState(false), [analyzing, setAnalyzing] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const latest = useRef({ options, onChange, onValidityChange });
  useEffect(() => { latest.current = { options, onChange, onValidityChange }; }, [options, onChange, onValidityChange]);
  const workflow = workflowAt(options, path), legacy = options.options_schema_version !== 2 && Boolean(workflowAt(options, "workflow"));
  const mode = workflow ? modeOf(workflow) : "placeholders";
  const primaryMode = modeOf(workflowAt(options, "workflow")), fallbackMode = modeOf(workflowAt(options, "text_workflow"));
  const primaryContract=JSON.stringify(retainedComfyContract(workflowAt(options,"workflow")));
  const fallbackContract=JSON.stringify(retainedComfyContract(workflowAt(options,"text_workflow")));
  useEffect(()=>()=>{readRevision.current++;analysisController.current?.abort();sampleController.current?.abort();for(const request of downloads.current)request.abort();for(const url of urls.current)URL.revokeObjectURL(url);},[]);
  function invalidatePending(blockSource?:Path){readRevision.current++;analysisController.current?.abort();sampleController.current?.abort();if(blockSource)setReadable(previous=>({...previous,[blockSource]:false}));setOperationRevision(readRevision.current);setValid(false);setAnalyzing(true);latest.current.onValidityChange?.(false);return readRevision.current;}
  useProductLeaveGuard(paths.some(item => raw[item] !== acceptedRaw.current[item]));
  useEffect(() => {
    const controller = new AbortController();
    analysisController.current=controller;
    setValid(false); setAnalyzing(true); latest.current.onValidityChange?.(false);
    const timer = setTimeout(() => {
      void Promise.all(paths.map(async item => {
        if(!readable[item])return false;
        const source = raw[item];
        if (!source) {
          setAnalyses(previous => ({ ...previous, [item]: undefined }));
          return item === "text_workflow" && !workflowAt(latest.current.options, item);
        }
        try {
          if (new TextEncoder().encode(source).length > 2 * 1024 * 1024) throw new Error("size");
          const current = workflowAt(latest.current.options, item);
          const replacing=intents.current[item]==="replace";
          const analyzed = await analyzeComfyWorkflow(source, replacing?"placeholders":current ? modeOf(current) : "placeholders", controller.signal,
            replacing?undefined:retainedComfyContract(current));
          if (controller.signal.aborted) return false;
          setAnalyses(previous => ({ ...previous, [item]: analyzed }));
          setErrors(previous => ({ ...previous, [item]: undefined }));
          acceptedRaw.current = { ...acceptedRaw.current, [item]: source };
          // Keep legacy contracts and the exact draft until an explicit edit is accepted.
          if (replacing || JSON.stringify(analyzed.prompt) !== JSON.stringify(current?.prompt)) {
            const base = latest.current.options;
            const hasLegacy = base.options_schema_version !== 2 && Boolean(workflowAt(base, "workflow"));
            const replacement: WorkflowInput = current ? { ...current, prompt: analyzed.prompt } : hasLegacy
              ? { prompt: analyzed.prompt, bindings: {}, output_node: Object.keys(analyzed.prompt)[0], reference_required: false }
              : { input_mode: "placeholders", prompt: analyzed.prompt, output: { mode: "auto_first_image" } };
            const next = replacing?replaceComfyGraph(base,item,analyzed):{ ...base, [item]: replacement, ...(!current && !hasLegacy && base.options_schema_version !== 2 ? { options_schema_version: 2, clip_skip_value_mode: "skip_count" } : {}) };
            delete intents.current[item];
            latest.current.options = next;
            latest.current.onChange(next);
          }
          return true;
        } catch (error) {
          if (!controller.signal.aborted) setErrors(previous => ({ ...previous, [item]: error }));
          return false;
        }
      })).then(results => {
        if (!controller.signal.aborted) {
          const ready = results.every(Boolean);
          setValid(ready); setAnalyzing(false); latest.current.onValidityChange?.(ready);
        }
      });
    }, 350);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [raw, primaryMode, fallbackMode, primaryContract, fallbackContract, path, operationRevision,readable]);
  const values = (options.values ?? {}) as Record<string, string | number>;
  const analysis = analyses[path];
  const roles = [...new Set(paths.flatMap(item => {
    const graph = workflowAt(options, item);
    return graph && "bindings" in graph ? Object.keys(graph.bindings) : analyses[item]?.used_roles ?? [];
  }))];
  const primary = workflowAt(options, "workflow");
  const referenceSupported = valid && Boolean(primary && ("bindings" in primary
    ? primary.bindings.reference : analyses.workflow?.reference_required));
  useEffect(() => { onReferenceSupportChange?.(referenceSupported); }, [referenceSupported, onReferenceSupportChange]);
  const supported = Object.values(analysis?.supported_tokens ?? analyses.workflow?.supported_tokens ?? {});
  function changeWorkflow(next: WorkflowInput) { onChange({ ...options, [path]: next }); }
  function changeMode(next: "placeholders" | "node_bindings") {
    if (!workflow || legacy) return;
    invalidatePending();
    const output = "output" in workflow ? workflow.output : { mode: "explicit_node" as const, node_id: workflow.output_node };
    changeWorkflow(next === "placeholders" ? { input_mode: next, prompt: workflow.prompt, output }
      : { input_mode: next, prompt: workflow.prompt, output, bindings: "bindings" in workflow ? workflow.bindings : {} });
  }
  function convertLegacy() {
    const next: Options = { ...options, options_schema_version: 2, clip_skip_value_mode: "node_value" };
    for (const item of paths) {
      const graph = workflowAt(options, item);
      if (graph && !("input_mode" in graph)) next[item] = { input_mode: "node_bindings", prompt: graph.prompt, bindings: graph.bindings, output: { mode: "explicit_node", node_id: graph.output_node } };
    }
    onChange(next);
  }
  function bind(role: string, nodeId: string, inputName: string) {
    if (!workflow || !("bindings" in workflow)) return;
    const bindings = { ...workflow.bindings }, nextValues = { ...values };
    if (!nodeId || !inputName) delete bindings[role];
    else {
      bindings[role] = { node_id: nodeId, input_name: inputName };
      const original = workflow.prompt[nodeId]?.inputs[inputName];
      if (!automatic.has(role) && nextValues[role] === undefined && (typeof original === "number" || typeof original === "string")) nextValues[role] = original;
    }
    const next = { ...workflow, bindings };
    onChange({ ...options, values: nextValues, [path]: "input_mode" in next ? next : { ...next, reference_required: Boolean(bindings.reference) } });
  }
  async function sample(kind: "text" | "reference") {
    const target=path,ticket=invalidatePending(path),abort=new AbortController();sampleController.current=abort;
    try {
      const graph=await getComfyApiSample(kind,abort.signal);
      if(abort.signal.aborted||ticket!==readRevision.current)return;
      intents.current[target]="replace";setRaw(previous=>({...previous,[target]:serializeComfyGraph(graph)}));setReadable(previous=>({...previous,[target]:true}));
    } catch (error) {if(!abort.signal.aborted&&ticket===readRevision.current){setErrors(previous=>({...previous,[target]:error}));setAnalyzing(false);}}
  }
  async function downloadSample(kind:"text"|"reference"){
    const abort=new AbortController();downloads.current.add(abort);setDownloadError(null);
    try{
      const graph=await getComfyApiSample(kind,abort.signal);if(abort.signal.aborted)return;
      const url=URL.createObjectURL(new Blob([serializeComfyGraph(graph)],{type:"application/json;charset=utf-8"}));urls.current.add(url);
      const anchor=document.createElement("a");anchor.href=url;anchor.download=`comfy-api-${kind}.json`;anchor.click();
      setTimeout(()=>{URL.revokeObjectURL(url);urls.current.delete(url);},0);
    }catch(error){if(!abort.signal.aborted)setDownloadError(error);}finally{downloads.current.delete(abort);}
  }
  const output = workflow && "output" in workflow ? workflow.output : undefined;
  function changeOutput(next: OutputPolicy) { if (workflow && "output" in workflow) changeWorkflow({ ...workflow, output: next } as VersionedWorkflow); }
  return <div className={styles.panel} aria-label={t("ComfyUI workflow 입력")}>
    <h4>{t("ComfyUI workflow 입력")}</h4>
    <label>{t("서버 주소")}<input disabled={disabled} value={String(options.base_url ?? "http://127.0.0.1:8188")} onChange={event => onChange({ ...options, base_url: event.target.value })} /></label>
    <p>{t("ComfyUI에서 내보낸 API JSON을 가져오거나, 선택 예시로 시작할 수 있어요.")}</p>
    <p>{t("파일을 가져오거나 예시를 사용하면 이 경로의 입력 연결과 출력 선택이 초기화돼요. 편집창 수정은 기존 설정을 유지해요.")}</p>
    <p className={styles.note}>{t("ComfyUI 서버의 기본 주소를 입력해 주세요. API 경로는 Angmoo가 붙입니다.")}</p>
    {Boolean(options.partner_auth)?<><p>{t("Comfy 계정 키는 지정한 ComfyUI 서버에 전달돼요. 신뢰할 수 있는 서버만 사용해 주세요.")}</p><p>{t("같은 기기의 ComfyUI는 127.0.0.1 또는 ::1 주소로 HTTP 연결할 수 있어요.")}</p><p>{t("Partner 인증으로 HTTP localhost에 연결할 때는 127.0.0.1을 사용해요. IPv6 전용 서버라면 [::1] 주소를 사용해 주세요.")}</p></>:null}
    <div className={styles.actions}>{paths.map(item => <Button key={item} type="button" variant="secondary" aria-pressed={path === item} onClick={() => {invalidatePending();setPath(item);setRaw(previous=>({...previous}));}}>{t(item === "workflow" ? "기본 workflow 입력" : "참조 없는 텍스트 경로 입력")}</Button>)}</div>
    <p>{t("참조가 없을 때 생성 제출 전에 사용할 텍스트 경로를 설정합니다. 생성 실패 후 자동 전환하지 않습니다.")}</p>
    <label>{t("API workflow 파일")}<input type="file" accept="application/json,.json" disabled={disabled} onChange={event => {
      const file = event.target.files?.[0], target = path;
      if (!file) return;
      event.target.value="";const ticket=invalidatePending(target);
      if (file.size > 2 * 1024 * 1024) { setErrors(previous => ({ ...previous, [target]: "워크플로 또는 응답이 지원 크기를 넘었습니다." }));setAnalyzing(false);return; }
      void file.text().then(source => {if(ticket===readRevision.current){intents.current[target]="replace";setRaw(previous=>({...previous,[target]:source}));setReadable(previous=>({...previous,[target]:true}));}}).catch(error => {if(ticket===readRevision.current){setErrors(previous=>({...previous,[target]:error}));setAnalyzing(false);}});
    }} /></label>
    <label htmlFor={`${id}-json`}>{t("불러온 API workflow JSON")}</label><textarea id={`${id}-json`} className={styles.jsonEditor} spellCheck={false} rows={10} disabled={disabled} value={raw[path]} onChange={event => { invalidatePending();delete intents.current[path];setReadable(previous=>({...previous,[path]:true}));setRaw(previous => ({ ...previous, [path]: event.target.value })); }} aria-invalid={Boolean(errors[path])} aria-describedby={errors[path] ? `${id}-json-error` : undefined} />
    {Boolean(errors[path]) ? <div id={`${id}-json-error`}><InlineError>{typeof errors[path]==="string"?t(errors[path] as string):comfyFailure(errors[path],t,t("JSON을 확인하지 못했습니다. 입력한 내용을 수정해 주세요."))}</InlineError></div> : null}
    <p role="status">{t(analyzing ? "JSON 분석 중…" : valid ? "JSON 분석 완료" : "JSON 입력을 확인해 주세요.")}</p>
    <div className={styles.actions}><Button type="button" variant="ghost" disabled={disabled} onClick={() => void sample("text")}>{t("텍스트 예시 사용")}</Button>{path === "workflow" ? <Button type="button" variant="ghost" disabled={disabled} onClick={() => void sample("reference")}>{t("참조 이미지 예시 사용")}</Button> : <Button type="button" variant="ghost" disabled={disabled} onClick={() => {invalidatePending();delete intents.current.text_workflow;const next={...options};delete next.text_workflow;onChange(next);setRaw(previous=>({...previous,text_workflow:""}));}}>{t("텍스트 경로 제거")}</Button>}</div>
    <p>{t("이 예시는 이미지와 텍스트를 함께 사용하며 ComfyUI의 ETN_LoadImageBase64 노드가 필요해요. Angmoo가 노드를 설치하지는 않아요.")}</p>
    <div className={styles.actions}><Button type="button" variant="ghost" disabled={disabled} onClick={()=>void downloadSample("text")}>{t("텍스트 예시 JSON 다운로드")}</Button><Button type="button" variant="ghost" disabled={disabled} onClick={()=>void downloadSample("reference")}>{t("참조 예시 JSON 다운로드")}</Button></div>
    {Boolean(downloadError)?<InlineError>{comfyFailure(downloadError,t,t("JSON을 확인하지 못했습니다. 입력한 내용을 수정해 주세요."))}</InlineError>:null}
    <p>{t("기존 노드 바인딩은 고급 설정에서 계속 사용할 수 있어요.")}</p>
    {legacy ? <><p>{t("기존 직접 입력 설정입니다. 입력한 값이 그대로 전달됩니다.")}</p><Button type="button" variant="secondary" disabled={!valid || disabled} onClick={convertLegacy}>{t("기존 설정을 새 형식으로 전환")}</Button></> : workflow ? <label>{t("입력 모드")}<select value={mode} disabled={disabled} onChange={event => changeMode(event.target.value as "placeholders" | "node_bindings")}><option value="placeholders">{t("자리표시자 입력")}</option><option value="node_bindings">{t("노드 입력 직접 지정")}</option></select></label> : null}
    <p className={styles.note}>{t("자리표시자는 Angmoo 설정값을 사용합니다. SillyTavern 설정은 자동으로 가져오지 않으며 JSON의 고정 값은 유지됩니다.")}</p>
    <p>{t("설치된 모델의 이름을 선택하거나 입력해 주세요.")}</p>
    {workflow && "bindings" in workflow ? <details open={legacy}><summary>{t("고급 입력 연결")}</summary>{supported.map(role => {
      const selected = workflow.bindings[role], node = selected ? workflow.prompt[selected.node_id] : undefined;
      return <div className={`${styles.row} ${styles.binding}`} key={role}><label>{role} · {t("입력 노드")}<select value={selected?.node_id ?? ""} disabled={disabled} onChange={event => { const nodeId = event.target.value; bind(role, nodeId, nodeId ? Object.keys(workflow.prompt[nodeId].inputs)[0] ?? "" : ""); }}><option value="">{t("연결 안 함")}</option>{Object.entries(workflow.prompt).map(([nodeId, item]) => <option key={nodeId} value={nodeId}>{nodeId} · {item.class_type}</option>)}</select></label>{selected && node ? <label>{t("입력 위치")}<select disabled={disabled} value={selected.input_name} onChange={event => bind(role, selected.node_id, event.target.value)}>{Object.keys(node.inputs).map(name => <option key={name}>{name}</option>)}</select></label> : null}</div>;
    })}</details> : null}
    {analysis ? <>
      <p>{t((workflow && "bindings" in workflow ? Boolean(workflow.bindings.positive) : analysis.prompt_applied) ? "생성할 때 프롬프트가 자동으로 전달됩니다." : "이 워크플로에는 Angmoo의 이미지 프롬프트가 적용되지 않습니다. JSON의 고정 프롬프트를 사용합니다.")}</p>
      <p>{t("감지한 자리표시자 위치: {{count}}개", { count: analysis.positions.length })}</p>
      <details><summary>{t("자리표시자 위치 보기")}</summary><ul className={styles.locations}>{analysis.positions.map((item, index) => <li key={index}>{item.token} · {item.node_id} · {JSON.stringify([item.input_name, ...item.path])}</li>)}</ul></details>
      {analysis.notices.length ? <p className={styles.note}>{t("Angmoo가 자동으로 채우지 않는 변수입니다. 필요한 경우 고정 값으로 바꿔 주세요.")}</p> : null}
    </> : null}
    <h4>{t("사용하는 입력")}</h4>
    <div className={styles.row}>{roles.map(role => {
      if (automatic.has(role)) return <p key={role}>{role} · {t("생성할 때 자동 공급")}</p>;
      const choices = [...new Set(paths.flatMap(item => {
        const graph = workflowAt(options, item);
        const locations = graph && "bindings" in graph && graph.bindings[role] ? [graph.bindings[role]] : analyses[item]?.positions.filter(position => position.role === role && position.path.length === 0) ?? [];
        return locations.flatMap(location => {
          const node = graph?.prompt[location.node_id];
          const fields = node ? connection?.object_info?.[node.class_type]?.input : undefined;
          const candidate = (fields?.required?.[location.input_name] ?? fields?.optional?.[location.input_name])?.[0];
          return Array.isArray(candidate) ? candidate.filter((value): value is string => typeof value === "string") : [];
        });
      }))];
      return <label key={role}>{role} · {t("값")}<input disabled={disabled} type={numeric.has(role) ? "number" : "text"} step={integers.has(role) ? 1 : "any"} list={choices.length ? `${id}-${role}` : undefined} value={values[role] ?? ""} onChange={event => { const next = { ...values }; if (!event.target.value) delete next[role]; else next[role] = numeric.has(role) ? Number(event.target.value) : event.target.value; onChange({ ...options, values: next }); }} />{choices.length ? <datalist id={`${id}-${role}`}>{choices.map(value => <option key={value} value={value} />)}</datalist> : null}</label>;
    })}</div>
    {roles.includes("seed") ? <p>{t("Seed -1은 접수할 때 한 번만 무작위로 정하고 같은 작업의 복구에도 유지합니다.")}</p> : null}
    {roles.includes("clip_skip") ? <><p>{t(legacy || options.clip_skip_value_mode === "node_value" ? "기존 직접 입력 설정입니다. 입력한 값이 그대로 전달됩니다." : "CLIP skip은 양수로 입력해 주세요. 1은 노드에 -1로 전달됩니다.")}</p>{!legacy ? <label>{t("CLIP skip 값 해석")}<select disabled={disabled} value={String(options.clip_skip_value_mode ?? "skip_count")} onChange={event => onChange({ ...options, clip_skip_value_mode: event.target.value })}><option value="skip_count">{t("양수 skip 수")}</option><option value="node_value">{t("노드 값 그대로")}</option></select></label> : null}</> : null}
    {roles.includes("reference") ? <p>{t(mode === "placeholders" ? "참조 이미지는 PNG Base64로 전달됩니다. 워크플로에서 이미지로 변환해 주세요." : "직접 입력 참조는 기존처럼 서버에 업로드한 파일명으로 전달됩니다.")}</p> : null}
    {output ? <><p>{t(output.mode === "auto_first_image" ? "첫 이미지 자동 선택" : "출력 노드 직접 지정")}</p><details><summary>{t("고급 출력 설정")}</summary><label>{t("이미지 출력")}<select disabled={disabled} value={output.mode} onChange={event => changeOutput(event.target.value === "auto_first_image" ? { mode: "auto_first_image" } : { mode: "explicit_node", node_id: Object.keys(workflow!.prompt)[0] })}><option value="auto_first_image">{t("첫 이미지 자동 선택")}</option><option value="explicit_node">{t("출력 노드 직접 지정")}</option></select></label>{output.mode === "explicit_node" ? <label>{t("이미지 출력 노드")}<select disabled={disabled} value={output.node_id} onChange={event => changeOutput({ ...output, node_id: event.target.value })}>{Object.entries(workflow!.prompt).map(([nodeId, item]) => <option key={nodeId} value={nodeId}>{nodeId} · {item.class_type}</option>)}</select></label> : null}</details></> : workflow && !("input_mode" in workflow) ? <label>{t("이미지 출력 노드")}<select disabled={disabled} value={workflow.output_node} onChange={event => changeWorkflow({ ...workflow, output_node: event.target.value })}>{Object.entries(workflow.prompt).map(([nodeId, item]) => <option key={nodeId} value={nodeId}>{nodeId} · {item.class_type}</option>)}</select><span>{t("기존 출력 노드의 이미지가 정확히 한 장이어야 합니다.")}</span></label> : null}
    <details open={advanced} onToggle={event => setAdvanced(event.currentTarget.open)}><summary>{t("연결 확인과 크기 제한")}</summary>
      {connection?.server_connection?.state === "connected" && connection?.input_readiness?.state === "ready" ? <p>{t("서버 연결과 입력 준비를 확인했습니다. 실행 가능 여부는 생성 요청 시 ComfyUI가 확인합니다.")}</p> : null}
      <p>{t(connection?.server_connection?.state === "connected" ? "서버 연결 확인됨" : "서버 연결 미확인")}</p>
      <p>{t(connection?.input_readiness?.state === "ready" ? "입력 준비 확인됨" : "입력 준비 미확인")}</p>
      <p>{t(connection?.candidate_lookup?.state === "available" ? "설정 후보를 불러왔습니다." : "설정 후보를 불러오지 못했습니다. 값을 직접 입력할 수 있습니다.")}</p>
      <p>{t("API JSON 2 MiB·256노드·64단계·100,000항목, 제출 본문 32 MiB까지 지원합니다.")}</p>
      <p>{t("PNG·JPEG·WebP, 12 MiB 이하, 최대 한 변 4,096픽셀, 단일 프레임 이미지를 받습니다.")}</p>
      <p>{t("전체 픽셀 수는 16,777,216 이하입니다. 참조 이미지의 제한은 10 MiB입니다.")}</p>
    </details>
  </div>;
}
