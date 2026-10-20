Unicode true
!include LogicLib.nsh
!include x64.nsh

; Test only backend cleanup, without closing the user's real application.
!macro CheckIfAppIsRunning executableName productName
!macroend
!include "..\src-tauri\installer-hooks.nsh"
!define MAINBINARYNAME "installer-backend-test"
!define PRODUCTNAME "Installer backend test"

Name "Installer backend test"
OutFile "..\..\.codex_tmp\installer-backend-test.exe"
InstallDir "$TEMP\jb-backend-test-disabled"
RequestExecutionLevel user
SilentInstall silent
SilentUnInstall silent

Section
  IfFileExists "$INSTDIR\binaries\jb_hwp_backend.exe" +3
    SetErrorLevel 2
    Quit
  !insertmacro JB_STOP_INSTALLED_BACKEND
  WriteUninstaller "$INSTDIR\uninstall-test.exe"
SectionEnd

Section Uninstall
  !insertmacro JB_STOP_INSTALLED_BACKEND
SectionEnd
