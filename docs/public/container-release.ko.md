# Docker로 Angmoo 실행하기

이 안내는 Linux amd64·ARM64용 Angmoo 0.1.2을 대상으로 합니다.
[0.1.2 공개](https://github.com/angmoo-tree/angmoo/releases/tag/release-v0.1.2) 후에
아래 명령을 사용하세요. 공개 전에는
[기존 0.1.1 한국어 안내](https://github.com/angmoo-tree/angmoo/blob/release-v0.1.1/README.ko.md)를 따르세요.

- `ghcr.io/angmoo-tree/angmoo-backend:release-v0.1.2`
- `ghcr.io/angmoo-tree/angmoo-frontend:release-v0.1.2`

두 서비스는 같은 릴리스로 사용합니다. 다중 플랫폼 태그가 실행 환경의 아키텍처에
맞는 이미지를 선택합니다. 아키텍처별 manifest와 layer는 이미지의 구성 요소이며
별개의 앱 버전이 아닙니다.

## 설치와 시작

Git과 Compose 2.22.0 이상이 포함된 Docker를 설치한 뒤 실행하세요.

```sh
git clone --branch release-v0.1.2 --depth 1 https://github.com/angmoo-tree/angmoo.git
cd angmoo
docker compose up -d --wait
```

http://127.0.0.1:3000 을 엽니다. frontend는 loopback으로만 공개되며 backend와
내장 SQLite·검색·그래프 구성 요소는 지원되는 Compose 설정으로 실행됩니다.
별도 PostgreSQL이나 Neo4j 서버는 필요하지 않습니다.

## 상태·로그 확인과 종료

```sh
docker compose ps
docker compose logs --tail 100 backend frontend
docker compose down
```

일반 종료 명령은 이름 있는 데이터 볼륨을 보존합니다. 데이터가 필요하면
`--volumes`를 추가하지 마세요. 이미지 정리, 컨테이너 정리, 볼륨 삭제는 서로
다른 작업입니다. 이미지 다운로드 실패를 해결하려고 볼륨을 삭제하지 마세요.

## 업데이트와 데이터

사용 중인 릴리스 checkout, Compose 프로젝트 이름과 데이터 볼륨 연결을 기록하세요.
버전을 바꾸기 전에 Compose로 종료하고 설치 비밀값과 미디어를 포함한 전체 데이터를
백업합니다. 새 릴리스의 실제 업데이트 절차와 버전이 일치하는 backend·frontend 쌍을 사용하세요.

앱 이미지와 사용자 데이터는 별도로 보존됩니다. 지원되는 내장 마이그레이션은 시작할 때
데이터 세대를 검증하고 전환합니다. 임의의 과거 버전으로 되돌리거나 미래의 모든 버전과
호환된다는 보장은 아닙니다. 새 빈 프로젝트·볼륨을 만든 뒤 기존 데이터가 보존된
업데이트로 판단하지 마세요.

`ANGMOO_IMAGE_TAG`는 버전별 이미지 태그를 선택합니다. 제품 버전과 데이터 schema
버전은 별개입니다. 과거 개발 값을 사용하거나 버전 검사를 우회해서 실행하지 마세요.
World Package 내보내기는 전체 데이터 백업이 아닙니다.

## 개발·배포 관리

소스 개발은 별도 데이터 볼륨을 쓰는 [기여 환경](development.md)을 사용합니다.
후보 생성·동일성 검증·공개 절차는 [배포 안내](../operations/release-publishing.md)와
[후보 가져오기](../operations/release-candidate-import.md)를 참고하세요.

Android는 휴대폰에서 Docker를 실행하는 대신 [Termux·PRoot](termux.ko.md)를
사용합니다. Linux ARM64 호환성이 Android 백그라운드·Doze 동작 인증을 의미하지는 않습니다.
