# P8-L-B Chat domain 구조 parity 증거

## 판정 범위

P8-L-B는 기존 Chat v1의 동작을 바꾸는 단계가 아니라, backend ownership을 `app.domains.chat`과 `app.runtime.chat`으로 이동하는 구조 전환이다. 이 단계만으로 World-scoped Chat v2, 계층형 기억, Retrieval Router, streaming 또는 새로운 schema가 구현되었다고 판정하지 않는다.

canonical ownership은 다음과 같다.

- domain contract·application orchestration: `app.domains.chat`
- SQLAlchemy·provider 실행: `app.runtime.chat`
- prompt safety policy: `app.core.prompt_safety`
- 기존 import compatibility: `app.models.messages`, `app.schemas.messages`, `app.services.messages`, `app.services.prompt_safety`

`app.domains.chat.domain`, `app.domains.chat.application`, `app.domains.chat.ports`는 FastAPI·SQLAlchemy·provider SDK와 legacy `models/schemas/services/runtime/integrations`를 직접 import하지 않는다. route는 `app.domains.chat.public`과 `app.runtime.chat.composition`을 통하여 동일한 v1 workflow를 호출한다.

## Frozen parity

P8-L-A의 `security/p8_l_a_inventory.json`은 수정하지 않는다. P8-L-B inventory는 그 파일의 normalized SHA-256을 predecessor로 고정하고 다음 parity를 별도로 증명한다.

- 기존 HTTP operation 11개 유지
- 기존 message table 4개와 table name 유지
- 기존 message migration 5개 유지
- Alembic 82개·head `20260825_0083` 유지
- Embedded SQLite manifest v3·87 tables·동일 schema digest 유지
- thread 한도, context 한도, message 길이, output token, default model, lease TTL 유지
- `RunLlmTracker(max_calls=1)`에 의한 attempt당 provider call 1회 유지
- P8-L-A에 기록된 legacy message exact edge 10개 제거
- legacy model/schema/service/prompt-safety import object identity 유지
- shared `ProfileRef`의 원래 여섯 field·required field·profile type과 community/Chat object identity 유지

따라서 이 단계에서 migration 추가, API path 변경, table rename, provider 호출 증가 또는 lease 의미 변경은 허용하지 않는다.

## Evidence와 확인 명령

정책과 generated evidence는 각각 다음 파일에 있다.

- `security/p8_l_b_chat_domain_policy.json`
- `security/p8_l_b_chat_domain_inventory.json`
- `scripts/ci/generate_p8_l_b_chat_domain_inventory.py`
- `backend/tests/test_p8_l_b_chat_domain_inventory.py`

repository root에서 다음을 실행한다.

```powershell
python scripts/ci/generate_architecture_inventory.py --check
python scripts/ci/generate_p8_l_b_chat_domain_inventory.py --check
backend\.venv\Scripts\python.exe -m pytest -q backend/tests/test_p8_l_b_chat_domain_inventory.py backend/tests/test_messages_service.py backend/tests/test_prompt_safety.py
```

PostgreSQL concurrency test environment가 연결되지 않은 실행에서는 concurrency parity를 `NOT VERIFIED`로 유지한다. SQLite 또는 import inventory PASS를 PostgreSQL advisory lock·lease concurrency의 실행 증거로 대체하지 않는다.
