; ER6 product filesystem policy:
; - the installer owns only %LOCALAPPDATA%\Angmoo\app;
; - silent uninstall always preserves local data;
; - interactive full deletion requires the generated checkbox and one final
;   permanent-deletion confirmation;
; - every recursive target is a literal approved product child and is rejected
;   when the root or child is a junction/symlink (reparse point).

; This state is deliberately separate from Tauri's generated checkbox state.
; A checked box is only a request; deletion becomes authorized only after the
; final irreversible-action confirmation and every target validation pass.
Var AngmooFullDeleteConfirmed
Var AngmooCanonicalAppRoot
Var AngmooHadExistingApp
Var AngmooPreviousRegistrationRoot
Var AngmooPreviousDisplayVersion
Var AngmooPreviousDisplayIcon
Var AngmooPreviousInstallLocation
Var AngmooPreviousUninstallString
Var AngmooPreviousMainBinaryName
Var AngmooHadStartMenuShortcut
Var AngmooHadDesktopShortcut
!define ANGMOO_INSTALLER_HOOK_DIR "${__FILEDIR__}"

!macro ANGMOO_VERIFY_NOT_REPARSE Target Label
  System::Call 'kernel32::GetFileAttributesW(w "${Target}") i .r0'
  ${If} $0 = -1
    Goto ${Label}_verified
  ${EndIf}
  IntOp $1 $0 & 0x400
  ${If} $1 <> 0
    MessageBox MB_OK|MB_ICONSTOP \
      "Angmoo filesystem operation stopped because an owned path is a reparse point: ${Target}"
    Abort
  ${EndIf}
${Label}_verified:
!macroend

; Generated Tauri registration happens while $INSTDIR points at staging. If a
; pre-promotion Gate fails, restore the previous durable registration (or
; remove the clean-install candidate registration) before exiting.
!macro ANGMOO_RESTORE_PREVIOUS_REGISTRATION
  StrCpy $INSTDIR $AngmooCanonicalAppRoot
  ${If} $AngmooHadExistingApp = 1
  ${AndIf} $AngmooPreviousRegistrationRoot != ""
    WriteRegStr SHCTX "${MANUPRODUCTKEY}" "" $AngmooPreviousRegistrationRoot
    WriteRegStr SHCTX "${UNINSTKEY}" "DisplayVersion" $AngmooPreviousDisplayVersion
    WriteRegStr SHCTX "${UNINSTKEY}" "DisplayIcon" $AngmooPreviousDisplayIcon
    WriteRegStr SHCTX "${UNINSTKEY}" "InstallLocation" $AngmooPreviousInstallLocation
    WriteRegStr SHCTX "${UNINSTKEY}" "UninstallString" $AngmooPreviousUninstallString
    WriteRegStr SHCTX "${UNINSTKEY}" "MainBinaryName" $AngmooPreviousMainBinaryName
    ${If} $AngmooHadStartMenuShortcut = 1
      !if "${STARTMENUFOLDER}" != ""
        CreateDirectory "$SMPROGRAMS\$AppStartMenuFolder"
        CreateShortcut "$SMPROGRAMS\$AppStartMenuFolder\${PRODUCTNAME}.lnk" "$AngmooCanonicalAppRoot\${MAINBINARYNAME}.exe"
      !else
        CreateShortcut "$SMPROGRAMS\${PRODUCTNAME}.lnk" "$AngmooCanonicalAppRoot\${MAINBINARYNAME}.exe"
      !endif
    ${Else}
      Delete "$SMPROGRAMS\$AppStartMenuFolder\${PRODUCTNAME}.lnk"
      Delete "$SMPROGRAMS\${PRODUCTNAME}.lnk"
    ${EndIf}
    ${If} $AngmooHadDesktopShortcut = 1
      CreateShortcut "$DESKTOP\${PRODUCTNAME}.lnk" "$AngmooCanonicalAppRoot\${MAINBINARYNAME}.exe"
    ${Else}
      Delete "$DESKTOP\${PRODUCTNAME}.lnk"
    ${EndIf}
  ${Else}
    DeleteRegKey SHCTX "${UNINSTKEY}"
    DeleteRegKey SHCTX "${MANUPRODUCTKEY}"
    !insertmacro MUI_STARTMENU_WRITE_BEGIN Application
      Delete "$SMPROGRAMS\$AppStartMenuFolder\${PRODUCTNAME}.lnk"
      RMDir "$SMPROGRAMS\$AppStartMenuFolder"
    !insertmacro MUI_STARTMENU_WRITE_END
    Delete "$DESKTOP\${PRODUCTNAME}.lnk"
  ${EndIf}
!macroend

!macro NSIS_HOOK_PREINSTALL
  ; Tauri's generated NSIS section calls SetOutPath $INSTDIR immediately
  ; before this hook. Release that current-directory handle first; Windows
  ; cannot rename the product root while the installer itself is positioned
  ; inside its app child.
  SetOutPath "$TEMP"
  ; An installed release already records the exact canonical app directory in
  ; MANUPRODUCTKEY.  Do not rename the complete product root during an
  ; in-place reinstall or updater run: canonical, graph, secrets, WebView and
  ; runtime files may legitimately have short-lived handles even after the UI
  ; closes.  Only launcher-era roots that are not already registered as
  ; `%LOCALAPPDATA%\Angmoo\app` need the case-only migration below.
  ReadRegStr $R9 SHCTX "${MANUPRODUCTKEY}" ""
  ${GetParent} "$R9" $R8
  StrCmp "$R8" "$LOCALAPPDATA\Angmoo" angmoo_case_root_done 0
  ; Windows resolves LocalAppData paths case-insensitively but preserves the
  ; spelling of the first directory creation.  The launcher-era preview used
  ; `angmoo`, so a case-only round trip is required before the installer
  ; materializes the canonical `Angmoo\app` path.  No user data is copied or
  ; deleted by this operation.
  IfFileExists "$LOCALAPPDATA\angmoo" angmoo_case_root_exists angmoo_case_root_done
angmoo_case_root_exists:
  IfFileExists "$LOCALAPPDATA\Angmoo.__casefix__" angmoo_case_temp_conflict angmoo_case_begin
angmoo_case_temp_conflict:
  MessageBox MB_OK|MB_ICONSTOP \
    "Angmoo installation stopped because a stale product-root case migration directory exists."
  Abort
angmoo_case_begin:
  !insertmacro ANGMOO_VERIFY_NOT_REPARSE "$LOCALAPPDATA\angmoo" angmoo_case_root
  ClearErrors
  Rename "$LOCALAPPDATA\angmoo" "$LOCALAPPDATA\Angmoo.__casefix__"
  IfErrors angmoo_case_first_failed angmoo_case_second
angmoo_case_first_failed:
  MessageBox MB_OK|MB_ICONSTOP \
    "Angmoo installation could not normalize the LocalAppData product directory name."
  Abort
angmoo_case_second:
  ClearErrors
  Rename "$LOCALAPPDATA\Angmoo.__casefix__" "$LOCALAPPDATA\Angmoo"
  IfErrors angmoo_case_second_failed angmoo_case_root_done
angmoo_case_second_failed:
  ; Best-effort rollback preserves the original lowercase directory if the
  ; second case-only rename cannot complete.
  ClearErrors
  Rename "$LOCALAPPDATA\Angmoo.__casefix__" "$LOCALAPPDATA\angmoo"
  MessageBox MB_OK|MB_ICONSTOP \
    "Angmoo installation could not finish the LocalAppData directory case migration."
  Abort
angmoo_case_root_done:
  ReadRegStr $AngmooPreviousRegistrationRoot SHCTX "${MANUPRODUCTKEY}" ""
  ReadRegStr $AngmooPreviousDisplayVersion SHCTX "${UNINSTKEY}" "DisplayVersion"
  ReadRegStr $AngmooPreviousDisplayIcon SHCTX "${UNINSTKEY}" "DisplayIcon"
  ReadRegStr $AngmooPreviousInstallLocation SHCTX "${UNINSTKEY}" "InstallLocation"
  ReadRegStr $AngmooPreviousUninstallString SHCTX "${UNINSTKEY}" "UninstallString"
  ReadRegStr $AngmooPreviousMainBinaryName SHCTX "${UNINSTKEY}" "MainBinaryName"
  StrCpy $AngmooHadStartMenuShortcut 0
  !if "${STARTMENUFOLDER}" != ""
    IfFileExists "$SMPROGRAMS\$AppStartMenuFolder\${PRODUCTNAME}.lnk" 0 +2
      StrCpy $AngmooHadStartMenuShortcut 1
  !else
    IfFileExists "$SMPROGRAMS\${PRODUCTNAME}.lnk" 0 +2
      StrCpy $AngmooHadStartMenuShortcut 1
  !endif
  StrCpy $AngmooHadDesktopShortcut 0
  IfFileExists "$DESKTOP\${PRODUCTNAME}.lnk" 0 +2
    StrCpy $AngmooHadDesktopShortcut 1
  StrCpy $AngmooCanonicalAppRoot "$LOCALAPPDATA\Angmoo\app"
  StrCpy $INSTDIR $AngmooCanonicalAppRoot
  StrCpy $AngmooHadExistingApp 0
  IfFileExists "$AngmooCanonicalAppRoot\*.*" 0 +2
    StrCpy $AngmooHadExistingApp 1

  ; Tauri links the final host after beforeBundleCommand. Generate the signed
  ; payload manifest here, while NSIS is compiling and MAINBINARYSRCPATH points
  ; at the exact host that the following File directive will embed. This avoids
  ; attesting a stale pre-link host from target\release.
  !system 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "${ANGMOO_INSTALLER_HOOK_DIR}\..\scripts\prepare-installer-payload.ps1" -SkipHostBuild -HostPath "${MAINBINARYSRCPATH}" -SidecarPath "${ANGMOO_INSTALLER_HOOK_DIR}\binaries\angmoo-sidecar-x86_64-pc-windows-msvc.exe" -ManifestPath "${ANGMOO_INSTALLER_HOOK_DIR}\installer-payload.json" -ProductVersion "${VERSION}"' = 0

  ; Ask the installed host to close normally, then wait for both the host and
  ; its sidecar. Never force-kill or overwrite a live executable. A remaining
  ; process makes the installation fail closed instead of reporting a partial
  ; payload as successful.
  InitPluginsDir
  File /oname=$PLUGINSDIR\angmoo-installer-preflight.ps1 "${ANGMOO_INSTALLER_HOOK_DIR}\..\scripts\installer-preflight.ps1"
  File /oname=$PLUGINSDIR\angmoo-verify-installed-payload.ps1 "${ANGMOO_INSTALLER_HOOK_DIR}\..\scripts\verify-installed-payload.ps1"
  File /oname=$PLUGINSDIR\angmoo-installer-payload-transaction.ps1 "${ANGMOO_INSTALLER_HOOK_DIR}\..\scripts\installer-payload-transaction.ps1"
  nsExec::ExecToStack '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "$PLUGINSDIR\angmoo-installer-preflight.ps1" -AppRoot "$INSTDIR" -TimeoutSeconds 20'
  Pop $R7
  Pop $R6
  ${If} $R7 <> 0
    IfSilent angmoo_preflight_silent angmoo_preflight_interactive
angmoo_preflight_interactive:
    MessageBox MB_OK|MB_ICONSTOP \
      "Angmoo installation stopped because the existing Angmoo runtime did not close normally. Close Angmoo and retry."
    Goto angmoo_preflight_abort
angmoo_preflight_silent:
    Goto angmoo_preflight_abort
angmoo_preflight_abort:
    SetErrorLevel 23
    Quit
  ${EndIf}

  ; Classify and recover only the three installer-owned app transaction roots.
  ; The verified existing app stays in place until the complete new staging
  ; payload has passed hash and data-compatibility checks.
  nsExec::ExecToStack '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "$PLUGINSDIR\angmoo-installer-payload-transaction.ps1" -Action Prepare -ProductRoot "$LOCALAPPDATA\Angmoo" -VerifierPath "$PLUGINSDIR\angmoo-verify-installed-payload.ps1"'
  Pop $R7
  Pop $R6
  ${If} $R7 <> 0
    IfSilent angmoo_prepare_silent angmoo_prepare_interactive
angmoo_prepare_interactive:
    MessageBox MB_OK|MB_ICONSTOP \
      "Angmoo installation could not prepare a trustworthy app update. User data was not changed."
    Goto angmoo_prepare_abort
angmoo_prepare_silent:
    Goto angmoo_prepare_abort
angmoo_prepare_abort:
    SetErrorLevel 50
    Quit
  ${EndIf}

  ; Tauri's generated File, uninstaller, registry and shortcut instructions now
  ; write a complete candidate into staging. POSTINSTALL resets every durable
  ; registration to the canonical app root after atomic promotion.
  StrCpy $INSTDIR "$LOCALAPPDATA\Angmoo\app.__install_staging__"
  CreateDirectory "$INSTDIR"
  SetOutPath "$INSTDIR"
  File /a /oname=installer-payload.json "${ANGMOO_INSTALLER_HOOK_DIR}\installer-payload.json"
  File /a /oname=verify-installed-payload.ps1 "${ANGMOO_INSTALLER_HOOK_DIR}\..\scripts\verify-installed-payload.ps1"
  File /a /oname=installer-payload-transaction.ps1 "${ANGMOO_INSTALLER_HOOK_DIR}\..\scripts\installer-payload-transaction.ps1"
!macroend

!macro NSIS_HOOK_POSTINSTALL
  ; Verify the complete staged candidate before replacing the current app.
  nsExec::ExecToStack '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "$INSTDIR\verify-installed-payload.ps1" -AppRoot "$INSTDIR"'
  Pop $R7
  Pop $R6
  ${If} $R7 <> 0
    nsExec::ExecToLog '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "$PLUGINSDIR\angmoo-installer-payload-transaction.ps1" -Action RecordFailure -FailureCode installer_staging_digest_mismatch -ProductRoot "$LOCALAPPDATA\Angmoo" -VerifierPath "$PLUGINSDIR\angmoo-verify-installed-payload.ps1"'
    IfSilent angmoo_staging_verify_silent angmoo_staging_verify_interactive
angmoo_staging_verify_interactive:
    MessageBox MB_OK|MB_ICONSTOP \
      "Angmoo installation stopped because the staged app payload did not match this installer. The previous app and user data were preserved."
    Goto angmoo_staging_verify_abort
angmoo_staging_verify_silent:
    Goto angmoo_staging_verify_abort
angmoo_staging_verify_abort:
    !insertmacro ANGMOO_RESTORE_PREVIOUS_REGISTRATION
    SetErrorLevel 35
    Quit
  ${EndIf}

  ; The staged new sidecar, not NSIS and not the old installed executable,
  ; decides whether the active SQLite/Ladybug generations are readable.
  ; The packaged sidecar is a GUI-subsystem (--noconsole) executable. ExecWait
  ; is the native synchronous NSIS boundary for that payload: it waits for the
  ; real process exit code without attaching command-line output pipes.
  ExecWait '"$INSTDIR\angmoo-sidecar.exe" --installer-data-preflight --data-root "$LOCALAPPDATA\Angmoo" --legacy-data-root "$LOCALAPPDATA\com.angmoo.desktop" --runtime-root "$LOCALAPPDATA\Angmoo\runtime" --payload-manifest "$INSTDIR\installer-payload.json" --installer-result-path "$LOCALAPPDATA\Angmoo\runtime\installer-data-upgrade-result.json"' $R7
  ${If} $R7 <> 0
    nsExec::ExecToLog '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "$PLUGINSDIR\angmoo-installer-payload-transaction.ps1" -Action RecordFailure -FailureCode installer_embedded_data_incompatible -ProductRoot "$LOCALAPPDATA\Angmoo" -VerifierPath "$PLUGINSDIR\angmoo-verify-installed-payload.ps1"'
    IfSilent angmoo_data_preflight_silent angmoo_data_preflight_interactive
angmoo_data_preflight_interactive:
    MessageBox MB_OK|MB_ICONSTOP \
      "This Angmoo installer cannot safely read the existing local data version. No user data was changed."
    Goto angmoo_data_preflight_abort
angmoo_data_preflight_silent:
    Goto angmoo_data_preflight_abort
angmoo_data_preflight_abort:
    !insertmacro ANGMOO_RESTORE_PREVIOUS_REGISTRATION
    SetErrorLevel 41
    Quit
  ${EndIf}

  ; Promote by same-volume directory rename, preserving a verified previous app
  ; as backup. Mixed existing payloads are never trusted as rollback sources.
  ; Release NSIS's current-directory handle on staging before the helper
  ; renames that directory to the canonical app root.
  SetOutPath "$TEMP"
  nsExec::ExecToStack '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "$PLUGINSDIR\angmoo-installer-payload-transaction.ps1" -Action Promote -ProductRoot "$LOCALAPPDATA\Angmoo" -VerifierPath "$PLUGINSDIR\angmoo-verify-installed-payload.ps1"'
  Pop $R7
  Pop $R6
  ${If} $R7 <> 0
    IfSilent angmoo_promote_silent angmoo_promote_interactive
angmoo_promote_interactive:
    MessageBox MB_OK|MB_ICONSTOP \
      "Angmoo installation could not promote the verified app payload. The previous app and user data were preserved."
    Goto angmoo_promote_abort
angmoo_promote_silent:
    Goto angmoo_promote_abort
angmoo_promote_abort:
    !insertmacro ANGMOO_RESTORE_PREVIOUS_REGISTRATION
    SetErrorLevel 50
    Quit
  ${EndIf}

  ; From here on every durable registry entry, shortcut and finish-page action
  ; must target the canonical app path rather than staging.
  StrCpy $INSTDIR $AngmooCanonicalAppRoot
  SetOutPath "$TEMP"
  WriteRegStr SHCTX "${MANUPRODUCTKEY}" "" $INSTDIR
  WriteRegStr SHCTX "${UNINSTKEY}" "MainBinaryName" "${MAINBINARYNAME}.exe"
  WriteRegStr SHCTX "${UNINSTKEY}" "DisplayIcon" "$\"$INSTDIR\${MAINBINARYNAME}.exe$\""
  WriteRegStr SHCTX "${UNINSTKEY}" "InstallLocation" "$\"$INSTDIR$\""
  WriteRegStr SHCTX "${UNINSTKEY}" "UninstallString" "$\"$INSTDIR\uninstall.exe$\""
  ${If} $NoShortcutMode <> 1
    ${If} $UpdateMode <> 1
    ${OrIf} $AngmooHadStartMenuShortcut = 1
      !if "${STARTMENUFOLDER}" != ""
        CreateDirectory "$SMPROGRAMS\$AppStartMenuFolder"
        CreateShortcut "$SMPROGRAMS\$AppStartMenuFolder\${PRODUCTNAME}.lnk" "$INSTDIR\${MAINBINARYNAME}.exe"
      !else
        CreateShortcut "$SMPROGRAMS\${PRODUCTNAME}.lnk" "$INSTDIR\${MAINBINARYNAME}.exe"
      !endif
    ${EndIf}
  ${EndIf}
  ${If} $PassiveMode = 1
  ${OrIf} ${Silent}
    ${If} $NoShortcutMode <> 1
      ${If} $UpdateMode <> 1
      ${OrIf} $AngmooHadDesktopShortcut = 1
        CreateShortcut "$DESKTOP\${PRODUCTNAME}.lnk" "$INSTDIR\${MAINBINARYNAME}.exe"
      ${EndIf}
    ${EndIf}
  ${EndIf}

  ; Only the verified, promoted sidecar may invoke the existing copy-on-write
  ; SQLite generation upgrade and Ladybug canonical replay/rebuild.
  ExecWait '"$INSTDIR\angmoo-sidecar.exe" --installer-data-upgrade --data-root "$LOCALAPPDATA\Angmoo" --legacy-data-root "$LOCALAPPDATA\com.angmoo.desktop" --runtime-root "$LOCALAPPDATA\Angmoo\runtime" --payload-manifest "$INSTDIR\installer-payload.json" --installer-result-path "$LOCALAPPDATA\Angmoo\runtime\installer-data-upgrade-result.json"' $R7
  ${If} $R7 <> 0
    ; The new app is verified but its data migration failed. Restore the exact
    ; verified predecessor before restoring registration and reporting failure;
    ; never leave a new manifest paired with an older executable or vice versa.
    SetOutPath "$TEMP"
    nsExec::ExecToStack '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "$PLUGINSDIR\angmoo-installer-payload-transaction.ps1" -Action RestoreFailure -FailureCode installer_embedded_data_migration_failed -ResultPath "$LOCALAPPDATA\Angmoo\runtime\installer-data-upgrade-result.json" -ProductRoot "$LOCALAPPDATA\Angmoo" -VerifierPath "$PLUGINSDIR\angmoo-verify-installed-payload.ps1"'
    Pop $R5
    Pop $R4
    ${If} $R5 <> 0
      IfSilent angmoo_data_restore_silent angmoo_data_restore_interactive
angmoo_data_restore_interactive:
      MessageBox MB_OK|MB_ICONSTOP \
        "Angmoo local data could not be upgraded and the verified previous app could not be restored automatically. Existing data generations were preserved."
      Goto angmoo_data_restore_abort
angmoo_data_restore_silent:
      Goto angmoo_data_restore_abort
angmoo_data_restore_abort:
      SetErrorLevel 50
      Quit
    ${EndIf}
    !insertmacro ANGMOO_RESTORE_PREVIOUS_REGISTRATION
    IfSilent angmoo_data_upgrade_silent angmoo_data_upgrade_interactive
angmoo_data_upgrade_interactive:
    MessageBox MB_OK|MB_ICONSTOP \
      "Angmoo local data could not be upgraded safely. The verified previous app was restored and existing data generations were preserved."
    Goto angmoo_data_upgrade_abort
angmoo_data_upgrade_silent:
    Goto angmoo_data_upgrade_abort
angmoo_data_upgrade_abort:
    SetErrorLevel 42
    Quit
  ${EndIf}

  ; Retire staging/backup only after app and data validation both pass.
  nsExec::ExecToStack '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "$PLUGINSDIR\angmoo-installer-payload-transaction.ps1" -Action Finalize -ProductRoot "$LOCALAPPDATA\Angmoo" -VerifierPath "$PLUGINSDIR\angmoo-verify-installed-payload.ps1"'
  Pop $R7
  Pop $R6
  ${If} $R7 <> 0
    IfSilent angmoo_finalize_silent angmoo_finalize_interactive
angmoo_finalize_interactive:
    MessageBox MB_OK|MB_ICONSTOP \
      "Angmoo update validation passed, but installer cleanup did not finish. Rerun this installer before starting Angmoo."
    Goto angmoo_finalize_abort
angmoo_finalize_silent:
    Goto angmoo_finalize_abort
angmoo_finalize_abort:
    SetErrorLevel 50
    Quit
  ${EndIf}

  ; Remove only known files from the pre-contract preview app location. The
  ; new app directory and every user-data directory stay untouched.
  Delete "$LOCALAPPDATA\Angmoo\angmoo-desktop.exe"
  Delete "$LOCALAPPDATA\Angmoo\angmoo-sidecar.exe"
  Delete "$LOCALAPPDATA\Angmoo\THIRD_PARTY_NOTICES.md"
  Delete "$LOCALAPPDATA\Angmoo\uninstall.exe"
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  StrCpy $AngmooFullDeleteConfirmed 0
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

  ; Set this only after the user said Yes and every target was validated. The
  ; post-uninstall hook must never infer authorization from the checkbox.
  StrCpy $AngmooFullDeleteConfirmed 1

  ; Revalidate immediately before each recursive operation. The complete
  ; validation pass above guarantees that a pre-existing reparse trap aborts
  ; before any child is removed; these checks also narrow the replacement
  ; window between validation and deletion.
  !insertmacro ANGMOO_VERIFY_NOT_REPARSE "$LOCALAPPDATA\Angmoo\canonical" angmoo_delete_canonical
  RMDir /r "$LOCALAPPDATA\Angmoo\canonical"
  !insertmacro ANGMOO_VERIFY_NOT_REPARSE "$LOCALAPPDATA\Angmoo\graph" angmoo_delete_graph
  RMDir /r "$LOCALAPPDATA\Angmoo\graph"
  !insertmacro ANGMOO_VERIFY_NOT_REPARSE "$LOCALAPPDATA\Angmoo\search" angmoo_delete_search
  RMDir /r "$LOCALAPPDATA\Angmoo\search"
  !insertmacro ANGMOO_VERIFY_NOT_REPARSE "$LOCALAPPDATA\Angmoo\media" angmoo_delete_media
  RMDir /r "$LOCALAPPDATA\Angmoo\media"
  !insertmacro ANGMOO_VERIFY_NOT_REPARSE "$LOCALAPPDATA\Angmoo\secrets" angmoo_delete_secrets
  RMDir /r "$LOCALAPPDATA\Angmoo\secrets"
  !insertmacro ANGMOO_VERIFY_NOT_REPARSE "$LOCALAPPDATA\Angmoo\runtime" angmoo_delete_runtime
  RMDir /r "$LOCALAPPDATA\Angmoo\runtime"
  !insertmacro ANGMOO_VERIFY_NOT_REPARSE "$LOCALAPPDATA\Angmoo\logs" angmoo_delete_logs
  RMDir /r "$LOCALAPPDATA\Angmoo\logs"
  !insertmacro ANGMOO_VERIFY_NOT_REPARSE "$LOCALAPPDATA\Angmoo\webview" angmoo_delete_webview
  RMDir /r "$LOCALAPPDATA\Angmoo\webview"
angmoo_keep_local_data:
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  ; The marker belongs to the migration mechanism, not to user content. This
  ; removes the product root only when full deletion emptied it; keep-data
  ; uninstall leaves the non-empty data root intact.
  ${If} $AngmooFullDeleteConfirmed = 1
    Delete "$LOCALAPPDATA\Angmoo\localappdata-migration-v1.json"
    RMDir "$LOCALAPPDATA\Angmoo"
  ${EndIf}
!macroend
