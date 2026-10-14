# Windows installer language and EXE-only distribution

## English

The Windows installer is one NSIS EXE containing English and Korean.
Interactive installation asks you to choose **English / 한국어**. This choice
applies to installation, update, recovery and removal instructions. Angmoo's
separately saved app language stays unchanged. Interactive reinstall offers
the choice again; the uninstaller uses NSIS's saved installer language.
NSIS page controls follow that choice. Native Windows MessageBox buttons
(OK/Yes/No) follow the Windows display language; their translated message
body uses the chosen installer language. No OS language setting is changed.
Silent installation with /S remains noninteractive and preserves its existing
data and exit-code contract. No undocumented /LANG option is advertised.

New MSI builds, candidate uploads, attestations and official distribution are
retired. Past MSI files and verification records remain historical evidence.
There is no automatic removal of existing installations or user data.

Build with the pinned tools and locked dependencies using
`npm run build:installer` in `desktop`. This builds the real sidecar and
`tauri build --bundles nsis`. Candidate metadata accepts exactly one current
`nsis/Angmoo_{version}_x64-setup.exe`. It rejects stale installers, MSI files,
duplicates, helpers, private data, links and a different source/version.
Checksums, SPDX SBOM and provenance identify the same EXE. A dirty local
worktree is labelled in provenance and is not a final release candidate.

Use an isolated Windows VM or a dedicated test user with synthetic data for
installation, app launch, updates and uninstall. Verify the actual EXE in both
languages, cancellation, repeat language selection, long messages, scaling,
recovery success/failure and the account-wide irreversible deletion warning.
Cancellation, an unchecked deletion box, silent/update removal or final No
must preserve data. Final deletion still requires validation of every allowed
path and reparse rejection before deleting owned children.

Static checks, a compiled translation probe and silent fixture success are
separate from actual candidate GUI verification. If no isolated UI environment
is available, record missing GUI cases as unmeasured. Do not mark them passed.
PR/hosted CI, platform review, main merge and release publication are separate
follow-up steps. This guide does not claim a 0.1.0 release has been published.

## 한국어

Windows 설치 프로그램은 English와 한국어를 포함한 NSIS EXE 하나입니다.
대화형 설치에서는 **English / 한국어**를 선택합니다. 이 선택은 설치·업데이트·
복구·제거 안내에 적용하며, Angmoo 앱에 저장한 화면 언어를 바꾸지 않습니다.
대화형 재설치에서도 언어를 다시 고를 수 있고, 제거 프로그램은 NSIS가 저장한
설치 언어를 사용합니다. /S 무인 설치에는 선택 창을 띄우지 않으며 기존 데이터
보존·종료 코드 계약을 유지합니다. 확인되지 않은 /LANG 옵션은 안내하지 않습니다.
일반 NSIS 화면의 버튼은 선택한 언어를 사용합니다. Windows 기본 오류 창의
확인·예·아니요 버튼은 OS 표시 언어를 사용하고, 안내 본문은 선택한 설치 언어로
표시됩니다. OS 언어 설정은 변경하지 않습니다.

MSI의 신규 생성·후보 업로드·attestation·공식 배포는 종료합니다. 과거 MSI 파일과
검증 기록은 역사 자료로 보존하며, 기존 설치판이나 사용자 데이터를 자동 제거하지 않습니다.

고정된 도구와 lockfile의 의존성을 준비한 뒤 `desktop`에서
`npm run build:installer`를 실행합니다. 실제 사이드카를 빌드하고
`tauri build --bundles nsis`로 EXE를 생성합니다. 후보 메타데이터는 현재 버전의
`nsis/Angmoo_{version}_x64-setup.exe` 하나만 허용합니다. 이전 버전·MSI·중복·
보조 실행 파일·비공개 자료·링크·다른 source/version은 거절합니다.
checksum·SPDX SBOM·provenance는 같은 EXE를 가리켜야 하며, 미커밋 변경이 있는
로컬 후보는 provenance에 그 상태를 기록하고 최종 릴리스 후보로 취급하지 않습니다.

실제 설치·앱 실행·업데이트·제거 검증은 격리 Windows VM 또는 전용 시험 사용자와
합성 데이터를 사용합니다. 같은 EXE로 두 언어의 화면, 취소, 재실행의 언어 변경,
긴 문구·화면 배율, 복구 성공·실패 및 이 Windows 계정 전체의 영구 데이터 삭제 경고를
확인합니다. 취소·삭제 항목 미선택·무인/업데이트 제거·최종 아니요는 데이터를 보존해야 합니다.
최종 삭제 동의 후에도 모든 허용 경로와 reparse 검증을 거친 뒤 소유한 하위 경로만 정리합니다.

정적 검사·번역 시험 프로그램 컴파일·무인 합성 데이터 회귀와 실제 후보 EXE의 화면
검증은 구분합니다. 격리 환경이 없으면 확인하지 못한 화면 항목은 미측정으로 기록합니다.
PR·원격 CI·플랫폼 검토·main 병합·공식 공개는 별도 후속 작업이며, 이 안내는
0.1.0 릴리스 공개 완료를 의미하지 않습니다.

## Resource ownership and focused verification

Installer UI belongs to desktop, not the app's frontend catalog or backend DB.
`installer-languages.nsh` uses official NSIS LangString declarations with
Windows language IDs 1033/1042. The pinned Tauri hook include precedes
MUI_LANGUAGE registration, so resources must be global declarations:
LangString inside an Install section fails NSIS compilation.
The selected/restored $LANGUAGE is available before our MessageBox instructions
execute. A dedicated AngmooMessagePath supplies the reparse warning's path
without reusing a shared register or a compile-time macro argument.

The standard dialog uses MUI_LANGDLL_ALWAYSSHOW for interactive reinstall.
The pinned MUI macro's Silent guard and MUI_UNGETLANGUAGE preserve silent
behavior and saved removal language. No new dialog/template or app locale
write is added. Standard translations and original legal notices remain
owned by the framework and their original authors.
The confirmed awkward generic Korean welcome and license guidance is replaced
through the official MUI_WELCOMEPAGE_TEXT, MUI_PAGE_HEADER_SUBTEXT and
MUI_LICENSEPAGE_TEXT_BOTTOM options with paired LangString resources.
The pinned page order places License after Welcome (which has no page header).
License consumes and unsets the header override; later pages retain their defaults.
Generated-page ordering is checked. The original GPL text and consent stay intact.

Focused commands from the repository root:

```powershell
backend\.venv\Scripts\python.exe scripts\ci\check_windows_installer_i18n.py
backend\.venv\Scripts\python.exe scripts\ci\check_desktop_installer_contract.py
backend\.venv\Scripts\python.exe scripts\ci\check_er6_desktop_supply_chain.py
backend\.venv\Scripts\python.exe -m pytest -q backend\tests\test_windows_installer_i18n.py backend\tests\test_l3_er6_interactive_remove_data.py backend\tests\test_l3_er6_installer_supply_chain.py
backend\.venv\Scripts\python.exe -m pytest -q backend\tests\test_installer_update.py backend\tests\test_l3_er5_desktop_sidecar_security.py
```

After build, also pass `--generated <target>/release/nsis/x64/installer.nsi`
to the language checker. CI runs these checks and retains its existing actual
NSIS installation, rollback, supported upgrade and Defender gates.

Installer CLI verification must place --installer-result-path immediately inside
the selected data-root/runtime. A successful process exit alone is insufficient:
also verify the durable result status and payload identity. Console output in a
windowed EXE is optional; invalid output handles must not hide a failure or change
its nonzero exit. The normal desktop readiness pipe remains mandatory.

설치 CLI 시험의 결과 파일은 선택한 data-root/runtime 바로 아래에 둡니다.
종료 코드뿐 아니라 결과 JSON의 상태와 payload 식별도 함께 확인합니다.
콘솔 없는 EXE의 선택적 출력 실패가 원래 오류나 실패 종료 코드를 덮지 않도록
검증하며, 정상 앱의 필수 readiness pipe와 결과 경로 보호는 유지합니다.

Use a candidate output separate from historical bundles. An NSIS-only build
does not remove an old MSI from an existing output directory; the metadata
checker intentionally rejects that mixed directory. Preserve the old files and
use a clean checkout or separately configured candidate output instead.

The Windows product version must agree in Tauri configuration, the desktop
package and its lockfile root, and the Cargo package and its lockfile root.
CI reads the version from Tauri configuration when generating release metadata;
the generator refuses disagreement before writing checksums or provenance.
A version transition rebuilds the host and installer. Dependency package versions
and supported data schema versions are separate from this product version.
Keep the existing downgrade protection and installation identity when preparing
a lower-numbered official release; this does not automatically authorize updating
an existing higher-numbered development installation.

후보 출력은 과거 bundle과 분리합니다. NSIS-only build가 기존 출력 폴더의 MSI를
자동 삭제하지는 않으며, 메타데이터 검사는 그 혼합 폴더를 의도적으로 거절합니다.
기존 파일을 보존하고 clean checkout 또는 별도로 설정한 후보 출력에서 검증합니다.

Windows 제품 버전은 Tauri 설정, desktop package와 lockfile의 루트 항목,
Cargo package와 lockfile의 루트 항목이 일치해야 합니다. CI는 Tauri 설정에서
버전을 읽으며, 메타데이터 생성기는 불일치하면 checksum·provenance 작성 전에
거절합니다. 버전 전환 시 앱 실행 파일과 설치 프로그램을 다시 빌드합니다.
라이브러리 버전과 지원 데이터 schema 버전은 제품 버전과 별개입니다.
더 낮은 번호의 공식 릴리스를 준비해도 기존 설치 식별·다운그레이드 차단을
유지하며, 기존의 더 높은 번호 개발판을 자동으로 덮어쓰지 않습니다.

Official references: [Tauri multilingual installer](https://v2.tauri.app/distribute/windows-installer/#internationalization),
[NSIS LangString](https://nsis.sourceforge.io/Docs/Chapter4.html#langstring).
