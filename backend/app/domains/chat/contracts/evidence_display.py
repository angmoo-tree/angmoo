"""Private, text-bound display labels. Never included in model input or its hash."""
from __future__ import annotations

from hashlib import sha256

LABELS = {
    "kind": "오늘 SNS 활동 종류: ", "action": "실제 행동: ", "actor": "행동 주체: ",
    "counterpart": "상대: ", "truncated": "원문 일부만 포함됨: 전문이나 전체 대화로 주장하지 말 것",
    "root_title": "대화 시작 글 제목: ", "root_body": "대화 시작 글 일부: ",
    "parent_title": "직접 연결된 이전 글 제목: ", "parent_body": "직접 연결된 이전 글: ",
    "title": "제목: ", "body": "내용: ", "thought": "이 활동에 연결된 생각(자기 관점·행동 이유): ",
    "thought_truncated": "생각은 앞 280자만 저장됨: 생략된 이유나 감정을 만들어내지 말 것",
    "thought_status": "생각 기록 상태: ", "thought_unrecorded": "; 행동 이유를 기록된 사실로 단정하지 말 것",
    "motivation": "행동 결정 시 직접 선언한 동기: ", "emotion": "행동 결정 시 직접 선언한 감정: ",
    "intensity": "강도 ",
}
REVISION = "evidence-display.v1"


def bounded_segments(parts: list[tuple[str | None, str]], limit: int) -> list[dict]:
    # Normalize the same Unicode whitespace as frozen model prose, retaining
    # provenance per character. Partial labels are literals, never translated.
    chars: list[tuple[str | None, str]] = []
    pending = None
    for key, text in parts:
        for char in text:
            if char.isspace():
                if chars and pending is None:
                    pending = (key, " ")
            else:
                if pending is not None:
                    chars.append(pending)
                    pending = None
                chars.append((key, char))
    chars = chars[:limit]
    while chars and chars[-1][1].isspace():
        chars.pop()
    output: list[dict] = []
    for key, char in chars:
        if output and output[-1]["key"] == key:
            output[-1]["text"] += char
        else:
            output.append({"key": key, "text": char})
    for segment in output:
        if segment["key"] is not None and segment["text"] != LABELS[segment["key"]]:
            segment["key"] = None
    return output


def projection(reference: str, segments: list[dict]) -> dict:
    text = "".join(s["text"] for s in segments)
    return {"revision": REVISION, "ref": reference, "text_digest": sha256(text.encode()).hexdigest(), "segments": segments}


def validate_projection(value: object, reference: str, text: str) -> list[dict]:
    if not isinstance(value, dict) or set(value) != {"revision", "ref", "text_digest", "segments"}:
        raise ValueError("evidence_display_invalid")
    segments = value["segments"]
    if (value["revision"] != REVISION or value["ref"] != reference
        or value["text_digest"] != sha256(text.encode()).hexdigest()
        or not isinstance(segments, list) or not 1 <= len(segments) <= 128):
        raise ValueError("evidence_display_invalid")
    for segment in segments:
        if (not isinstance(segment, dict) or set(segment) != {"key", "text"}
            or not isinstance(segment["text"], str) or not segment["text"] or len(segment["text"]) > 2000
            or (segment["key"] is not None and (not isinstance(segment["key"], str)
                or segment["key"] not in LABELS or LABELS[segment["key"]] != segment["text"]))):
            raise ValueError("evidence_display_invalid")
    if "".join(s["text"] for s in segments) != text or len(text) > 2000:
        raise ValueError("evidence_display_invalid")
    return segments


def excerpt_segments(value: object, reference: str, text: str, limit: int = 500) -> list[dict]:
    parts = validate_projection(value, reference, text)
    # Do not renormalize the excerpt: keep exactly text[:500], including a
    # possible trailing space. Python cuts codepoints, no JS offsets are used.
    result, remaining = [], limit
    for part in parts:
        if remaining <= 0:
            break
        excerpt = part["text"][:remaining]
        result.append({"key": part["key"] if excerpt == part["text"] else None, "text": excerpt})
        remaining -= len(excerpt)
    return result
