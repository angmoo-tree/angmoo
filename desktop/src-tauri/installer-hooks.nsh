; ER6 uninstaller policy:
; - silent uninstall always preserves local data;
; - interactive uninstall requires an explicit second confirmation to remove it;
; - MSI uninstall also preserves local data because it has no equivalent prompt.
!macro NSIS_HOOK_PREUNINSTALL
  IfSilent angmoo_keep_local_data 0
  MessageBox MB_YESNO|MB_ICONQUESTION \
    "Keep Angmoo local data (Worlds, Characters, posts, graph, and credentials)?" \
    IDYES angmoo_keep_local_data
  MessageBox MB_YESNO|MB_ICONEXCLAMATION \
    "Permanently remove all Angmoo local data from this Windows account?" \
    IDNO angmoo_keep_local_data
  RMDir /r "$LOCALAPPDATA\com.angmoo.desktop"
angmoo_keep_local_data:
!macroend
