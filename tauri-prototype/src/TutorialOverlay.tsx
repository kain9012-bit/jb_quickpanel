import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, ArrowRight, Check, X } from "lucide-react";

export type TutorialDestination = {
  tab?: "style" | "edit" | "chars" | "symbol" | "forms" | "page";
  editTab?: "table" | "cell" | "text";
  settings?: boolean;
};

type TutorialStep = TutorialDestination & {
  selector: string;
  title: string;
  body: string;
  hwpOnly?: boolean;
  kedufineOnly?: boolean;
};

const STEPS: TutorialStep[] = [
  {
    selector: '[data-tour="target"]',
    title: "작업할 한글 창 선택",
    body: "작업 환경에 맞게 일반 한글 또는 K-에듀파인 기안창을 선택하세요. 연결되지 않으면 대상 한글 창을 클릭한 뒤 상단 새로고침을 누르세요.",
  },
  {
    selector: '[data-tour="window-layout"]',
    title: "한글과 나란히 배치",
    body: "누를 때마다 한글은 왼쪽, JB에듀 폼은 오른쪽으로 정렬합니다. 일반 한글 모드에서만 사용할 수 있습니다.",
    hwpOnly: true,
  },
  {
    selector: '[data-tour="manual"]',
    title: "매뉴얼 바로 열기",
    body: "매뉴얼을 누르면 기본 브라우저에서 사용 안내가 열립니다. 필요한 기능을 검색하고 화면 예시를 확인할 수 있습니다.",
  },
  {
    selector: '[data-tour="tabs"]',
    title: "기능 영역 이동",
    body: "필요한 작업의 탭을 선택하세요. 현재 모드에서 사용할 수 있는 탭만 표시됩니다.",
  },
  {
    selector: '[data-tour="auto-format-toolbar"]',
    title: "전체 서식 자동 지정",
    body: "AI 초안을 한글에 붙여 넣고 전체를 블록 지정한 뒤 ‘전체 서식 자동 지정하기’를 누르세요. 제목·본문·표 서식을 한 번에 적용합니다.",
    tab: "style",
    hwpOnly: true,
  },
  {
    selector: '[data-tour="auto-format-direct"]',
    title: "선택한 부분만 서식 적용",
    body: "바꿀 텍스트만 블록 지정하고 문서제목·1단계 제목·본문 등을 누르세요. 선택한 부분에 자동 서식 설정을 적용합니다.",
    tab: "style",
    hwpOnly: true,
  },
  {
    selector: '[data-tour="auto-format-settings"]',
    title: "자동 서식 설정과 저장",
    body: "‘서식 설정’에서 제목 양식·글꼴·크기·번호·앞 기호를 정하세요. 설정은 최대 10개까지 저장하고 위의 ‘사용할 설정’에서 골라 쓸 수 있습니다.",
    tab: "style",
    hwpOnly: true,
  },
  {
    selector: '[data-tour="manual-styles"]',
    title: "서식 수동 지정",
    body: "서식 카드를 누르면 현재 커서 위치에 제목박스·표박스 등의 틀이 들어갑니다. 아래 ‘내 서식 추가’로 자주 쓰는 틀을 등록할 수 있습니다.",
    tab: "style",
  },
  {
    selector: '[data-tour="manual-styles"] .favorite-toggle',
    title: "즐겨찾기로 앞에 배치",
    body: "카드의 별을 누르면 즐겨찾기로 앞쪽에 모입니다. 등록한 순서가 유지되며, 양식·심볼·편집용지에도 같은 방식으로 사용할 수 있습니다.",
    tab: "style",
  },
  {
    selector: '[data-tour="user-style"]',
    title: "내 서식 등록",
    body: "일반 한글에서 필요한 내용을 블록 지정한 뒤 내 서식으로 추가하세요. 등록한 HWP 서식은 일반 한글과 기안창에서 함께 사용할 수 있습니다.",
    tab: "style",
  },
  {
    selector: '[data-tour="table-tools"]',
    title: "표 작업",
    body: "한글에서 표나 셀을 선택한 뒤 선·배경색·행 높이·열 너비 등을 바꾸세요. 선택한 범위에 적용됩니다.",
    tab: "edit",
    editTab: "table",
  },
  {
    selector: '[data-tour="cell-images"]',
    title: "여러 셀에 그림 넣기",
    body: "셀 범위를 선택하고 맞춤 방식을 고른 뒤 그림 파일들을 선택하세요. ‘기존 그림 다시 맞춤’으로 이미 들어간 그림도 정리할 수 있습니다.",
    tab: "edit",
    editTab: "table",
    hwpOnly: true,
  },
  {
    selector: '[data-tour="cell-tools"]',
    title: "셀 정리",
    body: "한글 표에서 적용할 셀들을 마우스로 블록 지정한 뒤 사용합니다. 엑셀 붙여넣기 흔적, 앞뒤 공백, 셀 내용 찾아바꾸기와 문자 추가를 선택 범위 전체에 적용합니다.",
    tab: "edit",
    editTab: "cell",
    hwpOnly: true,
  },
  {
    selector: '[data-tour="text-tools"]',
    title: "글자 작업",
    body: "글자 블록이나 셀을 선택한 뒤 색·글꼴·크기를 바꾸세요. 아래에서 위첨자·아래첨자·첨자 해제도 적용할 수 있습니다. 자간 정리는 일반 한글에서 사용합니다.",
    tab: "edit",
    editTab: "text",
  },
  {
    selector: '[data-tour="characters"]',
    title: "문자표",
    body: "한글에서 커서를 둔 뒤 필요한 문자를 누르세요. 원문자·네모문자 숫자도 사용할 수 있고, ‘내 문자표 추가’로 자주 쓰는 문자를 묶어 둘 수 있습니다.",
    tab: "chars",
  },
  {
    selector: '[data-tour="character-actions"]',
    title: "글자 겹치기와 문자표 순서",
    body: "‘글자 겹치기’에서 30 같은 글자와 원·네모 모양을 선택해 넣으세요. ‘순서 변경’에서는 문자표 묶음을 위·아래로 옮길 수 있으며 순서가 저장됩니다.",
    tab: "chars",
  },
  {
    selector: '[data-tour="symbols"]',
    title: "심볼",
    body: "한글에서 그림을 넣을 위치에 커서를 둔 뒤 원하는 심볼을 선택하세요. 자주 쓰는 이미지는 내 심볼 추가로 등록해 함께 사용할 수 있습니다.",
    tab: "symbol",
    hwpOnly: true,
  },
  {
    selector: '[data-tour="forms"]',
    title: "양식",
    body: "‘현재 문서에 삽입’ 또는 ‘새 문서로 열기’를 고른 뒤 양식 카드를 누르세요. ‘내 양식 추가’로 블록 지정한 내용이나 한글 파일을 등록할 수 있습니다.",
    tab: "forms",
    hwpOnly: true,
  },
  {
    selector: '[data-tour="forms"]',
    title: "기안창 전용 양식",
    body: "내부결재·발송용에서 유형을 고르고 카드를 누르면 기안창 본문에 삽입됩니다. 제목은 별도로 입력하며, ‘내 기안문 양식 추가’로 자주 쓰는 본문을 저장할 수 있습니다.",
    tab: "forms",
    kedufineOnly: true,
  },
  {
    selector: '[data-tour="pages"]',
    title: "편집용지",
    body: "원하는 편집용지 카드를 누르면 용지 여백이 적용됩니다. 위·아래·왼쪽·오른쪽과 머리말·꼬리말 값을 직접 입력해 내 편집용지로 저장할 수도 있습니다.",
    tab: "page",
    hwpOnly: true,
  },
  {
    selector: '[data-tour="settings"]',
    title: "설정과 단축키",
    body: "항상 위 표시·시작 위치·자동 실행·탭 순서·단축키를 바꿀 수 있습니다. ‘튜토리얼 다시 보기’로 이 안내를 언제든 열 수 있습니다.",
  },
  {
    selector: '[data-tour="settings-backup"]',
    title: "설정과 내 자료 백업·복원",
    body: "PC를 옮길 때 ‘설정·내 자료 백업’으로 파일을 저장하고 새 PC에서 복원하세요. 자동 서식 설정·내 서식·즐겨찾기도 함께 옮깁니다.",
    settings: true,
  },
  {
    selector: '[data-tour="settings-updates"]',
    title: "업데이트 확인과 내역",
    body: "‘지금 확인’으로 새 버전을 확인하고 ‘업데이트 내역’에서 바뀐 기능을 볼 수 있습니다. 새 버전 준비 후 상단 안내에서 지금 또는 나중에 적용을 선택하세요.",
    settings: true,
  },
  {
    selector: '[data-tour="status"]',
    title: "작업 결과 확인",
    body: "연결 상태와 실행 결과, 실패 이유가 항상 이곳에 표시됩니다. 기능이 동작하지 않으면 먼저 이 안내를 확인하세요.",
  },
];

export function TutorialOverlay({
  open,
  targetMode,
  onNavigate,
  onClose,
}: {
  open: boolean;
  targetMode: "hwp" | "kedufine";
  onNavigate: (destination: TutorialDestination) => void;
  onClose: () => void;
}) {
  const steps = useMemo(
    () => STEPS.filter((step) => (targetMode === "hwp" || !step.hwpOnly)
      && (targetMode === "kedufine" || !step.kedufineOnly)),
    [targetMode],
  );
  const [index, setIndex] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);

  useEffect(() => {
    if (!open) return;
    setIndex(0);
  }, [open, targetMode]);

  useEffect(() => {
    if (!open) return;
    const step = steps[Math.min(index, steps.length - 1)];
    if (!step) return;
    onNavigate({ tab: step.tab, editTab: step.editTab, settings: step.settings });
    let frame: number;
    const update = () => {
      window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(() => {
        const element = document.querySelector(step.selector);
        if (!element) {
          update();
          return;
        }
        element.scrollIntoView({ behavior: "instant", block: "nearest" });
        const elementRect = element.getBoundingClientRect();
        let left = Math.max(8, elementRect.left);
        let top = Math.max(8, elementRect.top);
        let right = Math.min(window.innerWidth - 8, elementRect.right);
        let bottom = Math.min(window.innerHeight - 8, elementRect.bottom);
        // Only expose the part of a target visible inside its scroll containers.
        for (let parent = element.parentElement; parent; parent = parent.parentElement) {
          const style = window.getComputedStyle(parent);
          const bounds = parent.getBoundingClientRect();
          if (/^(auto|scroll|hidden|clip)$/.test(style.overflowX)) {
            left = Math.max(left, bounds.left + parent.clientLeft + 6);
            right = Math.min(right, bounds.left + parent.clientLeft + parent.clientWidth - 6);
          }
          if (/^(auto|scroll|hidden|clip)$/.test(style.overflowY)) {
            top = Math.max(top, bounds.top + parent.clientTop + 6);
            bottom = Math.min(bottom, bounds.top + parent.clientTop + parent.clientHeight - 6);
          }
        }
        setRect(new DOMRect(left, top, Math.max(0, right - left), Math.max(0, bottom - top)));
      });
    };
    update();
    window.addEventListener("resize", update);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", update);
    };
  }, [index, onNavigate, open, steps]);

  if (!open || !steps.length) return null;
  const step = steps[Math.min(index, steps.length - 1)];
  const cardWidth = Math.min(390, window.innerWidth - 28);
  const estimatedHeight = 230;
  const cardTop = rect
    ? Math.max(14, Math.min(window.innerHeight - estimatedHeight - 14,
      rect.bottom + 14 + estimatedHeight < window.innerHeight ? rect.bottom + 14 : rect.top - estimatedHeight - 14))
    : Math.max(14, window.innerHeight / 2 - estimatedHeight / 2);
  const cardLeft = rect
    ? Math.max(14, Math.min(window.innerWidth - cardWidth - 14, rect.left))
    : Math.max(14, (window.innerWidth - cardWidth) / 2);
  const dismiss = () => {
    setIndex(0);
    setRect(null);
    onClose();
  };

  return (
    <div className="tutorial-layer" role="dialog" aria-modal="true" aria-label="처음 사용 안내">
      {rect && (
        <div
          className="tutorial-spotlight"
          data-target-selector={step.selector}
          style={{ top: rect.top - 6, left: rect.left - 6, width: rect.width + 12, height: rect.height + 12 }}
        />
      )}
      <section className="tutorial-card" style={{ top: cardTop, left: cardLeft, width: cardWidth }}>
        <div className="tutorial-progress">
          <span>{index + 1} / {steps.length}</span>
          <button type="button" onClick={dismiss} aria-label="안내 닫기"><X size={18} /></button>
        </div>
        <strong>{step.title}</strong>
        <p>{step.body}</p>
        <div className="tutorial-actions">
          <button type="button" className="secondary-command" onClick={() => setIndex((value) => value - 1)} disabled={index === 0}>
            <ArrowLeft size={15} /> 이전
          </button>
          {index === steps.length - 1 ? (
            <button type="button" className="primary-command" onClick={dismiss}><Check size={15} /> 시작하기</button>
          ) : (
            <button type="button" className="primary-command" onClick={() => setIndex((value) => value + 1)}>다음 <ArrowRight size={15} /></button>
          )}
        </div>
      </section>
    </div>
  );
}
