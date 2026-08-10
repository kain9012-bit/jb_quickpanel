# 전북교육 한글 서식도우미 v4.0

Python/Tk 기반 v3.4의 기능을 Tauri + React 화면으로 전환한 정식 `v4.0`입니다. 한글 COM 작업은 검증된 Python 브리지와 앱에 포함된 영구 sidecar가 담당합니다.

## 구현된 기능

- 일반 한글 / K-에듀파인 기안창 대상 전환과 자동 재연결
- 기본 서식 및 사용자 서식 삽입, 파일·현재 블록 등록, 이름·미리보기 관리
- 태그형·무태그형 서식 자동 지정, 기존 한글 표 보존, 표 삽입 뒤 본문 위치 복귀, 작업 중지
- 20개 표 작업, 셀 범위 기억, 공백·엑셀 붙여넣기 흔적 정리, 찾아바꾸기, 앞·뒤 문자 추가
- 셀별 여러 그림 삽입과 기존 그림 다시 맞춤
- 글자색·글꼴·크기, 줄 단위 자간 정리 1·2단계와 자간 초기화
- 사용자 문자표 우선 표시 및 편집, 그림 심볼 삽입
- 기본·사용자 양식과 편집용지 적용, 여백 직접 등록 및 관리
- 독립 창 열기·숨기기 단축키와 문서 기능 전역 단축키, 트레이 최소화, 중복 실행 방지
- 항상 위, 시작 위치·마지막 위치 기억, Windows 자동 실행·트레이 시작, 버전별 시작 메뉴 갱신
- 튜토리얼, 업데이트 안내 준비, 설정·오류 기록·문서 바로 열기

K-에듀파인 모드에서는 지원되는 탭과 기능만 표시하며, 자간 정리·셀 정리·그림·양식·편집용지는 숨깁니다.

## 구조

- `src/`: React 사용자 화면
- `src-tauri/`: Tauri 창, 트레이, 중복 실행 방지, 전역 단축키, Python sidecar 관리
- `backend/`: JSON 명령 서버와 Tauri 전용 한글 브리지
- 기존 저장소의 `src/jb_quickpanel/`: 검증된 한글·K-에듀파인 COM 브리지와 기능 로직 재사용

사용자 설정과 사용자 서식 데이터는 기존 버전과 같은 `%APPDATA%\JbHwpHelper` 위치를 사용하므로 버전이 바뀌어도 유지됩니다.

## 개발 실행

```powershell
cd C:\work\jb_quickpanel\tauri-prototype
pnpm install
pnpm tauri:dev
```

개발 실행은 저장소의 `.venv\Scripts\python.exe`를 먼저 사용하고, 없으면 PATH의 `python`을 사용합니다. Python에는 `pywin32`가 필요하며 한글 프로그램을 먼저 열어 두어야 실제 기능을 확인할 수 있습니다.

## 검사

```powershell
python -m unittest backend.test_server backend.test_auto_format_runner backend.test_tauri_hwp_bridge backend.test_full_features
pnpm build
cd src-tauri
cargo check
```

## 배포 빌드

정식 배포판은 Python COM 서버와 기본 서식·양식·심볼 자료를 sidecar로 묶은 뒤 Tauri NSIS 설치파일로 생성합니다.

```powershell
cd C:\work\jb_quickpanel\tauri-prototype
powershell -ExecutionPolicy Bypass -File .\build_v4.ps1
```

완성된 사용자용 파일은 저장소의 `release\전북교육 한글 서식도우미 v4.0 설치파일.exe`와 `release\전북교육 한글 서식도우미 v4.0.zip`에 생성됩니다. 사용자 PC에는 Python이 설치되어 있지 않아도 됩니다.