# JBEdu FORM 개발 안내

제품 소개와 사용 방법은 [루트 README](../README.md), 최신 변경 내용은 [변경 기록](CHANGELOG.md)을 참고합니다. `tauri-prototype`이라는 폴더 이름은 초기 전환 당시의 이름이며, 현재 설치형 앱의 소스가 이곳에 있습니다.

## 구성

| 위치 | 역할 |
| --- | --- |
| `src/` | React·TypeScript 화면, 튜토리얼, 즐겨찾기, 업데이트 안내 |
| `src-tauri/` | Rust 창·트레이·단축키·업데이트·Python 백엔드 관리 |
| `backend/` | JSON 명령 서버, Tauri 전용 한글 연결, 테스트 |
| `../src/jb_quickpanel/` | 한글·기안창 COM 브리지, 문서 편집과 사용자 자료 관리 |
| `../매뉴얼/` | 설명 원본, 실제 화면 캡처와 HTML·PDF 생성 |

사용자 설정과 자료는 `%APPDATA%\JbHwpHelper`를 사용합니다. 저장 경로나 백업 형식을 바꿀 때는 기존 사용자 자료 호환성을 확인해야 합니다.

## 개발 실행

Windows, Python 3.12, Node.js, pnpm, Rust MSVC 및 Windows C++ 빌드 도구를 준비합니다. pnpm은 `package.json`의 `packageManager`에 지정된 버전을 사용합니다.

```powershell
# 저장소 루트
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
cd tauri-prototype
pnpm install --frozen-lockfile
pnpm tauri:dev
```

개발 실행은 저장소의 `.venv\Scripts\python.exe`를 우선 사용하고, 없으면 PATH의 Python을 사용합니다. 실제 문서 기능은 설치형 한글 또는 K-에듀파인 기안창이 열린 상태에서 확인합니다.

## 검사

```powershell
# 저장소 루트
.\.venv\Scripts\python.exe -m pip install pytest
$env:PYTHONPATH = "$PWD;$PWD\tauri-prototype"
.\.venv\Scripts\python.exe -m pytest --import-mode=importlib -q tests tauri-prototype/backend
cd tauri-prototype
pnpm build
pnpm manual:check
cargo check --manifest-path src-tauri/Cargo.toml
```

단위 테스트와 빌드 성공은 실제 한글 버전별 동작 확인을 대신하지 않습니다. 문서 선택, 서식 삽입, 표·셀 편집, 문자 입력과 모드 전환은 설치본에서도 확인합니다.

## 매뉴얼 갱신

기능이나 화면이 달라지면 `../매뉴얼/원본/content.json`의 설명을 먼저 검토합니다.

```powershell
pnpm build
pnpm manual:build -- --reviewed
pnpm manual:check
```

설명 검토 기록이 현재 코드와 다르면 배포 빌드를 중단합니다. 생성된 HTML·PDF와 화면 캡처는 직접 편집하지 않습니다. 자세한 환경 설정은 [매뉴얼 관리](../매뉴얼/README.md)를 참고합니다.

## 설치파일 빌드

`build_v4.ps1`은 버전·매뉴얼 확인, Python 테스트, sidecar 생성, 프론트엔드·Rust 검사, 매뉴얼 생성, NSIS 설치파일 빌드와 서명을 수행합니다.

```powershell
cd tauri-prototype
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_v4.ps1
```

결과는 루트의 `release`와 `exe버전관리` 폴더에 생성되며 Git 추적에서 제외됩니다. 사용자 PC에는 별도 Python 설치가 필요하지 않습니다.

업데이트 서명 개인키는 로컬 `.signing` 폴더와 GitHub Actions 시크릿으로 관리합니다. 개인키·비밀번호·사용자 자료를 커밋하지 않습니다. 키가 없으면 정식 서명 설치본을 만들 수 없습니다.

## 배포

일반 소스 푸시는 설치본을 발행하지 않습니다. 배포할 버전을 확정한 후 `set_version.ps1`로 버전을 맞추고, 검증한 커밋에 `v`로 시작하는 버전 태그를 붙여 푸시합니다. 태그 푸시는 [Release 워크플로](../.github/workflows/release.yml)를 실행합니다.

GitHub Release에는 설치 EXE·ZIP·서명·매뉴얼과 `latest.json`을 발행합니다. 교육청 게시판을 통한 자동 업데이트는 ZIP 게시와 업데이트 표식 갱신이 별도로 필요합니다. 서명키 등록과 게시판 작업은 [AUTO_UPDATE.md](AUTO_UPDATE.md)를 따릅니다.
