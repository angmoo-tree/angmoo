; ER6 product filesystem policy:
; - the installer owns only %LOCALAPPDATA%\Angmoo\app;
; - silent uninstall always preserves local data;
; - interactive full deletion requires the generated checkbox and one final
;   permanent-deletion confirmation;
; - every recursive target is a literal approved product child and is rejected
;   when the root or child is a junction/symlink (reparse point).

!macro ANGMOO_VERIFY_NOT_REPARSE Target Label
  System::Call 'kernel32::GetFileAttributesW(w "${Target}") i .r0'
  ${If} $0 = -1
    Goto ${Label}_verified
  ${EndIf}
  IntOp $1 $0 & 0x400
  ${If} $1 <> 0
    MessageBox MB_OK|MB_ICONSTOP \
      "Angmoo data removal stopped because an owned path is a reparse point: ${Target}"
    Abort
  ${EndIf}
${Label}_verified:
!macroend

!macro NSIS_HOOK_PREINSTALL
  StrCpy $INSTDIR "$LOCALAPPDATA\Angmoo\app"
  CreateDirectory "$INSTDIR"
  SetOutPath "$INSTDIR"
!macroend

!macro NSIS_HOOK_POSTINSTALL
  ; Remove only known files from the pre-contract preview app location. The
  ; new app directory and every user-data directory stay untouched.
  Delete "$LOCALAPPDATA\Angmoo\angmoo-desktop.exe"
  Delete "$LOCALAPPDATA\Angmoo\angmoo-sidecar.exe"
  Delete "$LOCALAPPDATA\Angmoo\THIRD_PARTY_NOTICES.md"
  Delete "$LOCALAPPDATA\Angmoo\uninstall.exe"
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  IfSilent angmoo_keep_local_data 0
  ${If} $UpdateMode = 1
    Goto angmoo_keep_local_data
  ${EndIf}
  ${If} $DeleteAppDataCheckboxState <> 1
    Goto angmoo_keep_local_data
  ${EndIf}
  MessageBox MB_YESNO|MB_ICONSTOP \
    "Permanently delete every Angmoo World, Character, post, relationship, local credential, and setting from this Windows account? This cannot be undone." \
    IDNO angmoo_keep_local_data

  !insertmacro ANGMOO_VERIFY_NOT_REPARSE "$LOCALAPPDATA\Angmoo" angmoo_root
  !insertmacro ANGMOO_VERIFY_NOT_REPARSE "$LOCALAPPDATA\Angmoo\canonical" angmoo_canonical
  !insertmacro ANGMOO_VERIFY_NOT_REPARSE "$LOCALAPPDATA\Angmoo\graph" angmoo_graph
  !insertmacro ANGMOO_VERIFY_NOT_REPARSE "$LOCALAPPDATA\Angmoo\search" angmoo_search
  !insertmacro ANGMOO_VERIFY_NOT_REPARSE "$LOCALAPPDATA\Angmoo\media" angmoo_media
  !insertmacro ANGMOO_VERIFY_NOT_REPARSE "$LOCALAPPDATA\Angmoo\secrets" angmoo_secrets
  !insertmacro ANGMOO_VERIFY_NOT_REPARSE "$LOCALAPPDATA\Angmoo\runtime" angmoo_runtime
  !insertmacro ANGMOO_VERIFY_NOT_REPARSE "$LOCALAPPDATA\Angmoo\logs" angmoo_logs
  !insertmacro ANGMOO_VERIFY_NOT_REPARSE "$LOCALAPPDATA\Angmoo\webview" angmoo_webview
  !insertmacro ANGMOO_VERIFY_NOT_REPARSE "$LOCALAPPDATA\com.angmoo.desktop" angmoo_legacy

  RMDir /r "$LOCALAPPDATA\Angmoo\canonical"
  RMDir /r "$LOCALAPPDATA\Angmoo\graph"
  RMDir /r "$LOCALAPPDATA\Angmoo\search"
  RMDir /r "$LOCALAPPDATA\Angmoo\media"
  RMDir /r "$LOCALAPPDATA\Angmoo\secrets"
  RMDir /r "$LOCALAPPDATA\Angmoo\runtime"
  RMDir /r "$LOCALAPPDATA\Angmoo\logs"
  RMDir /r "$LOCALAPPDATA\Angmoo\webview"
angmoo_keep_local_data:
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  ; The marker belongs to the migration mechanism, not to user content. This
  ; removes the product root only when full deletion emptied it; keep-data
  ; uninstall leaves the non-empty data root intact.
  ${If} $DeleteAppDataCheckboxState = 1
  ${AndIf} $UpdateMode <> 1
    Delete "$LOCALAPPDATA\Angmoo\localappdata-migration-v1.json"
    RMDir "$LOCALAPPDATA\Angmoo"
  ${EndIf}
!macroend
