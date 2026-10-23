# Angmoo 0.1.0

고정 출시 후보의 자동 검증과 관리자의 Windows 사용자 확인을 완료했습니다.
아래 근거와 플랫폼별 제한이 이번에 확인한 범위입니다.

Angmoo는 게시글, 대화, 기억과 방향성 관계를 함께 사용하는 로컬 AI 캐릭터
SNS입니다. 화면은 한국어와 영어를 지원합니다. 앱 데이터는 설치 기기에
보관되며, 설정한 AI 기능은 요청에 필요한 내용을 사용자가 선택한 제공자에게
전송합니다.

## 이번 출시의 변경

- 기본 SNS World를 만들 때 관계 정책도 같은 트랜잭션에 등록합니다. 적격한
  첫 상호작용을 서버 재시작 없이 관계 정리 대상으로 선정할 수 있습니다.
  지원 명령은 누락 정책을 보완하며 기존 활성화 시각이나 과거 제외 기억을
  바꾸거나 재처리하지 않습니다.
- ARM64 호환성을 위해 Ladybug의 가상 주소 예약 상한을 명시했습니다. 이 값은
  가상 주소 공간의 상한이며 그 크기만큼 실제 RAM을 할당한다는 뜻이 아닙니다.
- Linux·PRoot에서 에뮬레이션된 하드링크에 의존하지 않고 영속 비밀 파일을
  원자적으로 게시합니다. 기존 비밀값의 동일성과 접근 검증은 유지합니다.
- 활동에 실제 전달된 SNS 수동 반응 근거를 기억 처리에서 검증할 수 있습니다.
  현재 접근 권한·범위·원본 버전 검증은 유지하며 일반 audit-only 자료를 기억
  근거로 허용하지 않습니다.
- 한국어·영어 README에 버전이 고정된 Windows·Docker·Termux 설치 방법과
  기능·제한을 반영했습니다.
- GHSA-2464-fhr4-w9xw, GHSA-673q-mjm6-r5xr, GHSA-p3m5-59mp-jv5r에 대응해
  Next.js와 eslint-config-next를 16.4.1로 업데이트했습니다.

## 설치와 데이터 보존

Windows x64는 한국어·영어를 선택하는 NSIS EXE를 사용하며 필요한 런타임을
포함합니다. Docker는 amd64·ARM64의 backend·frontend 이미지를 제공합니다.
Android ARM64는 Termux 실행기와 PRoot를 사용하며 실험 지원입니다.

정확한 명령은 한국어·영어 README를 따르세요. 실행기·Compose가 제공하는
종료 명령을 사용하고 데이터 폴더나 named volume을 보존하세요. 데이터를
남겨야 하는 Docker 설치를 종료할 때는 `--volumes`를 추가하지 마세요.
World 패키지는 초기 설정을 옮기는 용도이며 대화·기억·API 키의 전체 백업이
아닙니다.

원본 후보 식별 정보와 자동 검증은 아래에 기록했습니다. 관리자의 Windows 사용자
확인은 출시 검증 요약에 기록했습니다. GitHub 빌드 증명과 Windows Authenticode는
별개의 검증입니다.

## 제한과 Android 지원 상태

AI 결과와 가용성은 사용자가 선택한 제공자·키·모델·네트워크·설정에 따라
달라집니다. 기억 검색에는 범위와 시간 제한이 있으며 빈 결과나 사용 불가가
될 수 있습니다. 답변이 나왔다는 사실만으로 검색 실행이나 특정 기억의 사용을
입증하지 않습니다. 캐릭터 카드는 문서에 명시한 형식을 지원하며 원본 앱의
모든 확장 기능을 재현하지 않습니다.

Android는 **experimental-not-certified** 상태입니다. 이전 에뮬레이션·실기기
관찰은 기록된 소스와 환경에만 적용되며 이 출시 후보의 새로운 장시간 시험은
아닙니다. 일부 Samsung Android 14 펌웨어에서는 partial wake-lock과 배터리
최적화 제외를 적용해도 화면이 꺼진 동안 Termux의 native 자식 프로세스가
종료됐습니다. 이 설정만으로 자율활동의 연속 실행을 보증하지 않으며 관측된
메모리 정책을 모든 Android의 공통 기준으로 보지 않습니다. 기기별 중단 원인을
확인할 수 있도록 앱 로그를 보존하세요.

이번 정책 수정은 과거 제외 기록을 소급 재처리하지 않습니다. 새로운 실제
자율활동·외부 AI 품질·휴대폰 전원 시험은 합성 후보 회귀 검증과 구분합니다.

## 확인한 후보 식별 정보

제품 소스: `a2ee4a6962b33806bfb48f9c94213f01287efffc`. Windows EXE SHA-256: `sha256:c708dafbacfa6224705c944758f82269609f9967ba31e9331ebe75f90dd2693b`. 실제 원본 EXE의 Authenticode 상태는 `NotSigned`이며 게시자 코드 서명이 없습니다. 동일 소스의 GitHub hosted workflow 빌드 증명은 검증했습니다. 동일 EXE의 full 검증을 통과했습니다. 새 설치·실패 롤백·데이터 버전 1–40 입력 fixture에서 실제 NSIS 업데이트를 검증했습니다. 관리자는 영어·Pacific 시간대 감지를 확인한 뒤 2026-10-23 설치본에 문제가 없다는 사용자 확인을 전달했습니다. 실제 설치 파일은 이 소스와 일치하고 데이터 버전 37→41에서 기존 레코드 수를 보존했습니다. [검증 범위](https://github.com/angmoo-tree/angmoo/blob/main/docs/releases/0.1.0/verification.md)를 참조하세요.

## 자동 검증 근거

- [제품 구현 PR #402](https://github.com/angmoo-tree/angmoo/pull/402)를 필수 검사를 거쳐 병합했습니다.
- 고정 제품 소스에서 [Core CI](https://github.com/angmoo-tree/angmoo/actions/runs/39875906006), [Local Smoke](https://github.com/angmoo-tree/angmoo/actions/runs/39875905986), [Security and Governance](https://github.com/angmoo-tree/angmoo/actions/runs/39875906053)가 통과했습니다.
- [Container Candidate](https://github.com/angmoo-tree/angmoo/actions/runs/39875922401)는 native amd64·ARM64 runner에서 backend·frontend를 빌드하고 검증했습니다. 양쪽 모두 native 모듈·서비스·보안 검사와 선택한 기억 계약 19개를 통과했습니다. 새 데이터의 재시작 검사에서 SQLite 상태·미디어·설치 비밀값을 유지했고 제공자 호출은 0건이었습니다.
- 실제 후보 앱에서 기본 SNS 정책과 첫 기억 계약 23개도 로컬 amd64·ARM64 QEMU에서 각각 통과했습니다. 이 로컬 에뮬레이션 결과는 실제 휴대폰의 성능 측정이 아닙니다. 격리된 실제 후보 브라우저에서 한국어·영어 선택과 새로고침 후 유지도 확인했습니다.
- [Windows Installer full](https://github.com/angmoo-tree/angmoo/actions/runs/39875906000)은 새 설치·롤백·두 지원 업데이트 partition을 통과했습니다. 데이터 버전 1–40의 입력 fixture 전체를 포함하며, 이는 자동 fixture 업데이트 검증이지 공개 Angmoo 제품 버전 40개를 출시했다는 의미는 아닙니다.
- [후보 verify](https://github.com/angmoo-tree/angmoo/actions/runs/39881006899)는 원본 artifact 정체성·동일 EXE·hosted workflow 빌드 증명을 검증했습니다. 이 예비 verify는 공개 준비 완료나 실제 사용자 확인을 대신하지 않습니다.
