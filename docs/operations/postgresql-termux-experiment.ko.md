# Termux PostgreSQL 격리 실험과 SQLite 데이터 이전

2026-10-28 새 후보의 schema 3, 원문 스냅샷, 기존 PG 복제본 전환과 단일 backend 프로세스
정책은 [기억 원문 스냅샷 안내](memory-experience-snapshots.md)를 함께 적용한다.
아래 10-27 기록은 당시 실행 근거이며 새 후보의 실기기 통과를 뜻하지 않는다.

작성일: 2026-10-27. 이 문서는 **준비된 로컬 실험 `angmoo-pg-20261027-run01`**의 실행 안내다. 공개 설치기나 정식 업데이트 명령이 아니다. [English](postgresql-termux-experiment.md).

## 지원 범위와 검증 경계

| 항목 | 이번 지원·검증 범위 |
|---|---|
| 원본 | Termux Angmoo 0.1.3, 소스 `01ef3847c77a890071728b7f618f18fa88b775bf` |
| SQLite | schema 41, revision `20261022_0118`, migration count 117, canonical 181개 테이블 |
| 대상 | PostgreSQL 17.11, pgvector 0.8.7, ARM64 이미지 파일시스템을 PRoot로 실행 |
| 기기 | Galaxy A52s SM-A528N, Android 14, Google Play Termux 2026.10.09 |
| 검색 | PostgreSQL GIN 전문검색·CJK bigram·부분 일치, pgvector 768차원 float32 cosine 정확 검색 |
| 이전 | canonical·유효 벡터·예산·checkpoint/pending writes·미디어·secret 보존, FTS/LadybugDB 재구축 |
| 과거/미래 schema | 40·42 및 알 수 없는/손상 파일은 거절. 검증하지 않은 upgrade chain을 실행하지 않음 |
| 후속 | G5 혼합 부하·장시간·화면 꺼짐·자원/배터리 비교, 실제 AI/사용자 확인, Windows 설치판·Docker 제품 지원 |

공식 PRoot를 그대로 사용했을 때 Google Play Termux의 Android linker/공유 메모리 helper 문제가 발생했다. 이번에는 **시험 폴더 안의 고정 소스 PRoot 수정본**과 APK loader를 사용했다. 전역 `proot`·Termux 설정·기존 `angmoo` 명령을 바꾸지 않았다. 다른 기기나 Termux 배포판에서도 작동한다고 일반화하지 않는다. `scripts/postgresql_experiment/build_phone_proot.py`와 실행 기록의 `versions.lock.json`/`g1-report.md`가 해당 자산의 근거다.

## 위치와 실행 구성

PC 코드: `D:/project_code/angmoo-workspace/experiments/angmoo-postgresql-termux`, 로컬 브랜치 `experiment/postgresql-termux`. 원격이 없고 push가 차단돼 있다. 원본 `angmoo-tree-angmoo`의 `main`/`work/0.1.4`는 그대로 사용한다.

휴대폰에서는 다음처럼 경로를 잡는다. 아래 명령은 **Termux 셸**에서 실행한다.

```sh
TRIAL="$HOME/angmoo-pg-experiments/20261027-run01"
python "$TRIAL/scripts/phone_app.py" status all
```

| 시험 자산 | 경로/포트 |
|---|---|
| 실행기·이전 도구 | `$TRIAL/scripts/` |
| 이미지 원본과 식별 | `$TRIAL/artifacts/`, `$TRIAL/records/app-images.json` |
| PostgreSQL 이미지·클러스터 | `$TRIAL/rootfs`, `$TRIAL/pgdata`, `127.0.0.1:15414` |
| backend/frontend 이미지 | `$TRIAL/images/`, 각각 `18114` / `13114` |
| 이전 전 원본 백업 D0 | `$TRIAL/migration/D0` (읽기 전용), `snapshot.json` |
| 오프라인 변환 작업본 D1 | `$TRIAL/migration/D1` |
| 이전 후 앱 파일 | `$TRIAL/appdata`, DB `angmoo_pg_run01` |
| 백업 복원 검증본 | `$TRIAL/appdata-restore`, DB `angmoo_pg_run01_restore` |
| 구버전 복구 시험본 | `$TRIAL/migration/D2-recovery`, `$TRIAL/recovery-images/` |
| 선택된 실행 대상 | `$TRIAL/records/selection.json` |
| 비밀값 | `$TRIAL/secrets/` 및 앱 파일의 `secrets/`. 내용을 출력하거나 Git에 넣지 않음 |

세 이미지는 로컬 자산이다. 휴대폰에서 Docker daemon을 돌리지 않고 PRoot 프로세스가 각 파일시스템을 사용한다. 실제 image ID·archive hash·소스 SHA는 `app-images.json`에 기록한다. frontend 변경은 기존 Chat 진단 내보내기에 PostgreSQL SQLSTATE 필드를 보존하는 두 파일로 제한했다. 이 변경은 **LOCAL**이며 hosted UI나 새로운 화면을 참고하지 않았다. backend와 frontend의 빌드 커밋 식별자는 다르므로 정식 동일 소스 릴리즈 후보라는 의미가 아니다.

## 현재 준비된 시험본을 다시 켜고 끄기

G4에서 이미 변환·검증한 대상은 **다시 convert/activate하지 않는다**. 첫 활성화의 `verify`는 사용 전 원본과의 완전 일치를 검사하므로 사용 중 늘어난 세션·활동 행이 있으면 달라지는 것이 정상이다. 현재 선택된 복원 검증본을 그대로 시작한다.

```sh
python "$TRIAL/scripts/phone_app.py" start all
python "$TRIAL/scripts/phone_app.py" status all
# 휴대폰 브라우저: http://127.0.0.1:13114
python "$TRIAL/scripts/phone_app.py" stop all
```

실행 순서는 PostgreSQL → backend → frontend, 정상 종료는 반대 순서다. PID·시작 시각·boot ID·이미지/실행 ID를 대조하며 다른 앱의 포트나 프로세스를 종료하지 않는다. 동일한 소유 프로세스가 준비됐다면 중복으로 만들지 않는다. 부분 기동 실패 시 살아 있는 프로세스와 기록을 보존한다. 원인을 확인한 뒤 `stop all`로 시험 프로세스를 정지하고 다시 시작한다.

앱은 `angmoo_pg_run01_runtime` 계정으로 실행한다. 이 계정에는 앱 행의 읽기/쓰기 권한만 있고 superuser·DB 생성·schema 생성·schema ledger 변경 권한이 없다. `angmoo_pg_run01_admin`은 준비·이전·백업·복원 도구에서 사용한다. runtime DSN 파일과 관리 DSN 파일은 별도로 보관한다.

실행 모드는 `validation`과 `real-use`로 나눈다. 선택 기록이 없으면 `validation`이다. 검증 모드는 자동 SNS/AI worker와 외부 provider 연결을 차단하며, 복호화·화면/API·저장·검색·합성 checkpoint 재개를 확인한다. 실사용 모드는 기존 설정과 복제된 자격 정보를 사용해 채팅, 자동 SNS, 기억 처리·임베딩 등 실제 작업을 허용한다. 예약된 작업이 곧바로 실행되거나 API 사용료가 발생할 수 있다. 기존 캐릭터 활성화 설정·모델·예산을 임의로 변경하지 않는다.

사용자가 G5 실사용을 요청했을 때 다음 순서로 전환한다. 기존 앱 파일과 PostgreSQL 백업을 먼저 보존하고, 모드 선택 후 세 서비스를 다시 시작한다.

```sh
python "$TRIAL/scripts/phone_app.py" stop frontend
python "$TRIAL/scripts/phone_app.py" stop backend
python "$TRIAL/scripts/phone_app.py" start postgres
python "$TRIAL/scripts/phone_migrate.py" pg-backup
python "$TRIAL/scripts/phone_app.py" mode real-use
python "$TRIAL/scripts/phone_app.py" start all
python "$TRIAL/scripts/phone_app.py" status all
```

`records/execution-mode.json`은 선택된 데이터 경로와 연결해 저장하며 재시작에도 유지한다. 앱이 실행 중이면 모드 변경을 거절한다. 검증 모드로 돌아가려면 같은 종료 순서 뒤 `mode validation`과 `start all`을 실행한다. 이 변경은 시험 데이터의 새 활동을 되돌리거나 원본 SQLite로 복사하는 작업이 아니다.

두 모드 모두 SQLite 연결 금지, 시험 경로·DB identity·최소 권한 runtime role 검사를 유지한다. backend `/health`의 `validation_mode=false`, `automatic_activity=enabled`와 실제 scheduler 준비 상태를 확인해야 실사용 기동으로 인정한다. 화면의 상태만 바꾸거나 health 검사를 생략하지 않는다. 실사용 기동은 G5 전체 통과, 실제 AI 품질 또는 USER CHECK 완료를 뜻하지 않는다.

Docker에서 내보낸 이미지의 `/etc/resolv.conf`가 비어 있으므로 실행기는 설치된 Termux의 resolver 설정을 `$TRIAL/records/resolv.conf`로 복사하여 PRoot 내부에 연결한다. 전역 DNS나 이미지 파일을 수정하지 않는다. 첫 사용 이후에는 시험 폴더의 복사본을 유지한다. DNS/TLS 연결 확인은 자격 정보 인증이나 실제 AI 응답 검증과 구분한다.

서비스 로그는 `$TRIAL/logs/`에 기록하며 USB를 분리해도 실행 프로세스가 살아 있는 동안 계속 남는다. 이번 모드 선택 자체는 전체 SNS 상세 관찰 세션이나 장시간 CPU/PSS 측정을 시작하지 않는다. G5의 동등 부하 비교·호출 수/비용·60분/8시간/화면 꺼짐 판정은 별도 측정 기록으로 남긴다.

시작 직후 FTS가 기존 canonical 자료를 재검증·재구축할 수 있다. 휴대폰에서는 수분이 걸린 관측이 있다. 이때 검색 준비 상태는 `preparing`이며 SQLite나 빈 검색 결과로 자동 우회하지 않는다. `/health`의 HTTP 응답은 서비스 기동 확인이며 모든 검색 준비 완료와 같지 않다. backend 로그·PG 진단·projection 진행 상태를 함께 확인한다.

## 새로운 원본을 이전하는 순서

다음은 **비어 있는 새 시험 대상에 대한 첫 이전 순서**다. 현재 `run01`에 그대로 재실행하면 D0/대상 존재 검사로 거절된다. 새로운 run을 만들 때는 소유 marker, 허용 경로/DB/포트, 이미지 manifest와 실행 자산을 함께 고정해야 한다. 기존 run의 폴더나 DB를 삭제하여 재사용하지 않는다.

1. 원본 `angmoo status`로 실제 설치·data root를 확인한다. 원본을 정상 종료하고 열린 데이터 FD가 없는지 확인한다. 시험 중 원본과 후보의 성능을 동시에 비교하지 않는다.
2. 관리 도구가 초기화한 고정 major 17 PostgreSQL과 별도 빈 DB를 준비한다. 이 run의 클러스터/role/확장/DB identity는 G1 준비 기록에 연결돼 있다. 앱 파일·PGDATA·자격을 이미지에 넣지 않는다.
3. 아래 순서로 전체 백업, 변환, 검증, 첫 선택을 수행한다.

```sh
python "$TRIAL/scripts/phone_migrate.py" inspect
python "$TRIAL/scripts/phone_migrate.py" dry-run
python "$TRIAL/scripts/phone_migrate.py" backup
python "$TRIAL/scripts/prepare_phone_database.py"
python "$TRIAL/scripts/phone_migrate.py" convert
python "$TRIAL/scripts/phone_migrate.py" verify
python "$TRIAL/scripts/phone_migrate.py" activate
python "$TRIAL/scripts/phone_app.py" start backend
python "$TRIAL/scripts/phone_app.py" start frontend
```

`inspect`는 원본 정지·전체 파일 수·용량·디스크 예산을 확인한다. D1이 있으면 schema/무결성도 검사한다. `backup`은 필요한 여유 공간을 검사하고 원본 전체를 D0와 D1으로 복제한다. writer가 살아 있거나, 원본이 복사 중 바뀌거나, 대상이 이미 있으면 거절한다. schema 판별은 일관된 D1에서 수행하며 지원하지 않는 자료를 PostgreSQL에 쓰지 않는다.

`prepare_phone_database.py`는 G1에서 준비된 시험 클러스터를 기동하고, 빈 대상 DB·확장·소유 identity·비공개 관리 DSN을 준비한다. 사용자가 SQL을 직접 입력할 필요가 없다. 현재 run01은 이미 준비됐으므로 반복 실행하면 변경 전에 거절된다.

`convert`는 181개 테이블의 타입·ID·FK·unique·시각·JSON을 변환하고 PK 순서의 행 digest를 대조한다. 기존 Vec1 payload를 추출해 768차원 float32 값과 등록 정보·scope·예산을 검증한다. 유효 벡터를 재사용하고 임베딩 API를 호출하지 않는다. checkpoint는 SDK 저장 형태로 변환하고 부모/channel version/pending writes 및 strict serialization을 검증한다. 해석 불가 타입은 거절한다.

D0는 파일 전체가 byte 단위로 같아야 한다. D1은 읽기 전용 SQLite가 재생성하는 SHM과 **기존 DB에 딸린 빈 WAL의 생성/소멸만** 허용한다. 내용이 있는 WAL·DB·벡터·checkpoint·미디어·secret 변경은 모두 거절한다. 원본의 시작 당시 WAL도 D0에 그대로 보존한다.

`activate`는 원본과 D0의 최신성, 변환 결과, 앱 파일 hash를 다시 검사한 후 시험 실행기의 대상만 선택한다. 기존 `angmoo` wrapper나 원본 DB를 교체하지 않는다. 원본 앱을 그 사이 사용했다면 이전 D0를 최신 자료로 취급하지 말고 새로운 run의 백업부터 다시 진행한다.

## 중단·재개·지원 거절

```sh
# 재개 경계 시험 예: canonical 전체 단계까지 커밋 후 정지
python "$TRIAL/scripts/phone_migrate.py" convert --stop-after canonical
python "$TRIAL/scripts/phone_migrate.py" resume
# staging과 원본을 보존하고 중단 상태 기록
python "$TRIAL/scripts/phone_migrate.py" abort
```

`vectors`, `checkpoints`도 단계 경계로 선택할 수 있다. 완료 단계는 같은 migration ID·snapshot digest일 때만 이어간다. `abort`는 staging 삭제나 원본 복구 작업이 아니다. 잘못된 target/source·다른 migration ID·schema 40/42·손상 DB·해석 불가 checkpoint는 명시적으로 멈추며 임의로 빈 상태를 만들지 않는다. 부분 실패 기록은 휴대폰 `records/operation-failure-*.json`에 비공개로 보존한다. 원문 SQL/대화가 포함될 수 있으므로 공유할 때 내용 전체를 붙이지 않는다.

## PostgreSQL 백업과 빈 대상 복원

앱 writer를 먼저 정상 종료하고 PostgreSQL은 켜 둔다. `pg-backup`은 `pg_dump -Fc`와 media·secret·runtime 파일, 버전/이미지/권한 manifest, 테이블·sequence·constraint·index·trigger fingerprint를 연결한다. 실행 중인 PGDATA를 일반 파일 복사하지 않는다.

```sh
python "$TRIAL/scripts/phone_app.py" stop frontend
python "$TRIAL/scripts/phone_app.py" stop backend
python "$TRIAL/scripts/phone_migrate.py" pg-backup
# 위 명령의 backup 값을 사용한다. 아래는 검증에 사용한 실제 백업이다.
# 복원 대상 DB가 아직 없을 때만 실행 가능하다.
python "$TRIAL/scripts/phone_migrate.py" pg-restore --backup backups/20261027-055021-278a2bf5
python "$TRIAL/scripts/phone_migrate.py" activate-restored
```

이 run에서는 위 백업을 빈 `angmoo_pg_run01_restore`에 복원해 앱/API·검색·checkpoint 재개를 검증했다. **현재는 대상이 이미 있으므로 pg-restore를 다시 실행하지 않는다.** 검증된 복원 뒤에는 `start all`로 이어 쓴다. 비교 도중 멈춘 복원은 `pg-resume-restore --backup ...`로 fingerprint 검증부터 재개할 수 있지만, `appdata-restore` 복사까지 일부 수행한 상태는 덮어쓰지 않고 중지한다. 기존 기록을 조사하고 새 격리 대상에서 재시도한다.

PostgreSQL major 17과 필요한 role/확장을 유지한다. 새로운 major를 기존 PGDATA에 바로 연결하지 않는다. `pg_restore` 종료 코드뿐 아니라 정규화한 행 digest·sequence·DDL 의미·권한을 비교한다. PostgreSQL이 동일 상수 배열의 cast 표기를 바꾸는 경우만 좁게 정규화하고 다른 제약 차이는 허용하지 않는다.

## 원래 SQLite 앱으로 돌아가기

코드는 원본 `angmoo-tree-angmoo` 폴더에서 그대로 이어서 작업한다. 휴대폰은 시험 서비스를 정상 종료한 뒤 기존 `angmoo start`를 사용하면 원본 설치·원본 데이터로 돌아간다. 실험 파일 삭제는 필요하지 않다.

복구 연습에서는 D0를 변경 가능한 별도 `D2-recovery`로 복사하고 원래 0.1.3 이미지 파일시스템도 시험 폴더에 복사해 기동했다. 원본의 설치/데이터를 복원 대상으로 쓰지 않았다. 제공 도구는 `phone_migrate.py rollback-to-snapshot`과 `phone_recovery.py prepare/start/stop`이다. 현재 D2와 복구 이미지는 이미 있으므로 `prepare`는 반복하지 않는다.

```sh
python "$TRIAL/scripts/phone_app.py" stop all
# 이미 준비된 구버전+D0 복사본의 조회 복구 시험
python "$TRIAL/scripts/phone_recovery.py" start backend
python "$TRIAL/scripts/phone_recovery.py" start frontend
python "$TRIAL/scripts/phone_recovery.py" stop frontend
python "$TRIAL/scripts/phone_recovery.py" stop backend
```

구버전 복구 harness도 외부 API와 자동 활동을 중단한 조회 시험이다. **D0 복구는 전환 전 시점으로 돌아간다. PostgreSQL에서 이후 생성한 자료를 SQLite로 역이전하지 않는다.** 후보에서 새로 만든 자료는 PG 백업에 보존한다. 무손실 역변환 기능은 제공하지 않는다.

## 진단과 결과 해석

PostgreSQL 진단은 `pg_diagnostics.py`를 backend 이미지 안에서 실행한다. 기존 SQLite 직접 조회 SNS 보고서는 PG marker가 있으면 거절한다. 예를 들어 Termux에서 아래 Python을 실행한다.

```sh
python - <<'PY'
import pathlib,sys,time
r=pathlib.Path.home()/'angmoo-pg-experiments/20261027-run01'
sys.path.insert(0,str(r/'scripts'))
import phone_app
s=phone_app.selection()
x=phone_app.run_backend('/experiment/scripts/pg_diagnostics.py',
    '--dsn-file','/experiment/'+s['dsn_file'],
    '--data-root','/experiment/'+s['data_root'],
    '--output','/experiment/records/diagnostics-'+str(time.time_ns())+'.json')
print(x['stdout'])
raise SystemExit(x['returncode'])
PY
```

진단은 지정한 World/캐릭터의 scheduler·memory 상태·건수와 PostgreSQL 원인 코드를 다루며 provider의 답변 품질을 판정하지 않는다. 로그나 결과에 credential 값·대화 본문을 출력하지 않는다. 공개 API의 기존 오류 코드는 호환성을 위해 일부 유지하고, 내부에서는 SQLSTATE·pool·queue·timeout·currentness를 구분한다.

G4에서는 canonical 181개 테이블/27,506행, 벡터 255개, checkpoint 1,754개, pending writes 4,093개를 이전했다. SQLite 접속을 차단한 앱에서 암호화 자격 정보 57개의 복호화, 인증된 API 28개, 검색, 백업 복원과 합성 중단 활동의 재개를 검증했다. 실제 AI 응답 품질·장시간 안정성·모든 기기와의 호환성과는 구분한다.

원본·D0·실험 코드·이미지·DB·로그를 자동 정리하지 않는다. 삭제는 소유 경로/이미지/DB 목록과 보존할 근거를 제시한 뒤 사용자가 허락한 항목만 별도 작업으로 처리한다.

## SNS PostgreSQL 충돌 재시도

`SERIALIZABLE`에서 발생하는 `40001`은 실패한 SQL 한 문장만 다시 보내지 않고, 읽기·권한/실행권 검증·쓰기 전체를 새 트랜잭션으로 다시 수행한다. SNS의 `activity_write`는 기존 PostgreSQL transaction owner를 사용한다. 최대 4회, 전체 5초 예산과 20–100ms 지수 대기를 사용하며, 각 시도에서 ORM 캐시도 만료시킨다. PRoot에서 정상 DB 작업도 SQLite의 기존 250ms 예산을 넘길 수 있어 SNS DB 경계에 별도 예산을 둔다. 전역 격리 수준이나 연결 수는 낮추거나 늘리지 않는다.

적용 경계는 활동 바인딩·실행권 갱신·상태 초기화·피드 준비/전달/읽음/완료·Inbox 알림 처리·Routine 실행권/상태 반영·모델 호출 예산/프로필 저장·일일 준비·최종 결과/체크포인트 확인이다. 기존 게시 결과의 idempotency와 실행권 검증을 유지한다. provider 호출·이미지 생성·파일 작업은 재시도 callback 밖에 둔다. 같은 SNS 전체를 무조건 다시 실행하지 않으며, COMMIT 성공 여부가 불명확하면 자동 재전송 대신 기존 durable receipt를 확인해야 한다.

`40001`, `40P01`, `55P03`만 기존 owner의 재시도 대상이다. 제약 위반·권한 변경·실행권 상실은 숨기지 않는다. 재시도 소진/시간 제한/연결 풀 대기/불명확한 커밋은 provider timeout으로 분류하지 않는다. 활동 실패에는 안전한 SQLSTATE를 보존하고, 정상 완료하면 이전 실패 사유를 완료 결과에서 제거한다. 무한 대기를 줄이는 대신 제한을 넘는 실제 경합은 명시적 실패로 남는다.

회귀 검사는 실제 PostgreSQL 동시 갱신으로 실행권·피드 전달·최종 결과의 `40001`을 만들고, 실행권 재검증·메타데이터 보존·단일 provider 호출/게시 효과를 확인한다. COMMIT 단계 충돌, 4회 소진, 결과 불명 커밋의 재실행 금지도 별도로 검사한다. 휴대폰 실사용 결과와 장시간 G5 판정은 별도 증거로 기록한다.

근거: [PostgreSQL 17 트랜잭션 재시도 문서](https://www.postgresql.org/docs/17/mvcc-serialization-failure-handling.html).

## 충돌 추적 공간과 중단된 피드 선택 복구

휴대폰 실험 실행기는 `max_pred_locks_per_transaction=256`으로 SSI 충돌 추적 공간을 확보한다. `max_pred_locks_per_relation=32`도 명시해 기존 관계 단위 승격 기준을 유지한다. 연결 수 20, `shared_buffers=64MB`, 앱의 `SERIALIZABLE`과 입력 재검증은 유지한다. `53200`은 용량 문제이므로 반복 재시도로 숨기지 않는다. 공유 메모리 추가 할당량과 실제 기기의 전체 메모리·부하 중 안정성은 각각 측정한다. 이 설정은 실험용 실행기에만 적용된다.

응답 확인 전에 중단된 v2 Feed/Combined TargetSelector는 실행권·현재 입력·활동 단계·공개 행동 부재를 다시 확인한 뒤 한 번의 선택 복구를 허용한다. 기존 전달 기록과 최초 정상 호출 예산은 유지하고, 복구 예산 예약과 전달 시도 번호 갱신을 같은 트랜잭션에서 커밋한다. 실제 응답을 받기 전에는 전달 완료로 처리하지 않는다. 이전 시도의 늦은 콜백은 새 시도 번호를 덮어쓸 수 없으며, 복구 자체가 다시 중단돼도 허용 횟수를 채우지 않는다. 재개할 현재 cycle의 전달 기록은 보존 기간 정리에서 제외하고 다른 cycle의 기존 정리 정책은 유지한다.

이 복구는 아직 공개 효과가 없는 선택 요청에 한정된다. 완료한 답글·좋아요·게시를 다시 실행하지 않는다. 최초 요청이 공급자에게 도착했을 수 있어 추가 AI 비용이 발생할 수 있지만, 횟수와 기존 활동 예산으로 제한한다. 실행권 상실·입력 변경·예산 소진은 명시적인 실패로 남긴다. 실제 PostgreSQL 검사는 부모 그래프 취소·재개, 공개 효과의 단일 실행, COMMIT 충돌 후 원자적 예약을 검증한다. 실제 휴대폰 검증과 장시간 G5 판정은 별도 기록한다.

근거: [PostgreSQL 17 잠금 설정](https://www.postgresql.org/docs/17/runtime-config-locks.html).
