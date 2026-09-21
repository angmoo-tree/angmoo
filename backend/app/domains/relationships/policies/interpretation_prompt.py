"""Small shared output contract, never an extra relationship model call."""

from copy import deepcopy

METRIC_INSTRUCTIONS = """
관계 지표 부가 판단: 이번에 실제로 접한 상대의 말·행동을 자신의 페르소나,
기존 관계, 제공된 기억과 최근 맥락으로 어떻게 받아들였는지 판단하세요.
호감(affinity), 신뢰(trust), 긴장(tension)을 각각 increase/keep/decrease로 표현하세요.
단순 인사, 확인, 반복, 근거 부족은 keep입니다. 신뢰 변화에는 믿을 만함의 구체적 새 근거가 필요합니다.
자신의 답글 목적, 아직 실행하지 않은 행동, 상대의 숨겨진 의도는 변화 근거가 아닙니다.
이전에 이미 판단한 사건을 최근 맥락에서 다시 보았다고 새 변화로 세지 마세요.
정확한 수치, 친숙도, 관계 유형, 인식 문구는 여기서 작성하지 마세요.
관계 변화가 있는 상대만 relationship_metrics에 반환하며 없으면 []입니다.
대상과 new_evidence_refs는 입력에 제공한 참조만 사용하세요. 사용자에게 이 부가 결과를 보여주지 마세요.
"""


def with_metric_schema(schema: dict) -> dict:
    result = deepcopy(schema)
    result.setdefault("properties", {})["relationship_metrics"] = {
        "type": "array", "items": {"type": "object", "properties": {
            "target_ref": {"type": "string"},
            **{axis: {"type": "string", "enum": ["increase", "keep", "decrease"]}
               for axis in ("affinity", "trust", "tension")},
            "new_evidence_refs": {"type": "array", "items": {"type": "string"}},
        }, "required": ["target_ref", "affinity", "trust", "tension", "new_evidence_refs"]}}
    result["required"] = [*result.get("required", []), "relationship_metrics"]
    return result
