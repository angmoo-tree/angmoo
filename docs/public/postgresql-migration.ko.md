# Angmoo 0.1.3 데이터를 0.1.4로 이전하기

[English](postgresql-migration.md) | 한국어

Angmoo 0.1.4는 앱 데이터·활동 checkpoint·검색에 PostgreSQL을 사용합니다. **기존 0.1.3의 SQLite 데이터는 이전이 필요합니다.** 이미지만 바꿔서는 데이터가 변환되지 않습니다.

직접 이전은 정식 **0.1.3** 데이터 형식(SQLite schema 41)을 지원합니다. 다른 SQLite 릴리즈와 비공개 PostgreSQL 실험 데이터는 이번 지원 범위에 포함하지 않습니다. ID·대화·글·기억·관계·미디어·설치 비밀값을 보존하고, 정리 작업 복구·경험 스냅샷 등 0.1.4 기능에 필요한 새 필드를 준비합니다.

## 시작 전

같은 정식 [0.1.4 Release](https://github.com/angmoo-tree/angmoo/releases/tag/release-v0.1.4)의 파일을 사용하고 `RELEASE-SHA256SUMS`로 검증하세요. 자산은 공개 이후에 사용할 수 있습니다. 다운로드가 없다고 `main`의 스크립트로 대신하지 마세요.

도구는 원본·백업 위치·남은 공간을 보여주고 확인을 받습니다. 선택한 이전 환경을 정상 종료하고, 불변 백업과 작업 사본을 만든 뒤 새 PostgreSQL 설치로 변환합니다. 기존 설치·이미지·데이터는 삭제하지 않습니다. 변환과 인덱스 재구축은 AI 제공처를 호출하지 않습니다.

백업에는 대화와 키가 포함됩니다. 개인 저장소에 보관하고 Issue에 첨부하지 마세요. 사본·새 DB·이미지 파일시스템을 위한 공간이 필요하며, 표시되는 공간 검사는 최소 기준이지 이후 미디어 증가량의 예측은 아닙니다.

## Docker amd64·ARM64

Docker를 실행하고 0.1.4 이미지 세 개를 먼저 내려받거나 불러오세요. Windows는 `angmoo-migrate.exe`, Python 3.10 이상이 있는 Linux 호스트는 `angmoo-migrate.py`를 사용합니다.

Docker 이미지는 Linux amd64·ARM64를 제공합니다. macOS 호스트에서의 이전은 미검증이며 공식 지원은 후속 작업입니다. ARM64 이미지가 있다는 사실만으로 Mac의 기존 설치 탐색·권한 처리·복귀 동작까지 검증된 것은 아닙니다.

```powershell
.\angmoo-migrate.exe --language ko
```

```sh
python3 angmoo-migrate.py --language ko
```

Compose 라벨과 backend의 실제 마운트를 읽어 이전 대상을 찾습니다. 하나면 내용을 확인하고 시작하며, 여러 개면 먼저 하나를 선택합니다. 첫 대상을 임의로 고르지 않습니다. Docker 접속·권한 오류는 후보가 없다는 뜻으로 처리하지 않습니다.

자동으로 찾은 대상이 없을 때만 직접 지정하세요.

```powershell
.\angmoo-migrate.exe --language ko --source-volume "angmoo_angmoo_contributor_embedded_data" --backup-directory "D:\AngmooBackups"
```

예시를 그대로 쓰기 전에 실제 볼륨 이름을 확인하세요. `--list`는 이전하지 않고 목록만 표시합니다. Windows 설치판의 AppData는 Docker 이전 입력으로 사용하지 않습니다.

검증 후 브라우저 주소와 새 설치의 `compose.json` 경로를 출력합니다. 이후 기동·종료에는 이 파일을 사용합니다.

```sh
docker compose -f "<백업-폴더>/<이전-회차>/installation/compose.json" ps
docker compose -f "<백업-폴더>/<이전-회차>/installation/compose.json" stop
docker compose -f "<백업-폴더>/<이전-회차>/installation/compose.json" up -d --wait
```

생성된 Compose는 검증한 이미지와 새 영속 볼륨을 사용합니다. 이전 SQLite 볼륨을 PostgreSQL 데이터 폴더로 사용하지 않습니다. 이전 폴더에는 정상 운영 설정·자격 증명·백업이 있으므로 보존하세요.

같은 이미지·원본으로 중단된 변환을 재개하려면:

```powershell
.\angmoo-migrate.exe --language ko --resume "D:\AngmooBackups\<이전-회차>\migration.json"
```

새 설치를 중지하고 보존한 이전 환경으로 복귀하려면:

```powershell
.\angmoo-migrate.exe --language ko --rollback "D:\AngmooBackups\<이전-회차>\migration.json"
```

복귀는 이전 전에 실행 중이던 원본 컨테이너만 다시 시작합니다. 이전 후 PostgreSQL에서 추가한 내용은 새 환경에 남으며 SQLite에 합쳐지지 않습니다.

## Termux / PRoot ARM64

[Termux 안내](termux.ko.md)의 버전이 고정된 설치기로 공식 실행기를 갱신하세요. 기존 0.1.3 설치는 기동 전에 이전을 안내합니다. 직접 시작할 수도 있습니다.

```sh
angmoo migrate --release 0.1.4 --language ko
angmoo start
```

사용자 지정 설치는 원래 home을 명시하세요.

```sh
angmoo --home "$HOME/.local/share/angmoo-custom" migrate --release 0.1.4 --language ko
```

원본 설치 manifest를 확인한 뒤 형제 폴더 `<원래-home>-postgresql`에 ARM64 이미지 세 개를 설치하고 공통 변환기를 실행합니다. 원래 home은 보존하며 검증 후에만 새 home을 선택합니다. 이전 자체는 AI를 호출하지 않고, 일반 `start`가 정상 앱 동작을 시작합니다.

활성화 전에 중단됐다면 같은 이전 명령으로 재개할 수 있습니다. 원본·이미지 커밋·변환 규칙이 같아야 합니다. 원래 설치로 복귀하려면:

```sh
angmoo migrate --rollback --language ko
angmoo start
```

사용자 지정 설치의 복귀에도 같은 `--home`을 사용하세요. 이전 중에는 Termux를 열어 두세요. Android는 wake lock 중에도 프로세스를 종료할 수 있으며 Linux·ARM64 성공이 휴대폰의 백그라운드 생존을 보장하지는 않습니다.

Termux에서 이전을 재개할 때는 원래 목표 소스와 이미지 식별 정보를 유지합니다. 새로 지정한 manifest가 다르면 기존 설치를 종료하기 전에 `migration_resume_target_changed`로 중단합니다. 원래 후보로 재개하며, receipt를 바꾸거나 다른 후보에 과거 작업을 연결하지 마세요.

## Windows x64 설치판

기존 SQLite 데이터는 원래 위치에 보존합니다. 이전 작업 사본에서는 새 프로세스의 실행 소유권·접속 정보와 실행 잠금 파일만 제외하며, checkpoint·결과 저널·미디어·설치 비밀값은 포함합니다. 복사 중에도 실행 잠금을 유지해 다른 sidecar가 같은 원본으로 실행되지 않도록 합니다.

Angmoo를 종료하고 0.1.4 설치본을 실행하세요. 처음 기동할 때 이전 확인창과 백업 위치를 검토합니다. 거절하면 기존 SQLite를 변환하거나 지우지 않습니다. 동의하면 사용자 Angmoo 경로 안에 별도의 네이티브 PostgreSQL 클러스터와 앱 데이터 폴더를 준비합니다.

**프로그램 설치와 데이터 이전은 별도 단계입니다.** 설치기가 구버전을 발견해 먼저 제거할지 묻는다면 **제거하지 않기**를 선택해 업데이트할 설치를 유지하세요. 같은 0.1.4를 재설치할 때는 컴포넌트 추가·재설치 항목을 사용합니다. 데이터 이전 확인창은 설치기의 기존 버전 선택 화면이 아니라 설치된 앱을 처음 실행할 때 나타납니다. 기본 데이터 보존 옵션을 유지하세요.

최초 초기화·이전은 일반 재시작보다 오래 걸릴 수 있습니다. 실행기의 준비 기한은 최초 준비 최대 4분, 일반 재시작 1분이며 모든 사용자의 이전이 같은 시간에 끝난다는 보장은 아닙니다. 오류가 표시되면 원본·백업을 보존하고 복구 절차를 따르세요.

설치판이 PostgreSQL 17·pgvector를 제공합니다. Docker·WSL·별도 PostgreSQL 설치는 필요하지 않습니다. Angmoo 전용 클러스터·자격 증명·loopback 포트를 사용하며, 시스템 전체 DB 서비스를 등록하거나 개발자가 사용하던 PostgreSQL을 종료하지 않습니다.

실패하면 원본과 `postgresql-migration` 폴더를 보존하세요. 다음 실행에서 호환되는 작업을 재개할 수 있습니다. 오류를 없애기 위해 DB 파일을 삭제하거나 유일한 백업 위에 재설치하지 마세요. [백업·복구](postgresql-backup.ko.md) 절차와 오류 코드를 이용하세요.

## 복구 가능한 범위

기존 임베딩을 변환하고 키워드·그래프 인덱스를 재구축합니다. 과거에 저장하지 않은 원문은 만들어낼 수 없으므로 해당 기억은 원문 스냅샷 부족 상태를 명시합니다. 새 기억에는 현재 스냅샷 정책을 적용합니다.

완료 결과와 실패 이력은 유지합니다. 과거 실행 중이던 정리 작업의 실행권은 새 프로세스에 넘기지 않고 복구 필요 상태로 바꿉니다. 실패 부분은 수동 복구하며, 실패를 종료하면 이력을 보존하고 다음 자동 회차에 섞지 않습니다. 이전 성공이 AI 제공처 접속이나 모든 개인 질의의 검색 관련성을 인증하지는 않습니다.

PostgreSQL DB에 0.1.3 이미지를 연결해 되돌리지 마세요. 구형 이미지는 보존한 구형 SQLite와 함께 사용합니다. 저장 책임은 [실행 계약](postgresql-runtime.ko.md), 전체 백업은 [백업·복구](postgresql-backup.ko.md)를 참고하세요.

## 도구 코드와 검증 근거 확인하기

이전 도구는 오픈소스입니다. [Docker 호스트 실행기](../../launcher/migrate/docker_migrate.py), [Termux 이전 처리](../../launcher/termux/migrate.py), [공통 변환기](../../backend/app/runtime/postgresql_migration.py)를 확인할 수 있습니다. Windows도 [네이티브 실행기](../../backend/app/runtime/windows_postgresql.py)를 통해 같은 변환기를 사용합니다. 다운로드한 릴리즈를 검토할 때는 계속 바뀌는 `main` 대신 해당 릴리즈 태그를 선택하세요.

Release의 `angmoo-migration-tools.json`, `release-manifest.json`, `RELEASE-SHA256SUMS`는 소스 식별 정보와 파일 해시를 연결합니다. 검증 기록과 연결된 Actions 결과에는 시험한 플랫폼과 남은 제한을 적습니다. 해시는 파일의 일치를 확인하고, 플랫폼별 이전·보존·복구 시험은 확인한 동작의 근거를 제공합니다. 개인 데이터와 자격 증명은 공개 보고서에 넣지 마세요.
