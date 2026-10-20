export type ReleaseEntry = {
  tool: string;
  items: string[];
};

export type ReleaseNote = {
  version: string;
  added: ReleaseEntry[];
  changed: ReleaseEntry[];
};

/**
 * 설정의 업데이트 내역과 업데이트 직후 안내에서 함께 사용하는 사용자용 기록.
 * 새 버전을 위에 추가하고 개발·배포 내부 변경은 제외한다.
 */
export const RELEASE_NOTES: ReleaseNote[] = [
  {
    version: "0.0.7",
    added: [],
    changed: [{ tool: "셀 정리", items: ["앞뒤 공백 정리·셀마다 문자 붙이기에서 기존 굵기·글자색·줄바꿈 유지", "공백만 삭제하거나 앞뒤에만 삽입하도록 개선, 기존 셀 선택·찾아바꾸기는 유지"] }],
  },
  {
    version: "0.0.6",
    added: [],
    changed: [{ tool: "서식 자동 지정", items: ["기관명·날짜·음수·파일명과 표 내용이 잘못 바뀌는 경우 수정", "새 결과를 확인한 뒤 원문 교체, 실패·중지 시 원문 유지 개선", "그림·도형이 함께 선택되면 변경 전 안내하고 중단"] }],
  },
  {
    version: "0.0.5",
    added: [],
    changed: [{ tool: "서식 자동 지정", items: ["마침표 없는 숫자 제목 인식 및 제목 번호 중복·누락 수정", "세로선 하나로 구분한 2열 텍스트 표도 자동 변환", "제목·본문·참고·표 안의 마크다운 강조 표시 제거"] }],
  },
  {
    version: "0.0.4",
    added: [{ tool: "편집용지", items: ["기본 보고서 A4 세로·가로 편집용지 제공", "‘문서 전체’·‘현재 페이지만’ 적용 범위 선택 추가", "내 편집용지에서 세로·가로 방향 저장 및 미리보기 지원"] }],
    changed: [{ tool: "현재 페이지 적용", items: ["필요한 앞뒤 구역만 나누어 적용하고 다른 구역의 용지 설정 유지", "내용이 넘치면 해당 구역 안에서 다음 페이지로 이어짐"] }],
  },
  {
    version: "0.0.3",
    added: [{ tool: "문자표", items: ["순서 변경에 ‘맨 위로 이동’·‘맨 아래로 이동’ 버튼 추가"] }],
    changed: [{ tool: "내 문자표", items: ["새로 추가한 문자표를 맨 위에 표시하고 기존 묶음 순서는 유지", "삭제 확인창을 프로그램 내 ‘내 문자표 삭제’ 창으로 변경"] }],
  },
  {
    version: "0.0.2",
    added: [],
    changed: [
      { tool: "자간 정리", items: ["단어 중간 줄넘김·짧은 마지막 줄을 실제 줄 배치로 확인하고 최소 자간으로 조정", "해결되지 않는 조정은 원래 자간으로 복원하고 반복 실행 시 과도한 조정 방지", "번호·앞 기호·괄호 항목명과 글꼴·장평·문장 내용 유지", "표 안 일부 텍스트 블록은 선택한 글자만 처리"] },
    ],
  },
  {
    version: "0.0.1",
    added: [],
    changed: [
      { tool: "정식 배포", items: ["프로그램 이름을 ‘JBEdu FORM (JB에듀 폼)’으로 변경", "정식 배포 버전을 0.0.1부터 시작", "기존 기능·설정·사용자 자료·백업 호환 유지"] },
      { tool: "튜토리얼", items: ["나란히 배치·매뉴얼과 현재 기능을 실제 버튼 위치에서 안내", "자동 서식 설정·즐겨찾기·글자 겹치기·문자표 순서·백업·업데이트 안내 보완", "일반 한글·기안창 모드에 맞는 기능만 표시"] },
    ],
  },
  {
    version: "4.2.5",
    added: [{ tool: "창 배치", items: ["일반 한글 모드에서 ‘한글과 나란히 배치’ 버튼 추가", "누를 때마다 한글은 왼쪽, 서식도우미는 오른쪽에 정렬", "한글 창이 있는 모니터와 작업표시줄 제외 영역을 기준으로 배치"] }],
    changed: [],
  },
  {
    version: "4.2.4",
    added: [
      { tool: "글자 작업", items: ["위첨자·아래첨자·첨자 해제 버튼 추가", "글자 블록·선택한 셀에 적용하며 해제 시 다른 글자 서식 유지"] },
      { tool: "문자표", items: ["네모문자 숫자(1~20) 추가", "글자 겹치기에서 원·네모 모양과 글자를 골라 삽입", "‘순서 변경’에서 분류 묶음을 위·아래로 이동 / 재실행·백업 복원 후에도 순서 유지"] },
    ],
    changed: [],
  },
  {
    version: "4.2.3",
    added: [{ tool: "표 작업", items: ["‘글자처럼 취급’·‘글자처럼 취급 해제’ 버튼 추가", "선택한 표·그림 또는 커서가 들어 있는 표의 개체 설정 변경"] }],
    changed: [{ tool: "표 작업", items: ["새 버튼 아이콘을 기존 표 그림 스타일로 통일", "아이콘 크기를 유지하면서 위아래 여백을 줄여 카드 높이를 기존의 3/4로 축소"] }],
  },
  {
    version: "4.2.2",
    added: [{ tool: "표 작업", items: ["‘표 그리기’ 버튼을 눌러 한글·기안창에서 마우스로 표 그리기 시작"] }],
    changed: [],
  },
  {
    version: "4.2.1",
    added: [{ tool: "즐겨찾기", items: ["서식·양식·심볼·편집용지 카드의 별을 누르면 앞쪽에 배치", "즐겨찾기는 등록한 순서를 유지하며 재실행·업데이트·백업 복원 후에도 저장"] }],
    changed: [{ tool: "심볼", items: ["비전·슬로건·이미지 분류 탭을 편집도구와 같은 디자인으로 통일"] }],
  },
  {
    version: "4.2.0",
    added: [
      {
        tool: "K-에듀파인 양식",
        items: ["기안문 본문 예시 11종을 내부결재·발송용으로 분류", "본문 텍스트 삽입과 사용자 기안문 텍스트 등록"],
      },
    ],
    changed: [
      {
        tool: "K-에듀파인 양식",
        items: ["서식 탭은 두 모드 모두 HWP만 사용하고 블록 지정으로 추가", "일반 한글 양식은 기존 파일 방식 유지"],
      },
    ],
  },
  {
    version: "4.1.8",
    added: [],
    changed: [
      {
        tool: "자동 서식 설정",
        items: ["설정은 최대 10개까지 추가 가능", "저장에 실패하면 설정창을 유지"],
      },
      {
        tool: "안정성",
        items: ["자동 서식 작업 중단·실패에 대비한 원본 선택 영역 복구 파일 생성", "이전 버전 백업의 자동 서식 설정 복원 개선"],
      },
    ],
  },
  {
    version: "4.1.7",
    added: [
      {
        tool: "서식 자동 지정",
        items: [
          "자동 서식 설정을 여러 개 저장하고 상황에 맞게 선택",
          "기존 설정을 복제한 뒤 필요한 부분만 바꾸어 새 설정으로 저장",
        ],
      },
    ],
    changed: [
      {
        tool: "자동 서식 설정",
        items: ["서식 탭에서 사용할 설정을 바로 전환", "기존 단일 설정은 기본 설정으로 자동 이전"],
      },
    ],
  },
  {
    version: "4.1.6",
    added: [
      {
        tool: "업데이트 안내",
        items: [
          "업데이트 후 처음 실행하면 위쪽 띠에서 새 버전의 변경 내용 확인",
          "설정의 업데이트 내역에서 버전별 변경 내용 확인",
        ],
      },
    ],
    changed: [
      {
        tool: "자동 업데이트",
        items: ["새 버전을 미리 받아 둔 뒤 지금 적용 또는 나중에 적용 선택"],
      },
    ],
  },
  {
    version: "4.1.5",
    added: [
      {
        tool: "백업과 복원",
        items: [
          "설정·단축키·자동 서식 설정과 사용자 자료를 하나의 백업 파일로 저장",
          "PC를 바꾸어도 백업 파일로 설정과 내 자료를 한 번에 복원",
        ],
      },
    ],
    changed: [
      {
        tool: "백업과 복원",
        items: ["복원 직전 상태 자동 보관", "손상되거나 올바르지 않은 백업 파일 차단"],
      },
    ],
  },
  {
    version: "4.1.4",
    added: [],
    changed: [
      {
        tool: "안정성",
        items: [
          "한글이 장시간 응답하지 않을 때 서식도우미가 계속 멈춰 있지 않도록 개선",
          "시간이 초과된 작업의 중복 실행 방지",
          "작업 실패 내용을 오류 기록에 저장",
        ],
      },
    ],
  },
  {
    version: "4.1.3",
    added: [],
    changed: [
      {
        tool: "편집도구 · 글자작업",
        items: [
          "표 안의 텍스트 일부 선택과 셀 블록 선택을 구분",
          "텍스트 일부를 선택하면 해당 글자에만 서식 적용",
        ],
      },
    ],
  },
  {
    version: "4.1.2",
    added: [],
    changed: [
      {
        tool: "서식 수동 지정",
        items: ["서식을 넣은 뒤 줄 끝으로 이동하고 새 문단을 만들도록 개선"],
      },
    ],
  },
  {
    version: "4.1.1",
    added: [],
    changed: [
      {
        tool: "양식",
        items: ["양식이 다음 페이지로 밀리지 않고 현재 커서 위치에 들어가도록 개선"],
      },
    ],
  },
  {
    version: "4.1.0",
    added: [],
    changed: [
      {
        tool: "편집도구 · 글자작업",
        items: ["여러 셀을 선택해도 글꼴·글자 크기·글자색을 모든 선택 셀에 적용"],
      },
      {
        tool: "문자표",
        items: ["특수문자를 넣은 직후 한글 문서에 계속 입력할 수 있도록 개선"],
      },
    ],
  },
  {
    version: "4.0.9",
    added: [
      {
        tool: "심볼",
        items: ["내 심볼 추가와 등록한 심볼 이름 변경·삭제 기능"],
      },
    ],
    changed: [
      {
        tool: "교육비전·슬로건",
        items: ["교육비전과 슬로건 이미지를 최신 자료로 교체"],
      },
    ],
  },
  {
    version: "4.0.8",
    added: [],
    changed: [
      {
        tool: "한글 연결",
        items: [
          "한글이 여러 개 실행 중일 때 화면에 보이는 작업 문서를 우선 연결",
          "숨은 한글 문서에 기능이 잘못 적용되지 않도록 보호",
        ],
      },
    ],
  },
  {
    version: "4.0.7",
    added: [
      {
        tool: "서식 자동 지정",
        items: ["문서제목·1~3단계 제목·본문·참고를 선택 영역에 개별 적용하는 버튼"],
      },
    ],
    changed: [
      {
        tool: "서식 탭",
        items: ["전체 자동 지정과 수동 지정을 구분해 화면 구성 정리"],
      },
    ],
  },
  {
    version: "4.0.6",
    added: [
      {
        tool: "자동 서식 설정",
        items: [
          "기존 보고서의 문서제목·1단계 제목 양식을 블록 지정해 등록",
          "문서제목·1단계 제목의 표 서식 없음 선택",
        ],
      },
    ],
    changed: [
      {
        tool: "사용자 자료 관리",
        items: ["제목 양식·내 서식·내 양식·내 편집용지의 관리 미리보기 개선"],
      },
    ],
  },
  {
    version: "4.0.5",
    added: [
      {
        tool: "자동 서식 설정",
        items: [
          "문서 구조별 글꼴·크기·굵기·번호·앞 기호 설정",
          "표 안 글자의 글꼴과 크기 설정",
          "Windows에 설치된 글꼴 검색과 직접 입력",
        ],
      },
    ],
    changed: [],
  },
  {
    version: "4.0.4",
    added: [],
    changed: [
      {
        tool: "서식 자동 지정",
        items: ["태그가 없는 AI 초안을 문서 구조로 분석해 태그형과 같은 방식으로 서식 적용"],
      },
    ],
  },
  {
    version: "4.0.3",
    added: [
      {
        tool: "양식",
        items: ["현재 문서에 삽입과 새 문서로 열기 선택"],
      },
    ],
    changed: [
      {
        tool: "설치",
        items: ["업데이트 설치 시 바탕화면 바로가기가 중복되지 않도록 개선"],
      },
    ],
  },
  {
    version: "4.0.2",
    added: [],
    changed: [
      {
        tool: "화면",
        items: ["창 하단이 작업표시줄 위에 맞도록 실행 높이 조정", "편집용지 미리보기와 카드 배치 개선"],
      },
    ],
  },
  {
    version: "4.0.1",
    added: [
      {
        tool: "자동 업데이트",
        items: ["새 버전 설치파일을 미리 받고 적용 시점을 선택하는 기능"],
      },
    ],
    changed: [
      {
        tool: "셀에 그림 넣기",
        items: ["한글 버전에 따라 그림 삽입이 실패하던 문제 해결"],
      },
    ],
  },
];

export function compareVersion(a: string, b: string) {
  const normalize = (value: string) => value.trim().replace(/^[vV]\.?(?=\d)/, "");
  const pa = normalize(a).split(".").map((part) => Number.parseInt(part, 10) || 0);
  const pb = normalize(b).split(".").map((part) => Number.parseInt(part, 10) || 0);
  for (let index = 0; index < Math.max(pa.length, pb.length); index += 1) {
    const difference = (pa[index] ?? 0) - (pb[index] ?? 0);
    if (difference) return difference;
  }
  return 0;
}

export function notesBetween(from: string, to: string): ReleaseNote[] {
  return RELEASE_NOTES.filter(
    (note) => compareVersion(note.version, to) <= 0
      && (from ? compareVersion(note.version, from) > 0 : compareVersion(note.version, to) === 0),
  );
}
