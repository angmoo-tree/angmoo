import { ApiRequestError } from "@/lib/http/error-contract";
import type { UiText } from "@/hooks/use-ui-text";

const messages: Record<string, string> = {
  comfy_json_invalid: "JSON을 확인하지 못했습니다. 입력한 내용을 수정해 주세요.",
  comfy_json_duplicate_key: "JSON에 중복된 키가 있습니다. 같은 이름의 키를 하나만 남겨 주세요.",
  comfy_api_graph_required: "ComfyUI에서 API 형식으로 내보낸 JSON을 가져와 주세요.",
  comfy_workflow_required: "API workflow JSON을 입력해 주세요.",
  comfy_workflow_size_invalid: "워크플로 또는 응답이 지원 크기를 넘었습니다.",
  comfy_payload_too_large: "워크플로 또는 응답이 지원 크기를 넘었습니다.",
  comfy_json_complexity_exceeded: "워크플로의 중첩이나 항목 수가 지원 범위를 넘었습니다.",
  comfy_value_required: "워크플로에서 사용하는 입력값을 채워 주세요.",
  comfy_value_invalid: "숫자 입력은 유한한 숫자여야 합니다. 정수 입력에는 정수를 사용해 주세요.",
  comfy_clip_skip_count_invalid: "CLIP skip은 양수로 입력해 주세요. 1은 노드에 -1로 전달됩니다.",
  comfy_binding_missing: "직접 지정한 노드와 입력 위치를 확인해 주세요.",
  comfy_bindings_invalid: "직접 지정한 노드와 입력 위치를 확인해 주세요.",
  comfy_binding_collision: "같은 노드 입력에 여러 역할을 지정할 수 없습니다.",
  comfy_output_invalid: "직접 지정한 출력 노드가 JSON에 없습니다.",
  comfy_reference_or_text_path_required: "참조 이미지를 설정하거나 참조 없는 워크플로를 추가해 주세요.",
  comfy_text_workflow_requires_reference: "텍스트 경로에는 참조 이미지를 요구하는 입력을 넣을 수 없습니다.",
  comfy_url_invalid: "ComfyUI 서버의 기본 주소를 확인해 주세요. 사용자 정보·쿼리·fragment는 사용할 수 없습니다.",
  comfy_connection_invalid: "ComfyUI 서버 연결을 확인하지 못했습니다.",
  comfy_partner_key_required: "Partner 인증을 사용하려면 별도의 Comfy 계정 API 키를 저장해 주세요.",
  comfy_prompt_rejected: "ComfyUI가 작업을 접수하지 못했습니다.",
  comfy_prompt_response_invalid: "접수 결과를 확인해야 합니다. 같은 작업을 다시 제출하지 않습니다.",
  comfy_execution_failed: "ComfyUI에서 작업 실행에 실패했습니다.",
  comfy_no_image_output: "작업을 마쳤지만 이미지 출력이 없습니다. 이미지 출력 노드를 확인해 주세요.",
  comfy_selected_output_missing: "지정한 노드에 이미지 결과가 없습니다.",
  comfy_output_shape_invalid: "첫 이미지 결과의 파일 정보를 확인하지 못했습니다. 다른 결과로 바꾸지 않습니다.",
  generated_media_invalid: "첫 이미지 결과의 형식이나 크기를 확인하지 못했습니다. 다른 결과로 바꾸지 않습니다.",
  provider_http_401: "ComfyUI 서버 인증 키를 확인해 주세요.",
  provider_http_403: "ComfyUI 서버 접속 권한을 확인해 주세요.",
  reference_pixels_invalid: "참조 이미지의 형식이나 크기를 확인해 주세요.",
  generation_reference_changed: "참조 이미지의 권한이나 버전이 바뀌었습니다. 설정을 다시 확인해 주세요.",
};
export function comfyReason(code: string | null, text: UiText): string | null {
  return code && messages[code] ? text(messages[code]) : null;
}
export function comfyFailure(error: unknown, text: UiText, fallback: string): string {
  return error instanceof ApiRequestError ? comfyReason(error.code, text) ?? fallback : fallback;
}
