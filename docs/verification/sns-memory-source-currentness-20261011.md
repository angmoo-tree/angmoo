# SNS 기억 출처 재검증 오탐 수정 및 로컬 검증

작성일: 2026-10-11 (Asia/Seoul)
저장소: D:/project_code/angmoo-workspace/angmoo-tree-angmoo
브랜치: feat/0.1.0-release-readiness
시작 HEAD: a65c66f733684637d877752e45c7b896abf770fa
시작 작업 트리: clean.
범위: 현재 로컬 브랜치 수정 및 로컬 커밋. PR 생성, push, CI 수행, main 병합 없음.

## 원인과 수정

Chat 참가자·원문 작성자 연결 커밋 `f4a64077`에서 공통 `EpisodePacketSource`
내부 계약에 `author_id`가 추가됐다. `bounded_episode_packets`는 이 비공개 값을
제외한 기존 `episode-packet.v1` 자료를 만들지만, SNS snapshot guard는 해당 자료를
`asdict(source)`와 비교했다. 작성자 값이 null이어도 키의 유무 때문에 같지 않다.
따라서 원문과 권한이 그대로인 기억도 `activity_memory_source_changed`로 거부됐다.

Memory 소유의 순수 정책 `episode_source_payload`가 전달 출처의 6개 필드를 명시한다:
`reference`, `role`, `text`, `status`, `start_offset`, `end_offset`.
기억 입력 생성과 SNS snapshot guard가 이 동일한 projection을 사용한다.
기존 모델 입력의 필드·값·순서 및 예산 계산은 보존하고 내부 작성자 값은 계속 제외한다.
검사 예외, 무조건 성공 처리, 클라이언트의 관찰 flag, 원본 자료 재작성은 추가하지 않았다.

출처의 현재 canonical 접근 검사, digest/status, 원문·역할·범위, 생각, 요약·버전,
후속 기억 연결, scope/policy/snapshot 검사는 유지한다. 전달 자료 전체를 엄격히 비교하므로
예상 밖 `author_id`를 전달 자료에 삽입해도 거부한다. 내부 작성자 조회 및 Chat 이름 연결은
그대로 유지한다. DB migration, 색인 재준비, 새 SQL/AI/임베딩 호출은 필요하지 않다.

변경 파일은 Memory 정책, SNS Runtime guard, 해당 Runtime 회귀 검사, backend
ARCHITECTURE와 이 검증 문서다. Runtime이 Memory의 중립 값·순수 정책을 소비하는 기존
아키텍처 방향을 유지한다. frontend/UI 및 사용자 설정은 이번 수정 대상이 아니다.

## 재현 및 자동 회귀

수정 전 기존 `tests/runtime/test_activity_memory_revalidation.py`는 **3 failed, 2 passed**였다.
모두 snapshot을 사용하는 정상 자료에서 `revalidation.py:87`의 같은 오류로 실패했다.
새 정상 자료 회귀 4개도 수정 전에는 **2 failed, 2 passed**였고, 실패 항목은 snapshot
사용 시 작성자 None/검증된 작성자 두 경우다. snapshot 없는 기존 경로는 정상 통과했다.

수정 후 최종 직접 관련 matrix는 **58 passed, 1 deselected**, 106.24초다.
선택 해제한 항목은 이번 수정과 무관한 과거 Git baseline 기반 Chat 비용 benchmark다.
이전 단계의 부분 matrix 36 passed/1 skipped와 중복되므로 합산하지 않는다.

격리 회귀는 다음을 확인했다.

- 작성자 None/검증된 작성자와 snapshot 사용/구 경로에서 정상 SNS 기억 통과.
- 현재 원문 변경, 출처 digest 변경, 차단, 출처 없음은 계속 거부.
- 전달 자료의 참조·역할·본문·상태·시작/끝 범위 변조와 비공개 작성자 필드 삽입 거부.
- 기존 후속 연결·요약 변경, scope/policy 손상, 서로 다른 SNS 예산 회귀 통과.
- 기억 원문 저장소·hydration·Social 출처/권한·상황기억 proof와 Chat 작성자 연결 회귀 통과.

Docker 내부에서도 동일 Runtime 파일의 **20 passed**, 9.38초를 확인했다.
app UID/GID 10001:10001, `ANGMOO_DENY_EXTERNAL_NETWORK=1`로 실행했으며 SQLite fixture는
격리 시험 자료다. 실제 API 키 및 AI·임베딩을 사용하는 시험 호출은 없다.

## 실제 Docker 자료 읽기 전용 확인

실제 선택된 canonical generation marker를 읽고 SQLite를 `mode=ro`,
`PRAGMA query_only=ON`, 독립 `NullPool`로 열었다. 현재 Runtime의 canonical reader,
follow-up snapshot, provider reference, SNS packet 및 `assert_memories_current`를 사용했다.
앱 생성·migration·원본 DB 쓰기·제공사 요청은 실행하지 않았다. 키·대화 원문도 출력하지 않았다.

| 대상 | 입력 기준 | seed/hydrated | 전달 packet/source 수 | 결과 |
| --- | --- | --- | --- | --- |
| Red | 관찰 세션 첫 실패 활동의 실제 기억 ID 6개 | 6/6 | 2/2 | 통과 |
| Elias Finch | 현재 공개 기억 6개 | 6/6 | 2/4 | 통과 |
| Bram | 현재 공개 기억 6개 | 6/6 | 3/3 | 통과 |

Red의 원래 실패 활동은 `08a19bed-b824-4f8f-90ff-7c82b2c08985`,
관찰 session은 `sns-aa9aece237284232af90005af473753f`다. 이 확인은 그 ID 묶음을
현재 canonical 상태에서 다시 읽은 것이며 과거 checkpoint 전체나 AI 활동을 재실행한 것은 아니다.
세 대상 모두 전달 자료에 `author_id`가 없음을 확인했다.

Compose Watch의 기존 자동 반영으로 수정 후 서버 startup 완료를 확인했고, 변경한 제품
Python 파일 2개의 로컬/Docker SHA256이 일치한다.

- `revalidation.py`: `e4ada809566a3eb36db5e3657cedacb66981593bb390f79a4e6a8b134097641b`
- `episode_packets.py`: `c71f9620edcefc7b5a7601441bd7b889ab22b248e9e87918327c083deb71a027`

마지막 runtime 확인에서 backend/frontend는 모두 running/healthy다. 수동 Docker
재시작·재빌드, 자율활동 강제 실행, 원본 설정·기억·실패 기록 수정은 하지 않았다.
컨테이너 상태는 서버 가용성 확인이며 실제 AI 행동 품질 판정과 구분한다.

## 트레이드오프와 남은 관찰 범위

필드 6개를 고정한 작은 projection을 재사용하므로 추가 DB/제공사 작업은 없다.
추후 전달 계약에 필드를 추가하면 이 정책과 소비자 회귀를 함께 갱신해야 한다.
그 명시적 변경 부담으로 내부 필드의 우발적 노출과 비교 형식 불일치를 방지한다.

이번에 확인한 것은 오류 재현, 오탐 해소, 실제 변경·권한 손상의 거부와 Docker 현재 자료
재검증이다. 수정 후 새로운 4시간 자연 활동 관찰 또는 실제 AI 답변·이미지 품질 시험은
수행하지 않았다. 과거 관찰 세션의 실패 결과와 recorder completeness는 변경하지 않는다.

## 재현 명령

저장소 backend 디렉터리의 로컬 Python:

```powershell
$env:ANGMOO_DENY_EXTERNAL_NETWORK='1'
& '.venv/Scripts/python.exe' -m pytest tests/runtime/test_activity_memory_revalidation.py tests/memory/test_episode_packets.py tests/memory/test_episode_packet_repository.py tests/memory/test_episode_hybrid_reader.py tests/memory/test_episode_social_sources.py tests/memory/test_situation_proof_guards.py tests/chat/test_chat_identity_sources_costs.py -k 'not bounded_input_and_relationship_read_costs' -q -p no:cacheprovider --tb=short
```

Docker에서 격리 Runtime 회귀:

```powershell
docker exec -u 10001:10001 -e ANGMOO_DENY_EXTERNAL_NETWORK=1 -e PYTHONDONTWRITEBYTECODE=1 -w /workspace/backend angmoo-backend-1 /workspace/backend/.venv/bin/python -B -m pytest tests/runtime/test_activity_memory_revalidation.py -q -p no:cacheprovider --tb=short
```
