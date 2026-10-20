# 자동 업데이트 배포

JBEdu FORM은 데이터도구실 고정 게시글에서 `JBEDU-FORM` 표식을 읽고, 새 버전의 설치파일을 내려받아 적용합니다. 정식 배포 버전은 0.0.1부터 시작하며, 이전 시험판의 `JBEDT-0006` 표식은 읽지 않습니다. 시험판에서 정식판으로 처음 바꿀 때는 설치파일을 직접 실행합니다.

## 최초 준비

- 개인키: `.signing\tauri.key`
- 공개키: `.signing\tauri.key.pub`
- 앱에 포함되는 공개키: `update-config.json`

개인키와 공개키는 별도로 안전하게 백업합니다. 기존 설치본은 현재 공개키로 서명된 설치파일만 업데이트로 인정하므로 키를 임의로 다시 만들면 안 됩니다.

GitHub 저장소의 **Settings → Secrets and variables → Actions**에 다음 저장소 시크릿을 등록합니다.

| 시크릿 | 값 |
|---|---|
| `TAURI_SIGNING_PRIVATE_KEY` | `.signing\tauri.key` 파일의 한 줄 전체 |
| `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` | 키 암호. 현재처럼 빈 암호 키라면 등록하지 않아도 됨 |

개인키는 다음 명령으로 클립보드에 복사할 수 있습니다.

```powershell
Get-Content C:\work\jb_quickpanel\tauri-prototype\.signing\tauri.key -Raw | Set-Clipboard
```

개인키는 Git에 올리지 않으며, GitHub Actions는 저장소 시크릿에서만 읽습니다.


## 1. GitHub Release 발행

1. 버전을 한 번에 올립니다.

```powershell
cd C:\work\jb_quickpanel
powershell -ExecutionPolicy Bypass -File .\tauri-prototype\set_version.ps1 0.0.1
```

2. 변경사항을 커밋하고 같은 버전의 태그를 푸시합니다.

```powershell
git add -A
git commit -m "chore: 버전 0.0.1"
git push
git tag v0.0.1
git push origin v0.0.1
```

3. GitHub Actions가 테스트, Python sidecar 빌드, Tauri NSIS 빌드와 서명을 실행합니다.
4. 완료되면 GitHub Release에 설치 EXE, 게시판용 ZIP, `.sig`, `latest.json`이 올라갑니다.

## 2. 교육청 게시판 연결

1. GitHub Release에서 `JBEduForm_v0.0.1.zip`과 `JBEduForm_v0.0.1_Setup.exe.sig`를 내려받습니다.
2. ZIP을 교육청 게시판의 고정 업데이트 게시글에 첨부하고 게시글을 저장합니다.
3. 저장된 첨부파일 링크 주소를 복사합니다.
4. 내려받은 `.sig`와 첨부 링크로 게시글 표식을 만듭니다.

```powershell
cd C:\work\jb_quickpanel\tauri-prototype
powershell -ExecutionPolicy Bypass -File .\print_board_marker.ps1 -Version 0.0.1 -SignaturePath "$env:USERPROFILE\Downloads\JBEduForm_v0.0.1_Setup.exe.sig" -DownloadUrl "https://www.jbe.go.kr/board/download.jbe?..."
```

5. 클립보드에 복사된 한 줄을 게시글 본문의 `JBEDU-FORM` 표식으로 사용합니다. 정식판 배포 때 처음 추가하며, 이후 정식판 업데이트 시 이 표식만 교체합니다.

```text
[업데이트정보]id=JBEDU-FORM|앱=JBEdu FORM (JB에듀 폼)|버전=0.0.1|다운로드=...|서명=...
```

## 주의 사항

- 버전은 현재 설치본보다 반드시 높아야 합니다.
- 게시판에는 빌드 결과 ZIP을 올리고, 같은 빌드에서 생성된 `.sig`를 사용합니다.
- ZIP 안에는 설치파일 EXE가 하나만 있어야 합니다.
- TLS 인증서 검증과 minisign 서명 검증은 끄지 않습니다.
- 업데이트 실패는 한글 작업을 중단시키지 않으며 설정 화면에서 다시 확인할 수 있습니다.

앱은 GitHub가 아니라 교육청 게시판의 이 표식을 확인합니다. GitHub Release만 발행하고 게시판 표식을 갱신하지 않으면 기존 사용자에게 자동 업데이트가 전달되지 않습니다.

## 로컬에서 직접 빌드

GitHub Actions를 사용하지 않고 현재 PC에서 같은 파일을 만들 때 사용합니다.

```powershell
cd C:\work\jb_quickpanel\tauri-prototype
powershell -ExecutionPolicy Bypass -File .\build_v4.ps1
```

게시판에는 GitHub Release 또는 로컬 빌드에서 나온 ZIP과 반드시 같은 빌드의 `.sig`를 함께 사용합니다.
