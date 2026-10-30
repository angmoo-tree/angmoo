# PostgreSQL 백업·복구

[English](postgresql-backup.md) | 한국어

Angmoo 전체 백업에는 **DB·미디어·설치 암호화 비밀값·실행 자격 증명·설치/버전 기록**이 필요합니다. World Package 내보내기는 전체 백업이 아닙니다. 일치하는 설치본 또는 이미지 세 개의 참조도 보관하고, 개인 파일을 공개 지원 보고서에 넣지 마세요.

## 정상 종료 후 백업

공식 실행기로 종료하고 완료를 기다리세요. 실행 중인 PGDATA나 그 안의 파일 하나만 복사하지 않습니다. 콜드 백업은 같은 PostgreSQL 주 버전·플랫폼·Angmoo 자원으로 복원합니다. Windows·Linux·Termux 사이의 이전을 폴더 복사로 대신하지 않습니다.

| 환경 | 종료 후 보존할 것 |
| --- | --- |
| Windows | `postgresql`·`postgresql-appdata`·미디어/비밀값·이전 폴더를 포함한 Angmoo 데이터 root 전체와 일치하는 설치본 |
| Docker 새 설치 | PostgreSQL 데이터·앱 데이터·bootstrap 비밀값 볼륨, Compose와 정확한 이미지 참조 |
| Docker 이전 설치 | 외부 영속 볼륨 두 개와 자격 증명·`migration.json`·`installation/compose.json`이 있는 개인 이전 폴더 |
| Termux | 선택된 PostgreSQL home의 자격 증명·PGDATA·앱 데이터·설치 기록, 원본 home의 선택 정보와 일치하는 릴리즈/이미지 manifest |

Docker 볼륨은 `docker inspect` 또는 저장한 Compose에서 실제 이름을 확인하세요. 아래는 종료한 볼륨 하나를 **새 개인 백업 폴더**에 보관하는 예입니다.

```sh
docker compose -f "<설치-폴더>/compose.json" stop
docker run --rm --user 0:0 --entrypoint tar \
  --mount type=volume,src=<실제-볼륨-이름>,dst=/source,readonly \
  --mount type=bind,src=<개인-백업-절대경로>,dst=/backup \
  ghcr.io/angmoo-tree/angmoo-backend:release-v0.1.4 \
  -czf /backup/<중복되지-않는-파일명>.tar.gz -C /source .
```

필요한 볼륨마다 반복하고 archive의 SHA-256을 기록하세요. 백업 중에는 DB를 시작하지 않습니다. `docker compose stop`은 볼륨을 보존하며 `--volumes`를 붙인 정리는 별개의 삭제 작업입니다. 이전한 설치의 평소 운영은 구형 0.1.3 프로젝트가 아닌 생성된 Compose 파일을 사용합니다.

Termux는 `angmoo stop` 후 `selection.json`에서 선택된 형제 home을 확인해 별도 개인 위치에 보관합니다. 원래 0.1.3 home은 따로 보존하세요. 같은 릴리즈를 재설치해 이미지 파일시스템을 다시 준비할 수 있지만, 복원한 데이터를 빈 설치로 대체해서는 안 됩니다. 호스트 도구의 호환성은 Termux 배포판·버전에도 영향을 받습니다.

## 복원 후 확인

새 빈 폴더나 볼륨으로 복원하세요. 해시·PostgreSQL 주 버전·플랫폼을 확인하고 자격 증명·권한을 보존합니다. 복원 사본의 기동·설치 ID/스키마·대표 기록/미디어 조회·새 쓰기·검색·정상 재시작을 확인할 때까지 현재 설치를 보존하고, 검증한 사본만 정상 사용 대상으로 선택합니다.

Windows의 네이티브 제어기는 실제 클러스터 경로와 PostgreSQL system ID를 확인해 기동·종료합니다. 내부 dump/복원 경로는 다른 설치의 백업이나 앱 연결이 남은 상태를 거절하며, 복원 전 dump를 남기고 같은 전용 클러스터의 빈 DB에 복원합니다. `pg_dump` 하나는 추가 DB 백업이며 위의 전체 파일 백업을 대체하지 않습니다.

ID를 임의로 바꾸거나 검사를 끄고, 미완료 작업을 지우거나 새 스키마에 구형 이미지를 연결해 기동을 강제하지 마세요. 복원 실패는 완료로 처리하지 않고 dump·개인 오류 기록을 보존한 채 맞는 자원으로 다시 확인합니다.

## 이전 후 0.1.3으로 복귀

[플랫폼별 이전 복귀](postgresql-migration.ko.md)와 보존한 구형 SQLite 설치를 사용하세요. 이전 후 PostgreSQL에 쓴 데이터는 SQLite로 돌아가지 않습니다. 어느 데이터를 보존할지 결정할 때까지 양쪽을 유지합니다. 이미지·이전 환경·백업 삭제는 별도로 의도한 정리에서만 수행합니다.

## 진단 정보

제품 커밋/버전·PostgreSQL 주 버전·schema·오류 코드·실패 단계를 기록하세요. DSN·비밀번호·SQL 매개변수·키·대화 본문은 공개하지 않습니다. Windows 설치판은 실제 설치와 열리는 데이터 경로를 먼저 확인해야 활성 DB를 판단할 수 있습니다. [구형 SQLite 복구](../operations/sqlite-recovery.md)는 보존한 이전 원본에 적용하며 실행 중인 PostgreSQL의 복구 절차가 아닙니다.
