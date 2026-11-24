Unicode true
Name "Local Services Helper"
Caption "Local Services Helper Setup"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\Local Services Helper"
RequestExecutionLevel user
ManifestDPIAware true

VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "Local Services Helper"
VIAddVersionKey "FileDescription" "Local Services Helper Setup"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "LegalCopyright" "Local Services contributors"

!include "MUI2.nsh"
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_TITLE "Local Services Helper is ready"
!define MUI_FINISHPAGE_TEXT "Return to the Local Services extension in Chrome, then select Check connection."
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

!define ChromeHost "Software\Google\Chrome\NativeMessagingHosts\io.github.ejoliet.local_services"
!define UninstallKey "Software\Microsoft\Windows\CurrentVersion\Uninstall\LocalServicesHelper"

Section "Install helper"
  SetShellVarContext current
  SetRegView 64
  SetOutPath "$INSTDIR"
  File /oname=local-services-helper.exe "${PAYLOAD}"
  nsExec::ExecToStack '"$INSTDIR\local-services-helper.exe" --write-windows-manifest "$INSTDIR"'
  Pop $0
  Pop $1
  ${If} $0 != 0
    MessageBox MB_ICONSTOP "The helper configuration could not be saved. $1"
    Abort
  ${EndIf}
  ClearErrors
  WriteRegStr HKCU "${ChromeHost}" "" "$INSTDIR\host.json"
  ${If} ${Errors}
    MessageBox MB_ICONSTOP "Chrome setup could not be saved for this Windows user."
    Abort
  ${EndIf}
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "${UninstallKey}" "DisplayName" "Local Services Helper"
  WriteRegStr HKCU "${UninstallKey}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UninstallKey}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegDWORD HKCU "${UninstallKey}" "NoModify" 1
  WriteRegDWORD HKCU "${UninstallKey}" "NoRepair" 1
SectionEnd

Section "Uninstall"
  SetShellVarContext current
  SetRegView 64
  DeleteRegKey HKCU "${ChromeHost}"
  DeleteRegKey HKCU "${UninstallKey}"
  Delete "$INSTDIR\host.json"
  Delete "$INSTDIR\local-services-helper.exe"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
SectionEnd
