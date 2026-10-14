# -*- coding: utf-8 -*-
!ifndef ANGMOO_INSTALLER_LANGUAGES_INCLUDED
!define ANGMOO_INSTALLER_LANGUAGES_INCLUDED

; Installer-only UI. Keep app preferences and stable diagnostic codes separate.
; Official NSIS numeric Windows language IDs: English 1033, Korean 1042.
; Global declarations precede Tauri's MUI_LANGUAGE registration; section
; MessageBox instructions only run after MUI has selected/restored $LANGUAGE.
; Dynamic paths use a dedicated variable, never a macro argument or shared register.
LangString AngmooWelcomeText 1033 "This setup installs Angmoo on your computer.$\r$\n$\r$\nClose Angmoo before continuing.$\r$\n$\r$\nClick Next to continue."
LangString AngmooWelcomeText 1042 "Angmoo를 설치합니다.$\r$\n$\r$\n실행 중인 Angmoo가 있다면 종료한 뒤 진행해주세요.$\r$\n$\r$\n계속하려면 다음을 눌러주세요."
LangString AngmooLicenseSubtitle 1033 "Please review the license agreement before installing Angmoo."
LangString AngmooLicenseSubtitle 1042 "Angmoo를 설치하기 전에 사용권 계약 내용을 확인해주세요."
LangString AngmooLicenseBottomText 1033 "If you accept the terms, click I Agree to continue. You must accept the agreement to install Angmoo."
LangString AngmooLicenseBottomText 1042 "사용권 계약에 동의하면 동의함을 눌러 계속해주세요. Angmoo를 설치하려면 계약에 동의해야 합니다."
LangString AngmooReparseRejected 1033 "Angmoo stopped this file operation because the path is a link or junction:$\r$\n$AngmooMessagePath"
LangString AngmooReparseRejected 1042 "경로가 링크 또는 정션이어서 파일 작업을 중단했어요.$\r$\n$AngmooMessagePath"
LangString AngmooCaseConflict 1033 "Installation stopped because a directory from a previous folder-name migration still exists."
LangString AngmooCaseConflict 1042 "이전 폴더 이름 변경 과정의 임시 폴더가 남아 있어 설치를 중단했어요."
LangString AngmooCaseRenameFailed 1033 "Angmoo could not normalize its folder name in LocalAppData. Installation stopped."
LangString AngmooCaseRenameFailed 1042 "LocalAppData의 Angmoo 폴더 이름을 정리하지 못해 설치를 중단했어요."
LangString AngmooCaseMigrationFailed 1033 "Angmoo could not finish changing the LocalAppData folder name. Installation stopped."
LangString AngmooCaseMigrationFailed 1042 "LocalAppData 폴더 이름 변경을 완료하지 못해 설치를 중단했어요."
LangString AngmooRuntimeNotClosed 1033 "Installation stopped because Angmoo did not close normally. Close Angmoo and try again."
LangString AngmooRuntimeNotClosed 1042 "Angmoo가 정상적으로 종료되지 않아 설치를 중단했어요. Angmoo를 종료한 뒤 다시 시도해주세요."
LangString AngmooPrepareFailed 1033 "The update could not be prepared. User data was not changed."
LangString AngmooPrepareFailed 1042 "업데이트를 준비하지 못했어요. 사용자 데이터는 변경하지 않았어요."
LangString AngmooStagingMismatch 1033 "Installation stopped because the app files did not match their verification information. The previous app and user data were preserved."
LangString AngmooStagingMismatch 1042 "설치하려는 파일이 검증 정보와 일치하지 않아 설치를 중단했어요. 기존 앱과 사용자 데이터는 유지했어요."
LangString AngmooDataIncompatible 1033 "This installer cannot safely read the existing data version. User data was not changed."
LangString AngmooDataIncompatible 1042 "이 설치 파일은 기존 데이터 버전을 안전하게 읽을 수 없어요. 사용자 데이터는 변경하지 않았어요."
LangString AngmooPromoteFailed 1033 "The verified app files could not be put in place. The previous app and user data were preserved."
LangString AngmooPromoteFailed 1042 "검증된 앱 파일을 설치 위치로 옮기지 못했어요. 기존 앱과 사용자 데이터는 유지했어요."
LangString AngmooRestoreFailed 1033 "The data upgrade and automatic restoration of the previous app could not be completed. Existing data was preserved."
LangString AngmooRestoreFailed 1042 "데이터 업데이트와 이전 앱의 자동 복원을 완료하지 못했어요. 기존 데이터는 보존했어요."
LangString AngmooUpgradeFailedRestored 1033 "The data could not be upgraded safely. The verified previous app was restored, and existing data was preserved."
LangString AngmooUpgradeFailedRestored 1042 "데이터를 안전하게 업데이트하지 못했어요. 검증된 이전 앱을 복원했고, 기존 데이터는 보존했어요."
LangString AngmooCleanupFailed 1033 "Update verification passed, but installation cleanup did not finish. Run this installer again before starting Angmoo."
LangString AngmooCleanupFailed 1042 "업데이트 검증은 완료됐지만 설치 정리를 끝내지 못했어요. Angmoo를 실행하기 전에 이 설치 파일을 다시 실행해주세요."
LangString AngmooConfirmFullDelete 1033 "Permanently delete all Angmoo data for this Windows account?$\r$\nWorlds, characters, posts, chats, relationships, memories, images, saved connection information, and settings will be deleted.$\r$\nThis cannot be undone."
LangString AngmooConfirmFullDelete 1042 "이 Windows 계정의 모든 Angmoo 데이터를 영구 삭제할까요?$\r$\nWorld, 캐릭터, 게시글, 채팅, 관계, 기억, 이미지, 저장된 연결 정보와 설정이 삭제돼요.$\r$\n이 작업은 되돌릴 수 없어요."

!endif
