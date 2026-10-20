!define JB_INSTALLER_HOOK_DIR "${__FILEDIR__}"
!ifndef JB_LEGACY_UNINSTKEY
  !define JB_LEGACY_UNINSTKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\전북교육 한글 서식도우미"
!endif
!ifndef JB_LEGACY_PRODUCTKEY
  !define JB_LEGACY_PRODUCTKEY "Software\go\전북교육 한글 서식도우미"
!endif

!macro JB_REUSE_LEGACY_INSTALL
  Push $R0
  Push $R1
  ReadRegStr $R0 HKCU "${UNINSTKEY}" "MainBinaryName"
  ${If} $R0 == ""
  ${AndIf} $INSTDIR == "$LOCALAPPDATA\${PRODUCTNAME}"
    ReadRegStr $R0 HKCU "${JB_LEGACY_PRODUCTKEY}" ""
    ReadRegStr $R1 HKCU "${JB_LEGACY_UNINSTKEY}" "MainBinaryName"
    ${If} $R0 != ""
    ${AndIf} $R1 == "${MAINBINARYNAME}.exe"
      ${If} ${FileExists} "$R0\${MAINBINARYNAME}.exe"
      ${AndIf} ${FileExists} "$R0\uninstall.exe"
        StrCpy $INSTDIR $R0
        SetOutPath $INSTDIR
      ${EndIf}
    ${EndIf}
  ${EndIf}
  Pop $R1
  Pop $R0
!macroend

!macro JB_REMOVE_REPLACED_LEGACY_REGISTRATION
  Push $R0
  Push $R1
  ReadRegStr $R0 HKCU "${JB_LEGACY_PRODUCTKEY}" ""
  ReadRegStr $R1 HKCU "${JB_LEGACY_UNINSTKEY}" "MainBinaryName"
  ${If} $R0 == $INSTDIR
  ${AndIf} $R1 == "${MAINBINARYNAME}.exe"
    ReadRegStr $R1 HKCU "${UNINSTKEY}" "MainBinaryName"
    ${If} $R1 == "${MAINBINARYNAME}.exe"
      DeleteRegKey HKCU "${JB_LEGACY_UNINSTKEY}"
      DeleteRegKey HKCU "${JB_LEGACY_PRODUCTKEY}"
    ${EndIf}
  ${EndIf}
  Pop $R1
  Pop $R0
!macroend

!macro JB_STOP_INSTALLED_BACKEND
  ; The one-file Python backend can outlive the main window and lock its executable.
  !insertmacro CheckIfAppIsRunning "${MAINBINARYNAME}.exe" "${PRODUCTNAME}"
  InitPluginsDir
  File /oname=$PLUGINSDIR\stop-installed-backend.ps1 "${JB_INSTALLER_HOOK_DIR}\stop-installed-backend.ps1"
  ${If} ${RunningX64}
    StrCpy $R2 "$WINDIR\Sysnative\WindowsPowerShell\v1.0\powershell.exe"
  ${Else}
    StrCpy $R2 "$SYSDIR\WindowsPowerShell\v1.0\powershell.exe"
  ${EndIf}
  jb_backend_stop_retry:
  nsExec::ExecToStack '"$R2" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\stop-installed-backend.ps1" -InstallDir "$INSTDIR"'
  Pop $R0
  Pop $R1
  ${If} $R0 != 0
    IfSilent jb_backend_stop_abort 0
    MessageBox MB_ICONEXCLAMATION|MB_RETRYCANCEL "JB에듀 폼을 종료하지 못했습니다. 작업 중인 기능을 마친 후 프로그램을 완전히 종료하고 다시 시도해 주세요." IDRETRY jb_backend_stop_retry
    jb_backend_stop_abort:
    Abort
  ${EndIf}
!macroend

!macro NSIS_HOOK_PREINSTALL
  !insertmacro JB_REUSE_LEGACY_INSTALL
  !insertmacro JB_STOP_INSTALLED_BACKEND
  ; v4.0~v4.0.3 installers used a versioned product name and left one shortcut per version.
  Delete "$DESKTOP\전북교육 한글 서식도우미 v*.lnk"
  Delete "$SMPROGRAMS\전북교육 한글 서식도우미 v*.lnk"
  Delete "$SMPROGRAMS\전북교육 한글 서식도우미 (v*).lnk"
!macroend

!macro NSIS_HOOK_POSTINSTALL
  !insertmacro JB_REMOVE_REPLACED_LEGACY_REGISTRATION
  !insertmacro IsShortcutTarget "$DESKTOP\전북교육 한글 서식도우미.lnk" "$INSTDIR\${MAINBINARYNAME}.exe"
  Pop $R0
  ${If} $R0 == 1
    ${If} $NoShortcutMode <> 1
      Call CreateOrUpdateDesktopShortcut
    ${EndIf}
    Delete "$DESKTOP\전북교육 한글 서식도우미.lnk"
  ${EndIf}
  !insertmacro IsShortcutTarget "$SMPROGRAMS\전북교육 한글 서식도우미.lnk" "$INSTDIR\${MAINBINARYNAME}.exe"
  Pop $R0
  ${If} $R0 == 1
    Delete "$SMPROGRAMS\전북교육 한글 서식도우미.lnk"
  ${EndIf}
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  !insertmacro JB_STOP_INSTALLED_BACKEND
!macroend
