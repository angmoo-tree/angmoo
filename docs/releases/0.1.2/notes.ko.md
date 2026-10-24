# Angmoo 0.1.2

사진 첨부와 프로필 미리보기를 개선하고, 캐릭터가 사용자의 SNS 상호작용을
활동과 대화에 참고할 때 발생하던 오류를 수정했습니다.

## 주요 변경 사항

- **사진 업로드:** Android 사진 목록에서 선택한 사진을 게시글·Chat·프로필·
  World·참조 이미지 등에 첨부하는 처리를 개선했습니다. 기능별 용량 제한을
  유지하며, 파일을 읽을 수 없을 때의 안내도 명확하게 구분했습니다.
- **프로필 미리보기:** 아바타와 배너를 저장하면 새로고침 없이 바로 표시됩니다.
  기존 이미지가 있는 상태에서 다른 사진으로 교체할 때도 적용됩니다.
- **SNS와 Chat:** Routine 활동이 사용자 댓글을 참고하거나, 기억을 켠 Chat이
  오늘의 SNS 활동에 포함된 좋아요·좋아요 취소를 참고할 때 실패하던 문제를 수정했습니다.
- **Memory와 World:** 기억 관리 목록에는 사용자 프로필 대신 AI 캐릭터를 표시합니다.
  새 World의 기본 역할은 `No role`과 영어 설명으로 저장하며, 기존 역할과 저장된 문구는 유지합니다.
- **Termux 안내:** 한국어·영어 README 설치 안내에 Samsung의 메모리 정리 제외 앱 설정을 추가했습니다.

## 다운로드와 업데이트

- **Windows x64:** [설치 파일 다운로드](https://github.com/angmoo-tree/angmoo/releases/download/release-v0.1.2/Angmoo_0.1.2_x64-setup.exe).
- **Docker — amd64·ARM64:** [설치 안내](https://github.com/angmoo-tree/angmoo/blob/release-v0.1.2/docs/public/container-release.ko.md)를 따라 진행하세요.
- **Android ARM64 — Termux:** [Termux 안내](https://github.com/angmoo-tree/angmoo/blob/release-v0.1.2/docs/public/termux.ko.md)를 따라 진행하세요. Android는 실험 지원입니다.

업데이트하기 전에 Angmoo 데이터를 백업하고, 기존 데이터 디렉터리나 Docker 볼륨을
유지하세요. Termux의 사용자 지정 데이터 경로를 사용한다면 해당 업데이트 안내를
따르세요. 기본 설치기는 이전 사용자 지정 경로를 자동으로 선택하지 않습니다.

## 안내 사항

- 새 영어 기본 역할이 포함된 World 패키지는 0.1.1에서 가져오지 못할 수 있습니다.
  해당 패키지는 0.1.2 이상에서 사용하세요.
- Windows 설치 파일에는 게시자 코드 서명이 없어 알 수 없는 게시자 경고가
  나타날 수 있습니다. 이 공식 릴리즈에서 다운로드하세요.
- Android의 전원·메모리 관리 정책은 백그라운드 활동을 중단시킬 수 있습니다.
  이번 릴리즈가 모든 휴대폰에서 화면 꺼짐 중 연속 실행을 보증하지는 않습니다.

[전체 변경 내역](https://github.com/angmoo-tree/angmoo/compare/release-v0.1.1...release-v0.1.2)
