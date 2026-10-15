"use client";

import { useUiText } from "@/hooks/use-ui-text";
import type { ProviderDiagnostic } from "../types/media";

export function ProviderDiagnosticDetails({ value }: { value: ProviderDiagnostic }) {
  const uiText = useUiText("media");
  const comfy = !value.provider || value.provider === "comfyui";
  const title = comfy
    ? (value.kind === "warning" ? "ComfyUI 실행 안내" : "ComfyUI 오류 정보")
    : value.provider === "openrouter" ? "OpenRouter 요청 정보" : "NanoGPT 요청 정보";
  return <details>
    <summary>{uiText(title)}</summary>
    {value.messages.length ? <ul>{value.messages.map((message, index) => <li key={index}>{[message.node_id, message.class_type, message.input_name, message.type, message.exception_type, message.message, message.exception_message].filter(Boolean).join(" · ")}</li>)}</ul> : null}
    {value.transport ? <dl>
      <dt>{uiText("오류 분류")}</dt><dd>{value.transport.category}</dd>
      <dt>{uiText("마지막 확인 단계")}</dt><dd>{value.transport.observed_phase}</dd>
      <dt>{uiText("요청 경과 시간")}</dt><dd>{value.transport.elapsed_ms} ms</dd>
      {value.transport.status ? <><dt>HTTP</dt><dd>{value.transport.status}</dd></> : null}
      {value.transport.provider_code ? <><dt>{uiText("제공자 오류 코드")}</dt><dd>{value.transport.provider_code}</dd></> : null}
      {value.transport.request_id ? <><dt>{uiText("요청 식별자")}</dt><dd>{value.transport.request_id}</dd></> : null}
      <dt>{uiText("진단 수집 상태")}</dt><dd>{value.transport.completeness}</dd>
    </dl> : null}
    {value.truncated ? <p>{uiText("오류 정보 일부가 생략되었습니다.")}</p> : null}
    <p>{uiText(comfy ? "자세한 실행 로그는 ComfyUI에서 확인할 수 있습니다." : "이 정보만으로 제공자의 처리 완료 여부를 확인할 수는 없어요.")}</p>
  </details>;
}
