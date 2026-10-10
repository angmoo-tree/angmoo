# Creator Studio 안내·사진 처리·scheduler 복구 구현과 검증 기록 — 2026-10-10

대상은 workspace의 `10-10 Creator Studio 안내·상태 문구 최신화와 내부 용어 노출 정리 코드 구현 세부 계획.md` I00–I60이다.
기준 브랜치는 `feat/0.1.0-release-readiness`, 기준 HEAD는 `0c5eaab04d5067d284ac91b1565d9021ebf9afec`이고 시작 작업 트리는 깨끗했다.
I00–I60의 구현·관련 검증·변경 범위 검토를 완료했다. 이 기록과 관련 코드만 지정 브랜치의 Signed-off-by 로컬 커밋에 포함한다.
최종 SHA와 커밋 이후 clean 상태는 workspace 계획의 실행 결과 및 사용자 보고에 남긴다.
구현 커밋은 `f340963c`이며 110개 관련 파일만 포함했다. 이 기록의 최종 판독 보완도 같은 브랜치의 별도 로컬 커밋으로 보존한다.
PR·push·CI 워크플로·main 전환/머지·실제 AI 호출·원본 사용자 데이터 쓰기는 하지 않았다.

## 변경과 보존

- Studio 목록은 Creator Studio, World 편집/신규·공개 준비·draft 미리보기는 Worlds, 가져오기/내보내기는 World Packages가 소유한다.
  기본 화면의 P1/P2·quality tier·hash·row version·transaction·원시 enum을 사용자 안내로 바꿨다.
  사용자 본문과 고급 JSON을 필터링하지 않았고, 선택 설정 개수와 기존 필수/선택·저장·공개·권한·digest 승인 조건을 유지했다.
- 아이콘/배너는 실제 Home/소개 표시를 공유한다. 이름·소개·태그는 draft의 있는 항목만 표시하고, 모두 비면 배너만 표시한다.
  공용 중립 자르기는 선택→조절→적용 때만 World의 기존 revision-aware 저장을 호출한다.
  아이콘 768×768, 배너 1024×384, WebP 0.8/실제 MIME·5MiB 상한과 취소/실패의 이전 이미지·draft를 검증했다.
  기존 프로필도 같은 표시·계산을 쓰되 DTO·callback·권한·저장 수명은 원래 feature에 남겼다.
- 생성 마지막 단계의 카드 안 ON/OFF만 제외하고 아래에 완료→자율활동을 켜고 완료→건너뛰기를 배치했다.
  기존 capability/설정 controller를 안정된 React 컴포넌트 슬롯으로 전달한다. 명시 ON은 기존 요청 1회, 이미 ON이면 추가 ON 0회다.
  키 없음/거절/충돌이면 등록 결과·설정을 보존하며, 일반 완료/건너뛰기는 전체 저장이나 활성화를 하지 않는다.
- Home은 Angmoo Quicksand 700·1.35rem·코랄색으로 표시한다. 원문 OFL/정확한 자산 digest·로컬 번들·시스템 fallback을 등록했다.
  `/settings`·`/agents/new`만 AppShell의 명시적 navigation 옵션으로 제외했다. 숨겨진 기존 종료 Dialog footer는 탐색 footer가 아니다.
  Character-directory와 embedded Relationship만 중립 SectionHeading을 공유한다. 제목 역할/아이콘/내용과 standalone 관계 화면은 보존했다.
- 게시글/Chat 사용자 사진은 Media의 하나의 정책으로 원본 20MiB, 최종 10MiB·4096px·16,777,216px, 요청 14MiB를 적용한다.
  필요할 때만 로컬 Worker/실제 HEIF WASM으로 변환한다. 입력 16,384px·64MP, 동시 1개·30초·6회 인코딩·native codec allocation 512MiB를 제한한다.
  이 512MiB는 codec의 안전 제한이며 브라우저 전체 RSS나 WASM heap 전체가 512MiB라는 주장이 아니다.
  원본·이전 첨부·본문, auth/runtime/World/thread 수명, Chat의 실제 asset preflight/인식 허용·전송·분석/재시도 책임을 유지했다.
  다른 이미지 입력은 이전 정책을 유지한다. 서버의 실제 MIME·최종 byte/pixel·정규화 검증도 유지했다.
- World 사진은 원래 파일 5MiB와 요청 8,262,144 bytes를 유지한다. icon/banner/my-profile/media/world-characters/{id}/profile/media의
  정확한 POST에만 Next/ASGI 예외를 적용했고, 일반 1MiB·다른 method/유사 경로·auth/CSRF는 유지했다.
- scheduler는 주입된 실제 SQLite engine에서 기존 lease adapter를 선택한다. 짧은 BEGIN IMMEDIATE와 fresh owner/epoch/expiry CAS를 사용한다.
  SQLITE_BUSY 계열만 최대 4회·250ms 총 예산·50ms 개별 대기 안에서 재시도하고 원래 busy_timeout을 복원한다.
  canonical pool checkout도 50ms로 제한한다. 경합이 심할 때 빨리 실패할 수 있는 비용을 동시성 문서에 기록했다.
  worker 1·capacity 4·queued deadline 1초의 큐는 실행 중 Future와 Session 소유 스레드를 실제 종료 때까지 추적한다.
  같은 recovery owner가 DEGRADED에서 이전 작업 drain→유효 heartbeat/새 epoch 확인→READY로 복구한다.
  tick 완료 효과/장부를 재생하지 않으며, 살아 있는 자식 task가 있으면 finish/release/restart로 종료를 가장하지 않는다.
  최초 실패와 cleanup 실패를 구분하고, scheduler health는 상태 registry와 살아 있는 lease proof를 함께 요구한다.
  별도 supervisor 재시작·DB schema 변경·AI 정책 변경·당시 잠금 소유 작업을 Chat으로 단정하는 조치는 없다.

## I00–I60 완료 근거

| 단계 | 계획의 작업 | 상태 | 근거 |
|---|---|---|---|
| I00 | 지정 브랜치·HEAD·dirty·병행 작업 확인 | 완료 | 현재 브랜치/깨끗한 기준 HEAD와 구조 문서·보존 경계 대조 |
| I01 | frontend/backend 구조·디자인·AGENTS와 Next 관련 로컬 가이드 확인 | 완료 | 현재 브랜치/깨끗한 기준 HEAD와 구조 문서·보존 경계 대조 |
| I02 | Studio·World 편집/신규·World 가져오기·캐릭터 생성·홈·설정·관계 header·게시글/Chat·World 프로필 사진·scheduler SQLite 복구의 변경 목록 작성 | 완료 | 현재 브랜치/깨끗한 기준 HEAD와 구조 문서·보존 경계 대조 |
| I03 | 필수·선택·저장·공개·환경·권한·패키지·미리보기·캐릭터 ON·사진 한도/자원·scheduler 권한/복구 조건 대조 | 완료 | 현재 브랜치/깨끗한 기준 HEAD와 구조 문서·보존 경계 대조 |
| I04 | Studio 상단·빈 상태·연결 안내 교체 | 완료 | Studio/Worlds/Packages의 표시 소유권, ko/en 문구·enum·준비/오류·원문 경계 |
| I05 | 목록 그룹·원시 enum 표시 수정 | 완료 | Studio/Worlds/Packages의 표시 소유권, ko/en 문구·enum·준비/오류·원문 경계 |
| I06 | World 편집 머리말·제목·종료된 주제 안내 수정 | 완료 | Studio/Worlds/Packages의 표시 소유권, ko/en 문구·enum·준비/오류·원문 경계 |
| I07 | 필수 설정·태그·세계관·일상 도움말 교체 | 완료 | Studio/Worlds/Packages의 표시 소유권, ko/en 문구·enum·준비/오류·원문 경계 |
| I08 | 선택 설정·장소·역할·추가 지침 안내 교체 | 완료 | Studio/Worlds/Packages의 표시 소유권, ko/en 문구·enum·준비/오류·원문 경계 |
| I09 | 공개 준비 상태·선택 그룹 수 표시 유지·dirty 안내 정리 | 완료 | Studio/Worlds/Packages의 표시 소유권, ko/en 문구·enum·준비/오류·원문 경계 |
| I10 | Field/IssueList/notice 오류 문구 번역 경로 통일 | 완료 | Studio/Worlds/Packages의 표시 소유권, ko/en 문구·enum·준비/오류·원문 경계 |
| I11 | 버튼 아래 디버그 JSX 제거 | 완료 | Studio/Worlds/Packages의 표시 소유권, ko/en 문구·enum·준비/오류·원문 경계 |
| I12 | 시간대·언어 안내와 조회 상태 정리 | 완료 | Studio/Worlds/Packages의 표시 소유권, ko/en 문구·enum·준비/오류·원문 경계 |
| I13 | 캐릭터 카드·기존 설정 조회·패키지 내보내기 안내 수정 | 완료 | Studio/Worlds/Packages의 표시 소유권, ko/en 문구·enum·준비/오류·원문 경계 |
| I14 | 기기 홈 아이콘 표시와 기존 프로필 자르기의 중립적인 재사용 경로 구성 | 완료 | AppIconVisual·WorldBanner·ImageCropDialog·공용 계산, 실제 자르기/버전/실패 시험 |
| I15 | World 배너 표시 컴포넌트를 Worlds 내부에서 공유 | 완료 | AppIconVisual·WorldBanner·ImageCropDialog·공용 계산, 실제 자르기/버전/실패 시험 |
| I16 | 기존 아이콘·배너 카드에 두 미리보기와 자르기 진입·draft 메타 조건부 표시 구현 | 완료 | AppIconVisual·WorldBanner·ImageCropDialog·공용 계산, 실제 자르기/버전/실패 시험 |
| I17 | 사진 선택→자르기→적용→World 저장→미리보기와 취소/실패 연결 | 완료 | AppIconVisual·WorldBanner·ImageCropDialog·공용 계산, 실제 자르기/버전/실패 시험 |
| I18 | 생성 전용의 카드 ON/OFF 표시 옵션과 기존 활성화 controller 연결 | 완료 | 기존 활성화 controller와 안정된 composition 컴포넌트 슬롯, 생성 ON/OFF/차단/409 시험 |
| I19 | 생성 하단에 완료·자율활동을 켜고 완료·건너뛰기 배치 | 완료 | 기존 활성화 controller와 안정된 composition 컴포넌트 슬롯, 생성 ON/OFF/차단/409 시험 |
| I20 | 명시 ON 성공 후 완료 이동·실패·응답 유실·scope 처리 연결 | 완료 | 기존 활성화 controller와 안정된 composition 컴포넌트 슬롯, 생성 ON/OFF/차단/409 시험 |
| I21 | 새 World 만들기 전체 안내·초기/초안 전·저장/필드 오류 문구 검토·수정 | 완료 | 새 World·패키지 승인/digest/token/차단·취소·독립 복사·다운로드 시험 |
| I22 | World 가져오기 상단·파일 선택·인증/확인 중 안내 수정 | 완료 | 새 World·패키지 승인/digest/token/차단·취소·독립 복사·다운로드 시험 |
| I23 | 가져오기 미리보기·중복·승인·취소·성공·경고·오류 표시 정리 | 완료 | 새 World·패키지 승인/digest/token/차단·취소·독립 복사·다운로드 시험 |
| I24 | 홈 브랜드·두 경로 nav 예외와 글꼴 계약 확정 내역 대조 | 완료 | 공식 Quicksand/OFL·로컬 번들, AppShell 명시 옵션·Next/static·오프라인 폰트 검증 |
| I25 | 공식 Quicksand 로컬 자산·원문 고지·출처 등록 | 완료 | 공식 Quicksand/OFL·로컬 번들, AppShell 명시 옵션·Next/static·오프라인 폰트 검증 |
| I26 | 홈 제목 JSX·font face/token·브랜드 스타일 반영 | 완료 | 공식 Quicksand/OFL·로컬 번들, AppShell 명시 옵션·Next/static·오프라인 폰트 검증 |
| I27 | AppShell의 명시적인 nav 옵션과 Next/static 두 경로 연결 | 완료 | 공식 Quicksand/OFL·로컬 번들, AppShell 명시 옵션·Next/static·오프라인 폰트 검증 |
| I28 | 디자인·구조·자산 출처 문서의 승인·적용 범위 동기화 | 완료 | 공식 Quicksand/OFL·로컬 번들, AppShell 명시 옵션·Next/static·오프라인 폰트 검증 |
| I29 | 캐릭터 목록 header의 실제 시각 기준·computed 굵기 확인 및 neutral 표시 분리 | 완료 | SectionHeading의 Character/embedded Relationship computed geometry 비교 |
| I30 | embedded 관계 header를 동일 표시로 연결 | 완료 | SectionHeading의 Character/embedded Relationship computed geometry 비교 |
| I31 | 사용자 게시글·Chat 사진의 공용 원본/최종/자원 정책과 입력 판별 구성 | 완료 | Media Worker·실제 HEIC/회전/반전/alpha·한도/취소·ASGI 게시/Chat 연결 검증 |
| I32 | HEIF/HEIC 로컬 디코더·Worker/WASM 경로 선정·등록 | 완료 | Media Worker·실제 HEIC/회전/반전/alpha·한도/취소·ASGI 게시/Chat 연결 검증 |
| I33 | 필요한 사진만 방향 보정·등비 축소·bounded 인코딩 | 완료 | Media Worker·실제 HEIC/회전/반전/alpha·한도/취소·ASGI 게시/Chat 연결 검증 |
| I34 | HEIF 변환·EXIF/반전·투명도·색상 처리 연결 | 완료 | Media Worker·실제 HEIC/회전/반전/alpha·한도/취소·ASGI 게시/Chat 연결 검증 |
| I35 | ImagePicker 단계·사본 upload·최종 preview·ko/en 오류 연결 | 완료 | Media Worker·실제 HEIC/회전/반전/alpha·한도/취소·ASGI 게시/Chat 연결 검증 |
| I36 | World feed·Chat에 같은 user-photo 정책과 scope/취소/draft 수명 연결 | 완료 | Media Worker·실제 HEIC/회전/반전/alpha·한도/취소·ASGI 게시/Chat 연결 검증 |
| I37 | Next 사진 proxy 요청 상한을 14MiB로 연결 | 완료 | Media Worker·실제 HEIC/회전/반전/alpha·한도/취소·ASGI 게시/Chat 연결 검증 |
| I38 | backend 사진 요청 상한·최종 재검증 대조·보완 | 완료 | Media Worker·실제 HEIC/회전/반전/alpha·한도/취소·ASGI 게시/Chat 연결 검증 |
| I39 | 사진 codec·경계·자원·두 화면/두 전송 경로와 Chat 인식 조건의 좁은 회귀 검증 | 완료 | Media Worker·실제 HEIC/회전/반전/alpha·한도/취소·ASGI 게시/Chat 연결 검증 |
| I40 | 사진 계약·decoder/코덱 고지·아키텍처/디자인 예외와 근거 동기화 | 완료 | Media Worker·실제 HEIC/회전/반전/alpha·한도/취소·ASGI 게시/Chat 연결 검증 |
| I41 | World 사진 네 POST·파일/요청 상한과 선택/저장 소유 경로 대조 | 완료 | 정확한 네 World POST 한도·5MiB 선택 경계·실제 자르기·기존 프로필 검증 |
| I42 | Next/backend의 World 프로필 사진 요청 예외 보완 | 완료 | 정확한 네 World POST 한도·5MiB 선택 경계·실제 자르기·기존 프로필 검증 |
| I43 | World 선택 guard·프로필 입력/오류·ko/en 보완 | 완료 | 정확한 네 World POST 한도·5MiB 선택 경계·실제 자르기·기존 프로필 검증 |
| I44 | World 사진 경로·경계·저장/실패의 좁은 검증과 계약 문서 동기화 | 완료 | 정확한 네 World POST 한도·5MiB 선택 경계·실제 자르기·기존 프로필 검증 |
| I45 | 실제 scheduler·SQLite engine/port·예외·건강 판정과 재현 근거 대조 | 완료 | 실제 SQLite adapter·BUSY 예산·bounded queue/future·권한 복구·health·안전한 진단 |
| I46 | SQLite lease adapter를 실제 runtime 조립에 연결 | 완료 | 실제 SQLite adapter·BUSY 예산·bounded queue/future·권한 복구·health·안전한 진단 |
| I47 | BUSY 코드 분류·rollback/재시도·짧은 예산과 observer 연결 | 완료 | 실제 SQLite adapter·BUSY 예산·bounded queue/future·권한 복구·health·안전한 진단 |
| I48 | lease DB의 bounded 비동기 큐·future 수명·취소/종료 연결 | 완료 | 실제 SQLite adapter·BUSY 예산·bounded queue/future·권한 복구·health·안전한 진단 |
| I49 | 재시도 소진의 실행 권한 기반 자동 복구 구현 | 완료 | 실제 SQLite adapter·BUSY 예산·bounded queue/future·권한 복구·health·안전한 진단 |
| I50 | tick/heartbeat/stop 보조 task·release·최초 오류 보존 보완 | 완료 | 실제 SQLite adapter·BUSY 예산·bounded queue/future·권한 복구·health·안전한 진단 |
| I51 | runtime 상태·health·안전한 복구 진단 연결 | 완료 | 실제 SQLite adapter·BUSY 예산·bounded queue/future·권한 복구·health·안전한 진단 |
| I52 | 실제 임시 SQLite 기반 lock/lease/queue/lifecycle 회귀 검증 | 완료 | 임시 파일 SQLite 시험, 동일 PID Docker 200→503→200·epoch 1→2·중복 0·정상 종료 |
| I53 | 격리 Docker에서 scheduler 잠금→제한→자동 복구 검증 | 완료 | 임시 파일 SQLite 시험, 동일 PID Docker 200→503→200·epoch 1→2·중복 0·정상 종료 |
| I54 | scheduler 구조·동시성 계약·검증 결과 문서 동기화 | 완료 | 임시 파일 SQLite 시험, 동일 PID Docker 200→503→200·epoch 1→2·중복 0·정상 종료 |
| I55 | Creator Studio·Worlds·World Packages·Characters·Media·필요한 Chat 및 shell locale·필요한 runtime 상태 안내 동시 수정 | 완료 | ko/en catalog 16 namespaces·2590 source keys·보간/복수 일치 |
| I56 | 관련 표시·미리보기·자르기·완료·신규/가져오기·브랜드·nav·관계 header·사진 첨부 검증 | 완료 | 이 문서의 V01–V35 근거와 별도 미측정 범위 |
| I57 | 변경 파일 lint·관련 catalog/구조/디자인·자산 고지 검사 | 완료 | 변경된 TypeScript 39개 scoped lint·관련 구조/디자인·라이선스 검사 |
| I58 | fake 데이터로 ko/en·좁은/넓은 화면·Next/static·오프라인 글꼴 확인 | 완료 | Next/static UI·사진, ko/en, 480/1024/1440px·오프라인 폰트·산출물 빌드 |
| I59 | diff·완료/미확인·원문 보존 재검토 | 완료 | 관련 diff·원문/데이터 보존·승인 예외 범위·최종 검증 상태 확인. 원문 OFL의 공백 경고는 아래 기록처럼 별도로 구분 |
| I60 | 지정 브랜치에서 관련 파일만 필요 시 로컬 커밋·결과 보고 | 완료 | 현재 브랜치의 관련 파일만 Signed-off-by 로컬 커밋; 최종 SHA/clean 확인은 workspace 계획의 실행 결과. PR/push/CI/main 없음 |

## 검증 실행과 선택 근거

다음은 별도 실행 결과다. 일부 pytest 행은 같은 테스트를 포함하므로 개수를 합산해 고유 시험 수로 주장하지 않는다.
공용 shell·Worker·폰트와 두 산출물이 변경되어 타입 검사와 Next/static 빌드가 필요했다. 전역 lint/전체 pytest/원격 CI는 실행하지 않았다.

| 관련 V | 실행 | 결과·범위 |
|---|---|---|
| V01–V28 | `pnpm exec playwright test --config=playwright.creator-copy.config.ts creator-copy --project=next --project=static-export --timeout=45000 --max-failures=1` | 91 통과: Next 46, static 45, 실패/skip/flaky 0. ko/en·실제 codec·draft 8조합·승인/내보내기·ON 4상태·폭별 도달/overflow |
| V17/V20–V24 | 최종 `creator-copy-media.spec.ts`만 두 project에서 실행 | 48 통과, 실패/skip/flaky 0. 정확한 64,000,000픽셀·구체 오류·JPEG/PNG 형식 유지·축소 alpha 보완 이후 실제 codec/한도/취소/Chat/폰트 재검증 |
| V17/V26–V28 | 같은 config의 `home font`, `World crop file size boundaries`, 기존 `Profile avatar and banner retain real crop` 선택 실행 | 10 통과. 실제 loaded font face·5MiB−1/정확히/초과·기존 프로필을 두 runtime에서 확인. 구체적인 초과 안내 assertion을 추가한 뒤 경계 4개를 다시 확인해 모두 통과 |
| V20/V25 | `node frontend/scripts/test-photo-profile-proxy.mjs` | 격리 Next/가짜 upstream의 14MiB·8,262,144 bytes·일반 1MiB·chunk·method/segment·CSRF 경계 통과 |
| V20–V28 | `uv run python -m pytest tests/common/test_request_body_limits.py tests/image_integration/test_image_formats.py tests/image_integration/test_chat_attachments.py tests/media/test_profile_media.py tests/worlds/test_creator_routes.py::test_world_banner_round_trip_stays_inside_worlds_domain_storage -q` (backend) | 113 통과. 기존 final MIME/pixel/metadata/alpha/color·Chat attachment·프로필/World 저장 보존 |
| V21/V23/V24 | `ANGMOO_BROWSER_PHOTO_ARTIFACTS`에 최종 합성 사진 경로를 지정하고 `uv run python -m pytest tests/image_integration/test_browser_prepared_photo_roundtrip.py -q` (backend) | 28 통과. 두 브라우저 산출물 7종(일반/HEIC/큰 사진/회전/alpha/좌우 반전/축소 alpha)을 실제 ASGI·임시 저장·공개 PostMedia/Chat MessageAttachment·fake 분석에 연결. actual pixels/asset ID·색상/방향 검증. 지정 경로 없이 일반 pytest가 실행되면 이 로컬 관찰 연결 시험만 명시적으로 skip하며, 이 실행은 skip 0 |
| V29–V34 | `uv run python -m pytest tests/test_creator_scheduler_recovery.py tests/routines/test_scheduler_singleton.py tests/test_l3_er4_single_backend_runtime.py tests/test_l3_er2_sqlite_concurrency.py tests/common/test_request_body_limits.py -q` (backend) | 86 통과. 실제 파일 DB·SQLite BUSY/LOCKED/IOERR/FULL·CAS·pool·queue·lifecycle·health·공통 request 한도 |
| V31–V34 | 최종 `uv run python -m pytest tests/test_creator_scheduler_recovery.py -q` (backend) | 18 통과. 마지막 살아 있는 자식 task guard 포함. 기존 86 실행과 겹치는 결과를 중복 합산하지 않음 |
| V08/V17 | `uv run python -m pytest tests/test_creator_design_assets.py tests/test_t1_5_project_license.py -q` (backend) | 각 8/5 통과. 정확한 font/fixture digest·원문 OFL·URL/추가 face/변조 거절·실제 UNC와 JS regex 구분·기존 GPL 검사 |
| V07 (I55) | `pnpm test:ui-catalog` (frontend) | 16 namespaces·2590 source keys, ko/en key/보간/plural 일치 |
| V08/V10 | 변경한 TypeScript/TSX 39개만 `pnpm exec eslint <변경 파일>` | 오류 0·경고 0. 마지막 사진 보완의 직접 소스 3개도 다시 확인해 오류/경고 0 |
| V08/V10 | `python scripts/ci/check_frontend_architecture_boundaries.py`; `python scripts/ci/check_architecture_boundaries.py` | feature 14·legacy exact edges 0; modules 1469·edges 6268·legacy exact edges 0 |
| V08/V17 | `python scripts/ci/check_frontend_design_contract.py --check` | raw colors 1161/35 files(기존 1167보다 감소), surfaces 18, route gaps 0, diagnostic screenshot call sites 53. canonical PNG 11·고정 Linux 환경·25px/0.1 허용치 불변 |
| V08/V10/V17 | `uv run python ../scripts/check_dependency_licenses.py --check-notice ../THIRD_PARTY_NOTICES.md`; `python ../scripts/check_project_license.py` (backend) | python 85·node 67·정확한 conditional reviews 5, GPL-3.0-only/OFL·LGPL 고지 검사 통과 |
| V09/V17 (I58) | `ANGMOO_NEXT_DIST_DIR=.next-creator-production pnpm exec next build`; `pnpm build:static` (frontend, PowerShell env 설정) | 생산 Next와 정적 산출물·TypeScript 검사 통과. `out`/`static-shell/out`의 생성 파일은 소스 입력에서 제외하며 Worker 원본 타입 검사는 유지 |
| V09 (I58) | `studio draft metadata` 선택 실행과 화면 캡처 확인 | 2 통과. ko/en·480/1024/1440px 미리보기 캡처, 480px 한국어 및 1440px 영어의 실제 카드/문구/메타 배치 확인. 내부 스크롤 화면은 미리보기로 이동한 viewport를 캡처하며 canonical PNG 갱신/USER CHECK와 구분 |
| V35 | 별도 Docker image/container·3382·tmpfs, 실제 single-backend manager/SQLite lease와 fake tick | 아래 실제 운행 증거 참조 |

## V01–V35 판독

각 묶음은 아래 근거로 검토했다. UI는 합성 API 데이터, DB는 임시 데이터, AI provider는 fake이다.
이 표의 검증은 실제 AI 품질·설치 앱·원본 운영 서버 복구·사용자의 직접 화면 확인을 대신하지 않는다.

| V | 근거·판독 |
|---|---|
| V01 | 목록 네 그룹·enum 번역·unknown fallback·원문 `P2/CORE` 보존, 빈/503 상태와 기존 groupFor/launchable 목적지 검토 |
| V02 | World 초안/공개/보관 표시·선택 설정 0개·readiness/dirty 구분; 등급/hash/버전 기본 JSX 제거, 원문 데이터 불변 |
| V03 | 이름만 초안·이미지 미저장 제한·선택 빈 값; 기존 role key/daypart/길이/tag payload·field validators 검토 |
| V04 | draft 8조합·공백·readiness 버튼 저장 0회·row version 저장/공개 순서 보존 |
| V05 | 422 안내의 raw validator 비노출·crop 409·새 World 환경 로딩/실패·기존 권한/통신 분기와 ko/en 문구 검토 |
| V06 | 실제 내보내기 checkbox→preview→내용 변경 시 무효화→prepare/token/download; 캐릭터 역할/연결/제거·고급 원문 접근은 소유 함수 보존 |
| V07 | 두 locale 렌더링·동적 상태 label·오류/aria·catalog; 사용자 이름/원문·World language 값을 UI 언어로 바꾸지 않음 |
| V08 | 경계/디자인/고지 검사와 neutral crop/header/icon·feature-owned banner; 승인된 예외만 반영 |
| V09 | Next/static의 Studio 네 화면·생성/홈/설정/사진과 header를 ko/en·480/1024/1440px에서 확인; 마지막 실제 control 도달·overflow 검증 |
| V10 | 기준 clean HEAD·지정 브랜치·관련 변경만 검토. DB schema/키/원본 사용자 파일·운영 서버·PR/CI/main 미변경 |
| V11 | Home와 draft AppIconVisual, 소개와 draft WorldBanner를 같은 컴포넌트로 공유. deterministic fallback/cover geometry 보존 |
| V12 | draft 이름/소개/태그 8조합과 공백·배너만 표시; 선택/조절/취소 HTTP 0, 적용/409/재시도와 이전 값 보존 |
| V13 | 생성 카드 ON/OFF 없음·세 버튼 순서; OFF/ON/키 없는 blocked/409 failure에서 기존 controller gating과 다른 화면 ON/OFF 검토 |
| V14 | OFF→ON 요청 1, 이미 ON 0, 실패/skip/일반 완료의 추가 저장/OFF/등록 0. 기존 등록 receipt·epoch·leave guard·복귀 실패 처리 검토 |
| V15 | 새 World 초안 전 이미지 disabled·이름만 입력/선택 empty·422/원문 비노출·환경 state 구분 |
| V16 | Import preview·digest/token approval·독립 복사·cancel·blocked·damaged fallback·commit success. TTL/변경/cleanup 분기는 기존 소유 코드 보존/문구 대조 |
| V17 | 외부 요청 차단·캐시 없는 컨텍스트의 실제 로컬 font face 로딩·700/coral, 원문 고지/정적 복사·fallback 계약 |
| V18 | 두 runtime 설정/생성 AppShell navigation/footer 없음·폭별 마지막 control 도달; 다른 local/World 탐색 보존 |
| V19 | 세 폭·두 locale에서 Character/embedded Relationship icon/title/description computed 값 비교; h2/h1·standalone 분기 보존 |
| V20 | 실제 padded JPEG 10/20MiB 경계·손상/20MiB 초과, Next/ASGI chunk/byte/method/segment 경계·최종 서버 검증 |
| V21 | 실제 WASM primary HEIC, 4096px 축소·EXIF 회전/좌우 반전·alpha·RGB 읽기와 원본 보존. 기존 유효 ICC 보존 시험 |
| V22 | 조기 16,384px/64MP/APNG 거절·Worker cancel/supersession/30초·이전 첨부/본문 보존, scope/unmount/late response guard 검토 |
| V23 | 두 runtime 실제 준비 bytes를 ASGI Media/upload/storage→manual PostMedia 또는 Chat MessageAttachment에 연결·실제 pixel/asset ID 확인 |
| V24 | Chat 실제 최종 ID preflight denied→allowed·전송 차단/허용·메시지 첨부 ID, fake 인식 분석/기존 실패/재시도 시험 |
| V25 | 정확한 네 POST request 8,262,144 bytes와 유사/추가/빈 segment·다른 method·일반/agents/media 예외·CSRF 확인 |
| V26 | World 5MiB 선택 경계·구체 안내·기존 실제 저장/프로필/crop/실패 검증. 파일 크기 검사는 FileReader/디코딩 전 분기임을 소스로 대조 |
| V27 | 실제 crop canvas와 출력 pixels 비교·768²/1024×384·MIME/byte cap·원본·기존 profile UI 저장 회귀 |
| V28 | 취소 0/적용 1회·최신 row version·409 상태/조절값 보존·첫 draft guard. scope/epoch·URL/bitmap/canvas cleanup와 dialog focus/keyboard 계약 검토 |
| V29 | 두 connection의 실제 BEGIN IMMEDIATE, 다섯 lease 쓰기·acquire race·fresh transaction/rollback/CAS |
| V30 | 실제 BUSY 예산/timeout 복원, code mask·BUSY_SNAPSHOT·LOCKED/IOERR/FULL/불명 비재시도와 좁은 fallback |
| V31 | 실제 queued/running future·capacity/deadline·취소 뒤 worker 수명·event-loop 응답/Session thread·drain 이후 재획득 |
| V32 | 만료 자기 owner 새 epoch·다른 owner/fence·정상 권한 heartbeat·finish 경합 뒤 완료 효과/장부 중복 없음 |
| V33 | 실제 acquire/start 실패와 잠긴 release의 최초/cleanup 오류 구분·민감 내용 없는 진단·살아 있는 자식의 정상/예외 종료 guard |
| V34 | registry READY만으로 200 불가·만료 proof 503·실제 runner/heartbeat 뒤 복구·중지/drain·projector 기존 정책 |
| V35 | Docker tmpfs의 실제 lock→503→unlock→200, 동일 PID/시작 시각·epoch 변경·새 tick·중복 0·정상 shutdown |

## 격리 Docker 운행 결과

전용 image `angmoo-creator-lock-test:20261010`의 manifest digest는
`sha256:fafc5e416038cb30c7aff55106420d49ee6332eac12c73572ab8bbed1fb75696`다.
[Compose 설정](../../scripts/diagnostics/creator-scheduler-lock-test.compose.yml)과
[검증 앱](../../backend/scripts/verify_scheduler_lock_recovery.py)은 제품 API에 test endpoint를 추가하지 않는다.
원래 3000/18080·앱 컨테이너·사용자 volume/DB는 변경하지 않고, 별도 3382와 /tmp tmpfs만 사용했다.

| 증거 | 잠금 전 | 장기 잠금 중 | 잠금 해제 뒤 |
|---|---|---|---|
| health | 200 | 503 | 200 |
| scheduler | READY | DEGRADED | 실제 권한 확인 후 READY |
| backend PID | 1 | 같은 프로세스 | 1 |
| process start monotonic | 1088.885978628 | 동일 | 1088.885978628 |
| fencing epoch | 1 | expired proof로 READY 아님 | 2 |
| 완료 tick 효과 | 8 | 신규 tick 제한 | 9 |
| 동일 window 중복 | 0 | 0 | 0 |

7초짜리 실제 SQLite writer lock은 6초 TTL을 넘겼다. 해제 뒤 새 epoch와 신규 tick을 확인했다.
종료 요청 뒤 lifespan shutdown complete·container exit 0을 확인했고, 전용 container/network를 제거했다. 사용자 volume은 사용하지 않았다.
raw 결과/로그/종료 증거는 ignored `artifacts/creator-copy-media-20261010/docker-recovery.json`, `docker-recovery.log`, `docker-shutdown.json`에 있다.
이 결과는 현재 원본 운영 서버가 이미 같은 코드로 재시작·복구됐다는 주장이 아니다.

## 검증 중 발견·수정한 내용과 남는 범위

- 실제 HEIC fixture에서 초기 라이브러리 호출 방식의 ABI 불일치를 찾았다. pin된 libheif WASM의 실제 C ABI·primary handle·안전 제한·free 경로로 수정했고,
  fake decoder가 아닌 Next/static actual pixels 및 ASGI 최종 첨부로 재검증했다.
- 살아 있는 tick 자식의 일반 예외 경로도 finish/restart로 종료를 가장하지 않도록 마지막 guard를 추가했다. 해당 파일 최종 18개가 통과했다.
- TypeScript 입력에 정적 산출물의 복사된 Worker가 섞이는 빌드 문제를 해결했다. 생성 출력 디렉터리만 제외하고 원본 Worker/제품 검사는 유지한다.
- ref callback을 렌더 함수에 넘기는 경계는 stable component slot과 stable callback으로 바꿨다. React ref 검사 규칙을 끄거나 임의로 UI lock을 해제하지 않았다.
- 최종 계약 대조에서 입력 픽셀 한도의 이진 단위 계산을 정확한 64,000,000픽셀로 수정했다. 64,000,000 허용·64,008,000 거절과
  Worker의 구체적인 해상도 오류를 확인한다. 필요한 JPEG/PNG/WebP 축소는 원래 형식으로 인코딩하고 HEIF는 native alpha flag로
  JPEG/PNG를 선택하도록 보완했다. 새 축소 PNG의 실제 alpha·두 산출물·ASGI 연결을 함께 확인한다.
- 테스트 자체의 DTO/enum/EXIF 기대값·synthetic in-memory DB의 thread 소유·prepared download_path와 static preview fallback·숨겨진 Dialog footer 판정도 바로잡았다.
  오류를 숨기거나 검증 기준/visual 허용치를 넓히지 않았다. 기존 Starlette/httpx·anyio deprecation 경고 2종은 실패와 구분했다.
- 실제 AI 품질/비용, 원본 사용자 데이터로 실행, 설치 Windows 앱/물리 기기의 메모리·safe-area·모든 카메라/codec 호환성은 측정하지 않았다.
  canonical pinned-Linux PNG 갱신이나 direct USER CHECK도 수행하지 않았다. 이 작업의 로컬 자동 검증·격리 Docker 범위와 구분한다.

## 증거 파일과 최종 기록

[사진/코덱·출처·자원 계약](../operations/local-photo-codec.md),
[frontend 구조](../../frontend/ARCHITECTURE.md), [디자인](../../frontend/DESIGN.md),
[backend 구조](../../backend/ARCHITECTURE.md), [SQLite 동시성](../architecture/l3-er2-sqlite-concurrency.md)을 동기화했다.
로컬 상세 결과는 ignored `artifacts/creator-copy-final-browser-results.json`와
`artifacts/creator-copy-media-20261010/`의 JSON/XML/log/합성 사진/스크린샷에 보존한다.

최종 상태는 다음과 같다.

- I00–I60 61개 단계의 완료 근거와 V01–V35 35개 묶음의 판독을 위 표에 연결했다.
- 초기 전체 화면 시험 91개, 최종 직접 사진/폰트 시험 48개, 폰트/프로필/World 경계 선택 시험 10개,
  강화한 World 초과 안내 재시험 4개, 화면 캡처 시험 2개가 각각 통과했다. 같은 사례의 재실행을 고유 시험 수로 합산하지 않는다.
- 최종 실제 browser→ASGI/Post/Chat 연결은 28개 모두 통과했고, 원본 파일과 provider 호출 정책을 보존했다.
  이 시험은 ignored 합성 산출물 경로를 명시한 로컬 관찰 연결 시험이다. 새 checkout에 산출물이 없다는 이유로 일반 pytest를 실패시키지 않는다.
- 마지막 사진 소스를 포함한 Next/static 빌드와 restored source-input 설정의 `pnpm exec tsc --noEmit`가 통과했다.
  구조·디자인·catalog·고지 검사의 범위와 기준, canonical screenshot 환경/허용치는 유지했다.
- 카드 캡처에서 실제 여백·메타 조건부 표시·ko/en 문구와 좁은/넓은 미리보기 배치를 확인했다.
  scoped lint와 제품 코드/작성 문서의 최종 diff whitespace 검사는 통과했다. 전체 신규 파일을 포함한 검사에서는
  공식 원문 OFL 두 사본(`frontend/src/assets/fonts/quicksand/OFL.txt`, `frontend/public/licenses/Quicksand-OFL.txt`)의 21행 끝 공백만 경고했다.
  정확한 원문/고지 digest 계약을 지키기 위해 해당 공백은 그대로 보존했다. 이 두 원문만 제외한 diff 검사에 다른 공백 오류는 없다.
  키·DB·사용자 사진·운영 로그·빌드 산출물은 커밋 대상에 넣지 않는다.
- 구현 로컬 커밋은 관련 110개 파일로 한정했고, 검증 기록의 이 보완만 별도 로컬 커밋으로 남긴다. 사용자 서버 3000/18080·운영 Docker·설치 앱은 변경하지 않는다.
  이 작업의 3380/3381 preview만 종료하고, 격리 Docker container/network는 정상 종료 뒤 제거했다.
- 최종 상세 JSON은 `artifacts/creator-copy-final-media-results.json`, `creator-copy-font-profile-results.json`,
  `creator-copy-world-boundary-results.json`, `creator-copy-visual-review-results.json`에도 보존한다.
  화면은 `artifacts/creator-copy-media-20261010/visual-final/`, 최종 ASGI 결과는 `final-photo-roundtrip.xml`/`.log`에 있다.
