# PostgreSQL 실행·저장 계약

[English](postgresql-runtime.md) | 한국어

Angmoo 0.1.4는 backend 프로세스 하나와 전용 PostgreSQL 17·pgvector 0.8.7을 사용합니다. 스케줄러·projector는 backend 안에서 실행하고, PostgreSQL은 앱 원본·작업 상태·활동 checkpoint를 저장합니다. LadybugDB는 재구축 가능한 관계 그래프입니다.

| 환경 | 실행과 저장 |
| --- | --- |
| Docker amd64·ARM64 | frontend·backend·postgres 서비스와 분리된 PG·앱 데이터 볼륨 |
| Termux ARM64 | PRoot의 이미지 파일시스템 세 개와 전용 PGDATA·앱 데이터·비밀 파일. Docker daemon 없음 |
| Windows x64 | Tauri·동봉 backend sidecar·Angmoo 네이티브 PostgreSQL. 사용자별 데이터, 시스템 DB 서비스 등록 없음 |

Windows 설치판은 Windows 10 1903(빌드 18362) 이상을 요구합니다. 동봉 PostgreSQL 프로세스에 UTF-8을 지정해 한글 설치·데이터 경로를 처리하며, Windows 시스템 언어나 다른 PostgreSQL 설치의 설정은 바꾸지 않습니다.

## 검색과 기억

키워드 검색은 PostgreSQL 전문검색에 기존 CJK 전처리·trigram/부분 일치 정책을 연결합니다. 의미 검색은 저장된 모델·profile과 소유자·World·캐릭터·대화 범위 안에서 **768차원 pgvector 정확 코사인 검색**을 사용합니다. 이번 도입에 HNSW를 추가하거나 단순 DB 이전 때문에 임베딩을 다시 생성하지 않습니다.

인덱스 결과는 권한의 근거가 아닙니다. 삭제했거나 범위를 벗어난 기억은 인덱스에 남았다는 이유로 전달하지 않습니다. Chat·SNS는 시작 입력을 고정하고 선택한 기억에 연결된 저장 원문 스냅샷을 전달합니다. 관계 검토는 상대별 상황기억 본문과 기존 관계 인식만 사용하고 원문 스냅샷을 재조회하지 않습니다.

기억·관계 정리는 공용 실행 슬롯 하나를 사용합니다. 선택한 캐릭터의 준비된 기억 run 또는 상대별 검토를 짧고 안전한 트랜잭션 경계로 연속 처리합니다. 캐릭터 회차 전체에 DB 잠금을 유지하지 않습니다. 임베딩은 기존 20개 묶음 상한을 유지하며 SNS·Chat·일반 조회는 별도로 계속할 수 있습니다.

## 연결과 오류

주 SQLAlchemy 풀은 최대 10개를 재사용하고 임시 연결 5개를 추가로 허용합니다. checkpoint 풀은 2개, 별도 직접 연결은 2개로 제한합니다. 처음부터 그 수만큼 모두 생성한다는 뜻은 아닙니다. 실행 계정은 최대 20개, 서버는 관리자 예약 3개와 운영 여유를 포함해 28개를 예산으로 둡니다.

직렬화 충돌은 발생할 수 있습니다. DB 전용 작업은 횟수·경과 시간 상한 안에서 트랜잭션 전체를 다시 실행하고, 제공처 응답은 트랜잭션 밖에서 기다립니다. 받은 AI 결과는 저장 복구에 재사용하며 commit이 불명확하면 식별 정보·receipt를 대조해 공개 행동 중복을 막습니다.

잘못된 AI 문자열은 DB 장애로 반복 재시도하지 않습니다. 실패한 정리 항목은 수동으로 복구하고, 실패를 종료하면 완료 결과·이력을 보존한 채 다음 자동 회차의 대상에서 제외합니다. 제공처 429·503은 SDK와 앱을 합쳐 최초 포함 실제 전송 최대 2회 정책을 유지합니다.

## 식별과 스키마

Docker·브라우저는 `CONTRIBUTOR_POSTGRESQL`, 토큰으로 보호하는 설치판은 `LOCAL_POSTGRESQL`을 사용합니다. 데이터 root의 marker는 설치 ID와 비밀 DSN 파일을 연결하며 DB의 설치 ID도 일치해야 합니다. 서비스 계정은 스키마 owner와 분리된 제한 계정입니다.

`app/runtime/persistence/postgresql_schema.py`가 schema v5와 순차 변경을 소유합니다. 설치·이전의 owner 경로가 서비스 전에 스키마와 확장을 준비합니다. 정상 backend는 다른 ID·스키마를 거절하고 SQLite로 돌아가거나 과거 Alembic을 적용하지 않습니다.

schema v5와 제품 버전 0.1.4는 다릅니다. 동결한 SQLite schema 41은 지원 원본 0.1.3의 계약입니다. 구형 `LOCAL_EMBEDDED`·`CONTRIBUTOR_EMBEDDED` 코드와 fixture는 호환용으로 남고 현재 공개 실행기는 PostgreSQL을 선택합니다.

## 파일과 비밀값

앱 데이터에는 미디어·기존 암호화 비밀값·실행 DSN·받은 결과 저널이 있고 PostgreSQL 파일은 별도로 저장합니다. DB dump 하나만으로 미디어나 암호문을 읽을 비밀값까지 보존되지는 않습니다. [백업 절차](postgresql-backup.ko.md)를 따르고 개인 자료를 공개하지 마세요.

Windows는 전용 loopback 포트와 실제 클러스터 경로·system ID를 확인해 제어하며 다른 PostgreSQL을 채택하지 않습니다. Docker DB 포트는 서비스 네트워크 안에 두고 Termux는 loopback에 연결합니다. 자격 증명은 비밀 파일에 저장하며 이미지 계층이나 명령줄 비밀번호로 넣지 않습니다.

서비스를 다시 시작할 수 있도록 DB 접속 비밀번호는 소유자만 접근하는 로컬 파일에 저장합니다. 이 파일 형식 자체가 비밀번호를 암호화하지는 않으므로 비밀값 폴더와 백업을 비공개로 보관하세요. Docker 이전 도구는 완전히 기록한 파일을 공개하고 기존 자격 증명을 덮어쓰지 않습니다. 기본 접근 모델은 [PostgreSQL 비밀번호 파일 보호](https://www.postgresql.org/docs/17/libpq-pgpass.html)를 참고하세요.

지원하는 0.1.3 전환은 [이전 안내](postgresql-migration.ko.md)를 참고하세요. 과거 SQLite 문서의 PRAGMA·FTS5·Vec1 명령은 PostgreSQL 운영 절차가 아닙니다.
