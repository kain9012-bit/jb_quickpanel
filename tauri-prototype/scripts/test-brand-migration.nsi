Unicode true
!include LogicLib.nsh
!define JB_LEGACY_UNINSTKEY "${TESTKEY}\legacy-uninstall"
!define JB_LEGACY_PRODUCTKEY "${TESTKEY}\legacy-product"
!define UNINSTKEY "${TESTKEY}\current-uninstall"
!define MAINBINARYNAME "jb-hwp-helper"
!define PRODUCTNAME "JBEdu FORM (JB에듀 폼)"
!include "..\src-tauri\installer-hooks.nsh"

Name "Isolated brand migration test"
OutFile "${TESTOUTPUT}"
InstallDir "C:\work\.codex_tmp\brand-migration-disabled"
RequestExecutionLevel user
SilentInstall silent
Var TestRoot
Var LegacyDir

Section
  StrCpy $TestRoot $INSTDIR
  StrCpy $LegacyDir "$TestRoot\legacy"
  CreateDirectory $LegacyDir
  FileOpen $R0 "$LegacyDir\${MAINBINARYNAME}.exe" w
  FileWrite $R0 "test"
  FileClose $R0
  FileOpen $R0 "$LegacyDir\uninstall.exe" w
  FileWrite $R0 "test"
  FileClose $R0
  WriteRegStr HKCU "${JB_LEGACY_PRODUCTKEY}" "" $LegacyDir
  WriteRegStr HKCU "${JB_LEGACY_UNINSTKEY}" "MainBinaryName" "${MAINBINARYNAME}.exe"
  StrCpy $INSTDIR "$LOCALAPPDATA\${PRODUCTNAME}"
  !insertmacro JB_REUSE_LEGACY_INSTALL
  ${If} $INSTDIR != $LegacyDir
    SetErrorLevel 11
    Quit
  ${EndIf}

  ; A failed/incomplete installation must retain the previous registration.
  !insertmacro JB_REMOVE_REPLACED_LEGACY_REGISTRATION
  ReadRegStr $R0 HKCU "${JB_LEGACY_UNINSTKEY}" "MainBinaryName"
  ${If} $R0 != "${MAINBINARYNAME}.exe"
    SetErrorLevel 12
    Quit
  ${EndIf}
  WriteRegStr HKCU "${UNINSTKEY}" "MainBinaryName" "${MAINBINARYNAME}.exe"
  !insertmacro JB_REMOVE_REPLACED_LEGACY_REGISTRATION
  ReadRegStr $R0 HKCU "${JB_LEGACY_UNINSTKEY}" "MainBinaryName"
  ${If} $R0 != ""
    SetErrorLevel 13
    Quit
  ${EndIf}

  WriteRegStr HKCU "${JB_LEGACY_PRODUCTKEY}" "" $LegacyDir
  WriteRegStr HKCU "${JB_LEGACY_UNINSTKEY}" "MainBinaryName" "${MAINBINARYNAME}.exe"
  StrCpy $INSTDIR "$LOCALAPPDATA\${PRODUCTNAME}"
  !insertmacro JB_REUSE_LEGACY_INSTALL
  ${If} $INSTDIR != "$LOCALAPPDATA\${PRODUCTNAME}"
    SetErrorLevel 14
    Quit
  ${EndIf}
  DeleteRegKey HKCU "${UNINSTKEY}"
  StrCpy $INSTDIR "$TestRoot\custom"
  !insertmacro JB_REUSE_LEGACY_INSTALL
  ${If} $INSTDIR != "$TestRoot\custom"
    SetErrorLevel 15
    Quit
  ${EndIf}
  !insertmacro JB_REMOVE_REPLACED_LEGACY_REGISTRATION
  ReadRegStr $R0 HKCU "${JB_LEGACY_UNINSTKEY}" "MainBinaryName"
  ${If} $R0 != "${MAINBINARYNAME}.exe"
    SetErrorLevel 16
    Quit
  ${EndIf}
  WriteRegStr HKCU "${JB_LEGACY_UNINSTKEY}" "MainBinaryName" "other.exe"
  StrCpy $INSTDIR "$LOCALAPPDATA\${PRODUCTNAME}"
  !insertmacro JB_REUSE_LEGACY_INSTALL
  ${If} $INSTDIR != "$LOCALAPPDATA\${PRODUCTNAME}"
    SetErrorLevel 17
    Quit
  ${EndIf}
  WriteRegStr HKCU "${JB_LEGACY_UNINSTKEY}" "MainBinaryName" "${MAINBINARYNAME}.exe"
  Delete "$LegacyDir\uninstall.exe"
  !insertmacro JB_REUSE_LEGACY_INSTALL
  ${If} $INSTDIR != "$LOCALAPPDATA\${PRODUCTNAME}"
    SetErrorLevel 18
    Quit
  ${EndIf}
  SetErrorLevel 0
SectionEnd
