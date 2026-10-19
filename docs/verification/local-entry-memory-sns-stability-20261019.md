# Local entry, memory and SNS stability — implementation evidence

Status: IN PROGRESS. Unchecked plan items and unexecuted validation are not PASS.

- Source plan: workspace `docs/plan/10-19 자동 사용자·세션·SNS 진입과 상황기억·근거·자율활동·설정 안정화 통합 코드 구현 세부 계획.md`, I00–I219 / V00–V130.
- Baseline: clean local main `268fd33f23eb264ae9f8d94362c29e7c419447fe`.
- Branch: `fix/local-entry-memory-sns-stability`.
- Authority: frontend ARCHITECTURE.md, DESIGN.md, frontend/static-shell AGENTS, backend ARCHITECTURE.md. UI provenance: LOCAL.
- Scope: local implementation, targeted validation and local commits only. No push, PR, remote CI, main merge, release, candidate replacement, Docker restart or installed-app changes.
- Preserve: initial Device Home app list, existing names/data/keys, fixed ARM64 candidates and previous observation evidence.
- New defaults only: Korean `사용자`; other languages `User` for both account and World profile. No historical rename or display substitution.
- Tests use isolated files/SQLite, synthetic inputs and fake providers. Real AI quality and installed/native/ARM64 results are reported independently.

## Execution record

| Plan items | Status | Evidence |
| --- | --- | --- |
| I01–I04 | DONE | Clean main verified; new branch created; original plan takes precedence; protected runtime data excluded. |
| I00, I05–I219 | IN PROGRESS | Owner-boundary investigation, implementation and validation follow below. |

## Verification

- Proxy lifecycle unit harness: PASS (`node scripts/test-proxy-lifecycle.mjs`).
- Actual isolated Next + fake upstream: PASS (`node scripts/test-proxy-disconnect.mjs`), header/stream/upload cancellation, POST single dispatch, broken NDJSON and upstream 502.
- Existing package proxy security regression: PASS (`node scripts/test-world-package-proxy.mjs`, isolated dist).
- Proxy changed-file ESLint: PASS. TypeScript check: PASS through initial Identity/editor changes; final integration rerun pending.
- Local entry controller harness: PASS (fresh single-flight, expiry, persistent stop, response loss, late issuance, storage rejection, runtime replacement).
- Identity service tests: initial 9 pass / 1 migration contract failure. Migration fixed to canonical table DDL; focused migration test then PASS.
- Identity HTTP protocol/cookie/origin test: PASS (1 test). Full related identity regression is in progress; old tests require the new explicit protocol DTO.
- No live AI, candidate Docker, installed native/Tauri or ARM64 runtime verification has been run.
