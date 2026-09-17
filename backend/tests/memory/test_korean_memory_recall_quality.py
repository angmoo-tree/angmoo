"""Frozen synthetic lexical evaluation; split by experience, never user data."""
from dataclasses import replace
import json
import os
from pathlib import Path
from time import perf_counter

import pytest

from app.domains.memory.contracts.recall import (
    MemoryRecallDocument, MemoryRecallSearchQuery, RecallDocumentKind,
)
from app.domains.memory.contracts.scope import MemoryScope
from app.runtime.memory.sqlite_fts5_recall import SqliteMemoryRecallIndex
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath

SCOPE = MemoryScope("quality-owner", "quality-world", "quality-subject")
# Each experience has exact, spacing, multi-space, distractor and absent queries.
# The last four experiences are held out from tuning.
EXPERIENCES = (
    ("체력 훈련 중 지구력 데이터와 심박수 회복 지점을 분석함", "지구력 심박수", "체력훈련 지구력 심박수", "심박수 체온"),
    ("수영 연습에서 호흡 간격과 잠수 시간을 기록함", "호흡 잠수", "수영연습 호흡 잠수", "잠수 수온"),
    ("암벽 등반에서 손가락 압력과 발판 위치를 점검함", "손가락 발판", "암벽등반 손가락 발판", "발판 풍속"),
    ("비행 훈련에서 날개 각도와 상승 고도를 측정함", "날개 상승", "비행훈련 날개 상승", "상승 연료"),
    ("구조 실습에서 밧줄 매듭과 고정 지점을 확인함", "밧줄 매듭", "구조실습 밧줄 매듭", "매듭 도르래"),
    ("요리 수업에서 반죽 온도와 발효 시간을 비교함", "반죽 발효", "요리수업 반죽 발효", "발효 소금"),
    ("악기 연습에서 손목 각도와 박자 변화를 관찰함", "손목 박자", "악기연습 손목 박자", "박자 음정"),
    ("정원 관리에서 토양 수분과 뿌리 길이를 측정함", "토양 뿌리", "정원관리 토양 뿌리", "뿌리 비료"),
    ("항해 실습에서 조류 방향과 닻줄 장력을 기록함", "조류 닻줄", "항해실습 조류 닻줄", "닻줄 해무"),
    ("도자 작업에서 유약 농도와 가마 온도를 조절함", "유약 가마", "도자작업 유약 가마", "가마 도안"),
    ("응급 훈련에서 붕대 압력과 맥박 회복을 확인함", "붕대 맥박", "응급훈련 붕대 맥박", "맥박 산소"),
    ("천체 관측에서 렌즈 초점과 별자리 위치를 기록함", "렌즈 별자리", "천체관측 렌즈 별자리", "별자리 은하"),
)


def document(identifier, text, **kwargs):
    return MemoryRecallDocument(
        document_id=identifier, memory_item_id=identifier,
        owner_id=SCOPE.owner_id, world_id=SCOPE.world_id,
        subject_world_character_id=SCOPE.subject_world_character_id,
        kind=RecallDocumentKind.MEMORY_ITEM, canonical_source_id=identifier,
        text=text, **kwargs,
    )


def build_index(path, documents):
    index = SqliteMemoryRecallIndex(StaticRuntimeDataPath(path))
    index.rebuild(documents)
    return index


def cases():
    for n, (_, exact, spacing, negative) in enumerate(EXPERIENCES):
        for label, query, expected in (
            ("exact", exact, [f"memory-{n}"]),
            ("spacing", spacing, [f"memory-{n}"]),
            ("whitespace", exact.replace(" ", " \t  "), [f"memory-{n}"]),
            ("missing_concept", negative, []),
            ("extra_word", spacing + " 우주선", []),
        ):
            yield {"split": "tune" if n < 8 else "holdout", "id": f"{n}-{label}",
                   "query": query, "expected": expected, "label": label}


def test_frozen_quality_comparison(tmp_path):
    docs = [document(f"memory-{n}", row[0]) for n, row in enumerate(EXPERIENCES)]
    # Plausible wrong records contain only one of the required concepts.
    docs += [document(f"distractor-{n}", row[1].split()[0] + " 일반 조언을 읽음")
             for n, row in enumerate(EXPERIENCES)]
    index = build_index(tmp_path, docs)
    variant = os.environ.get("MEMORY_QUALITY_VARIANT", "B1")
    results = []
    try:
        for case in cases():
            query = MemoryRecallSearchQuery(SCOPE, case["query"], (RecallDocumentKind.MEMORY_ITEM,), 5)
            if variant == "B1":
                query = replace(query, korean_spacing_fallback=True)
            start = perf_counter()
            found = [row.memory_item_id for row in index.search(query)][:5]
            results.append({**case, "found": found, "elapsed_ms": (perf_counter()-start)*1000})
            expected = [] if variant == "B0" and case["label"] == "spacing" else case["expected"]
            assert found == expected, case
    finally:
        index.close()
        if output := os.environ.get("MEMORY_QUALITY_OUTPUT"):
            Path(output).write_text(json.dumps({"variant": variant, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
