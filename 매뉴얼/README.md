# 사용자 매뉴얼 관리

설명 원본은 `원본/content.json`, 화면과 PDF 생성기는 `도구/build-manual.cjs`입니다.
HTML과 PDF는 동일한 원본을 사용하며 HTML은 이미지를 포함한 단일 파일로 생성합니다.
사용자 설정을 읽거나 실제 한글 문서를 변경하지 않고, 격리된 자료와 실제 React 화면으로 캡처합니다.

## 업데이트 절차

1. 새 기능 또는 바뀐 동작을 `원본/content.json`에 반영합니다. 버튼 이름은 실제 UI와 맞춥니다.
2. `tauri-prototype`에서 `npm run build` 후 `npm run manual:build -- --reviewed`를 실행합니다.
3. `배포본`의 HTML과 PDF 내용을 확인합니다. 검토 기록은 `원본/review.json`에 저장됩니다.
4. 일반 배포 빌드에서는 `build_v4.ps1`이 매뉴얼을 다시 생성합니다. 설명 검토 대상 코드가 바뀌었는데 검토 기록을 갱신하지 않으면 빌드를 중단합니다.

버전 표기는 package.json을 읽어 자동으로 갱신합니다. 기능 설명 자체를 코드로 추측하여 작성하지는 않습니다.
새 버전의 공지와 매뉴얼은 역할이 다르므로 기능의 실제 사용법을 원본에 반영해야 합니다.
HTML/PDF는 별도 배포자료와 설치 리소스로 함께 생성합니다.
앱 상단 ‘매뉴얼’과 설정의 ‘사용자 매뉴얼’은 설치된 HTML을 기본 브라우저로 엽니다.
자동 서식의 ‘사용방법’에서도 해당 항목으로 이동할 수 있습니다.
변경 기록은 설치된 CHANGELOG.md를 열며, 한글 처리 로직과는 별개입니다.

## 실행 환경

- 프론트엔드 빌드 의존성 및 기존 Python 백엔드 의존성
- Playwright와 Chromium. `MANUAL_PLAYWRIGHT_PATH`로 Playwright 모듈 경로를 지정할 수 있습니다.
- Codex 번들 런타임의 Playwright가 있으면 자동으로 사용합니다.
- 외부 환경에서는 Playwright를 설치하고 Chromium을 준비한 뒤 실행합니다.
- `MANUAL_PYTHON`으로 Python 실행파일을 지정할 수 있습니다.

```powershell
npm run manual:check
npm run build
npm run manual:build -- --reviewed
```

## 폴더 구조

- `원본`: 설명·디자인·화면 자료·검토 기록
- `도구`: HTML/PDF 생성과 검사 도구
- `배포본`: 사용자에게 전달할 HTML/PDF

최종 HTML: `배포본/전북교육_한글_서식도우미_사용자매뉴얼_v.<버전>.html`
최종 PDF: `배포본/전북교육_한글_서식도우미_사용자매뉴얼_v.<버전>.pdf`
배포 빌드에서도 이 폴더를 사용합니다. release 폴더에는 매뉴얼 복사본을 따로 만들지 않습니다.
설치용 복사본은 생성기가 `tauri-prototype/src-tauri/manual/index.html`, `manual/manual.pdf`,
`support/CHANGELOG.md`에 준비합니다. 이 폴더는 생성물이며 원본을 직접 편집하지 않습니다.
Tauri는 `JB_APP_RESOURCE_DIR`로 설치 리소스 위치를 백엔드에 전달합니다.
