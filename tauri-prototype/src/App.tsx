import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { getCurrentWindow } from "@tauri-apps/api/window";
import { isRegistered, register, unregister } from "@tauri-apps/plugin-global-shortcut";
import {
  AlignHorizontalSpaceAround,
  ArrowDown,
  ArrowDownToLine,
  ArrowUp,
  ArrowUpToLine,
  ArrowUpDown,
  Brush,
  BookOpen,
  Check,
  ChevronDown,
  ChevronUp,
  CircleHelp,
  Combine,
  Columns2,
  Copy,
  Download,
  Eraser,
  FileImage,
  FilePlus2,
  FileText,
  History,
  ImagePlus,
  Link,
  LoaderCircle,
  Minus,
  PaintBucket,
  PartyPopper,
  Pencil,
  Plus,
  RefreshCw,
  RotateCcw,
  Settings,
  Square,
  Star,
  Subscript,
  Superscript,
  Type,
  Table2,
  Trash2,
  Upload,
  Unlink,
  WandSparkles,
  X,
} from "lucide-react";
import {
  applyWindowPosition,
  arrangeHwpWindows,
  cancelAutoFormat,
  focusExternalWindow,
  requestBackend,
  readWindowLayoutState,

  setWindowInputMode,
  setWindowPreferences,
} from "./backend";
import {
  applyPreparedUpdate,
  displayUpdateError,
  displayVersion,
  prepareUpdate,
  preparedUpdateVersion,
} from "./updater";
import { ReleaseNotesDialog } from "./ReleaseNotesDialog";
import { RELEASE_NOTES } from "./releaseNotes";
import { TutorialOverlay, type TutorialDestination } from "./TutorialOverlay";
import { TableToolImage, TableToolPreview } from "./TableToolPreview";
import { useReleaseNotice } from "./useReleaseNotice";
import { cardFavoriteKey, orderFavoriteCards, type CardFavorites, type FavoriteKind } from "./favorites";
import type {
  AppSettings,
  AutoFormatProfile,
  AutoFormatRoleStyle,
  AutoFormatSettings,
  AutoTitleAnalysis,
  AutoTitleTemplate,
  BackendResponse,
  CellSelection,
  CharacterGroup,
  ContentItem,
  IntegrationStatus,
  PageMargins,
  PictureSymbolGroup,
  PictureSymbolItem,
  TableToolItem,
} from "./backend";

type TabId = "style" | "edit" | "chars" | "symbol" | "forms" | "page";
type EditTabId = "table" | "cell" | "text";
type ContentKind = "style" | "form" | "page";
type FormUseMode = "insert" | "new_document";
type KedufineCategory = "internal" | "outgoing" | "legacy";
type KedufineForm = { key: string; id: string; title: string; category: KedufineCategory; preview: string; body: string; user_item: boolean; legacy: boolean };
type KedufineFormDraft = { id?: string; title: string; category: "internal" | "outgoing"; body: string };

const VERSION = "v.0.0.7";
const MAX_AUTO_FORMAT_PROFILES = 10;

const DEFAULT_MARGINS: PageMargins = {
  top: 10,
  header: 10,
  left: 20,
  gutter: 0,
  right: 20,
  footer: 10,
  bottom: 15,
};
const DEFAULT_AUTO_FORMAT_SETTINGS: AutoFormatSettings = {
  document_title_template: "auto-title-builtin:document_title",
  title_template: "auto-title-builtin:title",
  roles: {
    document_title: { font: "HY헤드라인M", size: 23, bold: true },
    title: { font: "HY헤드라인M", size: 16, bold: false, marker: "number_dot", custom_marker: "" },
    subtitle: { font: "휴먼명조", size: 14, bold: true, marker: "hangul_dot", custom_marker: "" },
    subsubtitle: { font: "휴먼명조", size: 13, bold: true, marker: "number_paren", custom_marker: "" },
    body: { font: "휴먼명조", size: 13, bold: false, marker: "dash", custom_marker: "" },
    table: { font: "굴림체", size: 12, bold: false },
    reference: { font: "맑은 고딕", size: 11, bold: false, marker: "reference", custom_marker: "" },
  },
};

type AutoFormatRoleKey = keyof AutoFormatSettings["roles"];
type DirectAutoFormatRoleKey = Exclude<AutoFormatRoleKey, "table">;

const HEADING_MARKER_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "number_dot", label: "1. 2. 3." },
  { value: "number_paren", label: "1) 2) 3)" },
  { value: "hangul_dot", label: "가. 나. 다." },
  { value: "hangul_paren", label: "가) 나) 다)" },
  { value: "roman_upper_dot", label: "Ⅰ. Ⅱ. Ⅲ." },
  { value: "roman_lower_dot", label: "ⅰ. ⅱ. ⅲ." },
  { value: "number_circle", label: "① ② ③" },
  { value: "circle", label: "○ (동일 기호)" },
  { value: "square", label: "□ (동일 기호)" },
  { value: "dash", label: "- (동일 기호)" },
  { value: "custom", label: "직접 입력" },
  { value: "none", label: "없음" },
];
const HEADING_ROLE_KEYS = ["title", "subtitle", "subsubtitle"] as const;
const HEADING_SEQUENCE_MARKERS = new Set([
  "number_dot", "number_paren", "hangul_dot", "hangul_paren",
  "roman_upper_dot", "roman_lower_dot", "number_circle",
]);

const AUTO_FORMAT_ROLES: Array<{
  key: AutoFormatRoleKey;
  label: string;
  example: string;
  markerOptions?: Array<{ value: string; label: string }>;
}> = [
  {
    key: "document_title",
    label: "문서제목",
    example: "보고서·계획서 제목",
  },
  {
    key: "title",
    label: "1단계 제목",
    example: "1. 추진 배경",
    markerOptions: HEADING_MARKER_OPTIONS,
  },
  {
    key: "subtitle",
    label: "2단계 제목",
    example: "가. 세부 내용",
    markerOptions: HEADING_MARKER_OPTIONS,
  },
  {
    key: "subsubtitle",
    label: "3단계 제목",
    example: "1) 추진 방법",
    markerOptions: HEADING_MARKER_OPTIONS,
  },
  {
    key: "body",
    label: "본문",
    example: "- 세부 설명",
    markerOptions: [
      { value: "dash", label: "-" },
      { value: "asterisk", label: "*" },
      { value: "circle", label: "○" },
      { value: "square", label: "□" },
      { value: "bullet", label: "•" },
      { value: "custom", label: "직접 입력" },
      { value: "none", label: "없음" },
    ],
  },
  {
    key: "reference",
    label: "참고",
    example: "※ 참고 사항",
    markerOptions: [
      { value: "reference", label: "※" },
      { value: "asterisk", label: "*" },
      { value: "custom", label: "직접 입력" },
      { value: "none", label: "없음" },
    ],
  },
  {
    key: "table",
    label: "표 안 글자",
    example: "표 전체 텍스트",
  },
];
const DIRECT_AUTO_FORMAT_ROLES: Array<{ key: DirectAutoFormatRoleKey; label: string }> = [
  { key: "document_title", label: "문서제목" },
  { key: "title", label: "1단계 제목" },
  { key: "subtitle", label: "2단계 제목" },
  { key: "subsubtitle", label: "3단계 제목" },
  { key: "body", label: "본문" },
  { key: "reference", label: "참고" },
];

function cloneAutoFormatSettings(value: AutoFormatSettings): AutoFormatSettings {
  return {
    ...value,
    roles: {
      document_title: { ...value.roles.document_title },
      title: { ...value.roles.title },
      subtitle: { ...value.roles.subtitle },
      subsubtitle: { ...value.roles.subsubtitle },
      body: { ...value.roles.body },
      table: { ...value.roles.table },
      reference: { ...value.roles.reference },
    },
  };
}

function cloneAutoFormatProfile(profile: AutoFormatProfile): AutoFormatProfile {
  return {
    ...profile,
    settings: cloneAutoFormatSettings(profile.settings),
  };
}

function cloneAutoFormatProfiles(profiles: AutoFormatProfile[]): AutoFormatProfile[] {
  return profiles.map(cloneAutoFormatProfile);
}

function createAutoFormatProfileId() {
  const random = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `profile-${random}`;
}

const DEFAULT_SETTINGS: AppSettings = {
  always_on_top: true,
  target_mode: "hwp",
  start_mode: "hwp",
  start_position: "top_right",
  remember_window_position: false,
  last_geometry: "",
  close_to_tray: false,
  start_minimized: false,
  tutorial_completed: false,
  check_updates_on_startup: true,
  toggle_hotkey: "Ctrl+Alt+H",
  global_hotkeys_enabled: true,
  global_hotkeys: {},
  card_favorites: { style: [], form: [], kedufine_form: [], symbol: [], page: [] },
  character_group_order: [],
  tab_order: ["style", "edit", "chars", "symbol", "forms", "page"],
  auto_format: cloneAutoFormatSettings(DEFAULT_AUTO_FORMAT_SETTINGS),
  active_auto_format_profile: "default",
  auto_format_profiles: [
    {
      id: "default",
      name: "기본 설정",
      settings: cloneAutoFormatSettings(DEFAULT_AUTO_FORMAT_SETTINGS),
    },
  ],
};
const TAB_LABELS: Record<TabId, string> = {
  style: "서식",
  edit: "편집도구",
  chars: "문자표",
  symbol: "심볼",
  forms: "양식",
  page: "편집용지",
};
const FONT_ROWS = [
  { name: "HY헤드라인M", sizes: [15, 16, 17, 18, 20, 25, 30] },
  { name: "휴먼명조", sizes: [11, 12, 13, 14, 15, 17, 20] },
  { name: "맑은 고딕", sizes: [9, 10, 11, 12, 13, 14, 15] },
  { name: "굴림체", sizes: [9, 10, 11, 12, 13, 14, 15] },
];

type HotkeyAction = {
  id: string;
  category: string;
  label: string;
  command?: string;
  args?: Record<string, unknown>;
  special?: "auto_format" | "insert_images";
};

function normalizeShortcutForTauri(shortcut: string): string {
  return shortcut
    .split("+")
    .map((part) => part.trim().toLocaleLowerCase() === "win" ? "Super" : part.trim())
    .join("+");
}

function shortcutFromEvent(event: React.KeyboardEvent): string | null {
  if (["Control", "Alt", "Shift", "Meta"].includes(event.key)) return null;
  const modifiers: string[] = [];
  if (event.ctrlKey) modifiers.push("Ctrl");
  if (event.altKey) modifiers.push("Alt");
  if (event.shiftKey) modifiers.push("Shift");
  if (event.metaKey) modifiers.push("Win");
  if (!modifiers.length) return "";

  const aliases: Record<string, string> = {
    " ": "Space",
    ArrowUp: "Up",
    ArrowDown: "Down",
    ArrowLeft: "Left",
    ArrowRight: "Right",
    Escape: "Escape",
  };
  let key = aliases[event.key] ?? event.key;
  if (key.length === 1 && /[a-z]/i.test(key)) key = key.toUpperCase();
  return [...modifiers, key].join("+");
}

type ActionButtonProps = {
  label: string;
  icon: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  tone?: "default" | "accent" | "danger";
};

function ActionButton({
  label,
  icon,
  onClick,
  disabled,
  tone = "default",
}: ActionButtonProps) {
  return (
    <button
      type="button"
      className={`action-button is-${tone}`}
      onClick={onClick}
      disabled={disabled}
    >
      <span className="action-icon" aria-hidden="true">{icon}</span>
      <span>{label}</span>
    </button>
  );
}

function Modal({
  title,
  children,
  onClose,
  wide = false,
  className = "",
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
  wide?: boolean;
  className?: string;
}) {
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className={`modal ${wide ? "is-wide" : ""} ${className}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="modal-header">
          <h2>{title}</h2>
          <button type="button" className="icon-button is-borderless" onClick={onClose} aria-label="닫기">
            <X size={18} />
          </button>
        </header>
        <div className="modal-body">{children}</div>
      </section>
    </div>
  );
}

function FavoriteCard({ children, title, active, busy, onToggle }: {
  children: ReactNode;
  title: string;
  active: boolean;
  busy: boolean;
  onToggle: () => void;
}) {
  const label = `${title} 즐겨찾기 ${active ? "해제" : "추가"}`;
  return (
    <div className="favorite-card">
      {children}
      <button type="button" className={`favorite-toggle${active ? " is-active" : ""}`}
        title={label} aria-label={label} aria-pressed={active} disabled={busy}
        onClick={(event) => { event.stopPropagation(); onToggle(); }}>
        <Star size={17} />
      </button>
    </div>
  );
}

function ContentGrid({
  items,
  kind,
  busy,
  onRun,
  favorites = [],
  onToggleFavorite,
}: {
  items: ContentItem[];
  kind: ContentKind;
  busy: boolean;
  onRun: (item: ContentItem) => void;
  favorites?: string[];
  onToggleFavorite?: (key: string) => void;
}) {
  const gridClassName = kind === "form"
    ? "content-card-grid form-grid"
    : kind === "page"
      ? "content-card-grid page-grid"
      : "content-card-grid";

  return (
    <div className={gridClassName}>
      {orderFavoriteCards(items, favorites).map((item) => {
        const card = <button
          type="button"
          className="content-card"
          key={item.key}
          disabled={busy}
          onClick={() => onRun(item)}
        >
          <span className="content-preview">
            {kind === "page" ? (
              <PagePreview margins={item.margins ?? DEFAULT_MARGINS} orientation={item.orientation} />
            ) : item.preview ? (
              <img src={item.preview} alt="" draggable={false} />
            ) : (
              <FileText size={32} />
            )}
          </span>
          <span className="content-title">{item.title}</span>
          {item.user_item && kind !== "page" && <span className="user-badge">내 {TAB_LABELS[kind === "form" ? "forms" : kind]}</span>}
        </button>;
        return onToggleFavorite ? (
          <FavoriteCard key={item.key} title={item.title} active={favorites.includes(item.key)}
            busy={busy} onToggle={() => onToggleFavorite(item.key)}>{card}</FavoriteCard>
        ) : card;
      })}
    </div>
  );
}

function PagePreview({ margins, orientation = "portrait" }: { margins: PageMargins; orientation?: "portrait" | "landscape" }) {
  return (
    <span className={`page-preview ${orientation === "landscape" ? "is-landscape" : ""}`} aria-hidden="true">
      <span className="margin-value is-top">{margins.top}</span>
      <span className="margin-value is-left">{margins.left}</span>
      <span className="page-sheet">
        <span className="margin-value is-header">{margins.header}</span>
        <span className="page-word">용지</span>
        <span className="margin-value is-footer">{margins.footer}</span>
      </span>
      <span className="margin-value is-right">{margins.right}</span>
      <span className="margin-value is-bottom">{margins.bottom}</span>
    </span>
  );
}

export default function App() {
  const windowLayoutActiveRef = useRef(false);
  const windowLayoutChangingRef = useRef(false);
  const windowLayoutTimer = useRef<number | undefined>(undefined);
  const [activeTab, setActiveTab] = useState<TabId>("style");
  const contentRef = useRef<HTMLElement>(null);
  const [editTab, setEditTab] = useState<EditTabId>("table");
  const [styles, setStyles] = useState<ContentItem[]>([]);
  const [autoTitleTemplates, setAutoTitleTemplates] = useState<AutoTitleTemplate[]>([]);
  const [forms, setForms] = useState<ContentItem[]>([]);
  const [kedufineForms, setKedufineForms] = useState<KedufineForm[]>([]);
  const [kedufineCategory, setKedufineCategory] = useState<KedufineCategory>("internal");
  const [kedufineFormDraft, setKedufineFormDraft] = useState<KedufineFormDraft | null>(null);
  const [kedufineFormManagerOpen, setKedufineFormManagerOpen] = useState(false);
  const [pages, setPages] = useState<ContentItem[]>([]);
  const [tableTools, setTableTools] = useState<TableToolItem[]>([]);
  const [characterGroups, setCharacterGroups] = useState<CharacterGroup[]>([]);
  const [pictureGroups, setPictureGroups] = useState<PictureSymbolGroup[]>([]);
  const [fontNames, setFontNames] = useState<string[]>(FONT_ROWS.map((font) => font.name));
  const [pictureGroupIndex, setPictureGroupIndex] = useState(0);
  const [pictureSymbolManagerOpen, setPictureSymbolManagerOpen] = useState(false);
  const [settings, setSettings] = useState<AppSettings>(DEFAULT_SETTINGS);
  const [integration, setIntegration] = useState<IntegrationStatus>({
    startup: false,
    start_menu: false,
    settings_dir: "",
  });
  const [connected, setConnected] = useState(false);
  const [busy, setBusy] = useState("");
  const busyRef = useRef("");
  const [stopRequested, setStopRequested] = useState(false);
  const [status, setStatus] = useState("Python COM 서버를 준비하는 중입니다.");
  const [updateStatus, setUpdateStatus] = useState(`현재 버전 ${VERSION} · 업데이트 확인 대기`);
  const [updateReadyVersion, setUpdateReadyVersion] = useState("");
  const [updateDismissed, setUpdateDismissed] = useState(false);
  const [updateBusy, setUpdateBusy] = useState(false);
  const updateBusyRef = useRef(false);
  const [hadUserData, setHadUserData] = useState<boolean | null>(null);
  const [releaseDetailsOpen, setReleaseDetailsOpen] = useState(false);
  const [releaseHistoryOpen, setReleaseHistoryOpen] = useState(false);
  const releaseNotice = useReleaseNotice(VERSION, hadUserData);
  const [selection, setSelection] = useState<CellSelection>({
    active: false,
    dragging: false,
    label: "선택된 셀 범위 없음",
  });
  const polling = useRef(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [autoFormatHelpOpen, setAutoFormatHelpOpen] = useState(false);
  const [autoFormatSettingsOpen, setAutoFormatSettingsOpen] = useState(false);
  const [autoTitleRegistration, setAutoTitleRegistration] = useState<(AutoTitleAnalysis & {
    name: string;
    error?: string;
  }) | null>(null);
  const [autoTitleManagerRole, setAutoTitleManagerRole] = useState<"document_title" | "title" | null>(null);
  const [autoTitleSelectionGuideRole, setAutoTitleSelectionGuideRole] = useState<"document_title" | "title" | null>(null);
  const [autoFormatRoleGuide, setAutoFormatRoleGuide] = useState<DirectAutoFormatRoleKey | null>(null);
  const [autoFormatDraft, setAutoFormatDraft] = useState<AutoFormatSettings>(
    cloneAutoFormatSettings(DEFAULT_AUTO_FORMAT_SETTINGS),
  );
  const [autoFormatProfilesDraft, setAutoFormatProfilesDraft] = useState<AutoFormatProfile[]>(
    cloneAutoFormatProfiles(DEFAULT_SETTINGS.auto_format_profiles),
  );
  const [autoFormatProfileIdDraft, setAutoFormatProfileIdDraft] = useState("default");
  const [hotkeyOpen, setHotkeyOpen] = useState(false);
  const [hotkeySearch, setHotkeySearch] = useState("");
  const [capturingHotkey, setCapturingHotkey] = useState("");
  const [capturingToggleHotkey, setCapturingToggleHotkey] = useState(false);
  const [toggleHotkeyError, setToggleHotkeyError] = useState("");
  const [tutorialOpen, setTutorialOpen] = useState(false);
  const [sourceKind, setSourceKind] = useState<"form" | null>(null);
  const [managerKind, setManagerKind] = useState<ContentKind | null>(null);
  const [nameDialog, setNameDialog] = useState<{
    title: string;
    initial: string;
    submitLabel: string;
    onSubmit: (value: string) => Promise<void>;
  } | null>(null);
  const [nameValue, setNameValue] = useState("");
  const [pageEditor, setPageEditor] = useState<ContentItem | "new" | null>(null);
  const [pageTitle, setPageTitle] = useState("");
  const [pageMargins, setPageMargins] = useState<PageMargins>(DEFAULT_MARGINS);
  const [pageOrientation, setPageOrientation] = useState<"portrait" | "landscape">("portrait");
  const [pageScope, setPageScope] = useState<"document" | "page">("document");
  const [symbolEditor, setSymbolEditor] = useState<CharacterGroup | "new" | null>(null);
  const [symbolTitle, setSymbolTitle] = useState("");
  const [symbolValues, setSymbolValues] = useState("");
  const [symbolDeleteTarget, setSymbolDeleteTarget] = useState<CharacterGroup | null>(null);
  const [symbolDeleteError, setSymbolDeleteError] = useState("");
  const [characterOrderEditing, setCharacterOrderEditing] = useState(false);
  const [composeOpen, setComposeOpen] = useState(false);
  const [composeValue, setComposeValue] = useState("");
  const [composeShape, setComposeShape] = useState<"circle" | "square">("circle");
  const [composeError, setComposeError] = useState("");
  const [findText, setFindText] = useState("");
  const [replaceText, setReplaceText] = useState("");
  const [addText, setAddText] = useState("");
  const [imageMode, setImageMode] = useState("fit_inside");
  const [formUseMode, setFormUseMode] = useState<FormUseMode>("insert");

  const orderedCharacterGroups = useMemo(() => {
    const ranks = new Map(settings.character_group_order.map((id, index) => [id, index]));
    const fallback = ranks.size;
    return characterGroups.map((group, index) => ({ group, rank: ranks.get(group.id) ?? fallback + index }))
      .sort((first, second) => first.rank - second.rank)
      .map(({ group }) => group);
  }, [characterGroups, settings.character_group_order]);

  const modalOpen = settingsOpen || hotkeyOpen || tutorialOpen || autoFormatHelpOpen || autoFormatSettingsOpen || pictureSymbolManagerOpen || kedufineFormManagerOpen || releaseDetailsOpen || releaseHistoryOpen || Boolean(
    sourceKind || managerKind || nameDialog || pageEditor || symbolEditor || symbolDeleteTarget || composeOpen || kedufineFormDraft || autoTitleRegistration || autoTitleManagerRole || autoTitleSelectionGuideRole || autoFormatRoleGuide,
  );

  useEffect(() => {
    void setWindowInputMode(modalOpen).catch(() => undefined);
  }, [modalOpen]);

  const activateCellTextInput = useCallback(() => {
    void (async () => {
      await setWindowInputMode(true);
      window.setTimeout(() => {
        void setWindowInputMode(false).catch(() => undefined);
      }, 80);
    })().catch(() => undefined);
  }, []);

  const execute = useCallback(async <T,>(
    command: string,
    args: Record<string, unknown> = {},
    options: { quiet?: boolean; allowBusy?: boolean } = {},
  ): Promise<BackendResponse<T> | null> => {
    if (busyRef.current && !options.allowBusy) return null;
    busyRef.current = command;
    setBusy(command);
    try {
      const response = await requestBackend<T>(command, args);
      if (!options.quiet) {
        setStatus(response.message || (response.ok ? "작업을 완료했습니다." : "작업하지 못했습니다."));
      }
      if (response.data && typeof response.data === "object") {
        const data = response.data as Record<string, unknown>;
        if (data.selection) setSelection(data.selection as CellSelection);
        if (typeof data.connected === "boolean") setConnected(Boolean(response.ok && data.connected));
      }
      return response;
    } catch (error) {
      setConnected(false);
      setStatus(`연결 오류: ${String(error)}`);
      return null;
    } finally {
      busyRef.current = "";
      setBusy("");
    }
  }, []);

  const moveCharacterGroup = useCallback(async (id: string, direction: -1 | 1 | "first" | "last") => {
    if (busyRef.current) return;
    const order = orderedCharacterGroups.map((group) => group.id);
    const index = order.indexOf(id);
    const nextIndex = direction === "first" ? 0 : direction === "last" ? order.length - 1 : index + direction;
    if (index < 0 || nextIndex < 0 || nextIndex >= order.length || index === nextIndex) return;
    order.splice(index, 1);
    order.splice(nextIndex, 0, id);
    const response = await execute<{ settings: AppSettings }>("settings_save", {
      changes: { character_group_order: order },
    }, { quiet: true });
    const savedOrder = response?.data?.settings?.character_group_order;
    if (response?.ok && Array.isArray(savedOrder)) {
      setSettings((current) => ({ ...current, character_group_order: savedOrder }));
      window.requestAnimationFrame(() => {
        const group = Array.from(document.querySelectorAll<HTMLElement>("[data-character-group-id]"))
          .find((element) => element.dataset.characterGroupId === id);
        group?.scrollIntoView({ block: "nearest" });
      });
    } else {
      setStatus(response?.message || "문자표 순서를 저장하지 못했습니다.");
    }
  }, [execute, orderedCharacterGroups]);

  const insertCharacter = useCallback(async (value: string) => {
    if (busyRef.current) return;
    const response = await execute<{ hwp_hwnd?: number }>("insert_character", { value });
    const hwnd = Number(response?.data?.hwp_hwnd || 0);
    if (response?.ok && hwnd > 0) {
      await focusExternalWindow(hwnd).catch(() => undefined);
    }
  }, [execute]);

  const alignWindowLayout = useCallback(async () => {
    if (busyRef.current || settings.target_mode !== "hwp") return;
    busyRef.current = "window_layout";
    setBusy("window_layout");
    window.clearTimeout(windowLayoutTimer.current);
    windowLayoutChangingRef.current = true;
    try {
      const target = await requestBackend<{ hwnd: number; pid: number }>("window_layout_target");
      if (!target.ok || !target.data?.hwnd || !target.data.pid) {
        setStatus(target.message || "배치할 한글 창을 찾지 못했습니다.");
        return;
      }
      const result = await arrangeHwpWindows(target.data.hwnd, target.data.pid);
      windowLayoutActiveRef.current = result.active;
      setStatus(result.message || "창 배치를 변경했습니다.");
    } catch (error) {
      setStatus(`창 배치 실패: ${String(error)}`);
      const state = await readWindowLayoutState().catch(() => null);
      if (state) {
        windowLayoutActiveRef.current = state.active;
      }
    } finally {
      busyRef.current = "";
      setBusy("");
      windowLayoutTimer.current = window.setTimeout(() => { windowLayoutChangingRef.current = false; }, 300);
    }
  }, [settings.target_mode]);

  useEffect(() => {
    let disposed = false;
    void readWindowLayoutState().then((state) => {
      if (!disposed && state) {
        windowLayoutActiveRef.current = state.active;
      }
    }).catch(() => undefined);
    return () => { disposed = true; window.clearTimeout(windowLayoutTimer.current); };
  }, []);

  const startTableDrawing = useCallback(async () => {
    const response = await execute<{ hwp_hwnd?: number }>("table_draw");
    const hwnd = Number(response?.data?.hwp_hwnd || 0);
    if (response?.ok && hwnd > 0) {
      try {
        await focusExternalWindow(hwnd);
      } catch {
        setStatus("표 그리기를 시작했지만 한글 창을 활성화하지 못했습니다. 한글 창을 클릭하세요.");
      }
    }
  }, [execute]);

  const insertComposedCharacter = useCallback(async (value: string, shape: "circle" | "square", closeDialog = false) => {
    if (busyRef.current) return;
    const response = await execute<{ hwp_hwnd?: number }>("compose_characters", { value, shape });
    if (!response?.ok) {
      if (closeDialog) setComposeError(response?.message || "글자 겹치기를 실행하지 못했습니다.");
      return;
    }
    if (closeDialog) {
      setComposeOpen(false);
      await setWindowInputMode(false).catch(() => undefined);
    }
    const hwnd = Number(response.data?.hwp_hwnd || 0);
    if (hwnd > 0) await focusExternalWindow(hwnd).catch(() => undefined);
  }, [execute]);

  const loadCatalogs = useCallback(async () => {
    const results = await Promise.all([
      requestBackend<{ items: ContentItem[] }>("style_catalog"),
      requestBackend<{ items: AutoTitleTemplate[] }>("auto_title_template_catalog"),
      requestBackend<{ items: ContentItem[] }>("form_catalog"),
      requestBackend<{ items: KedufineForm[] }>("kedufine_form_catalog"),
      requestBackend<{ items: ContentItem[] }>("page_catalog"),
      requestBackend<{ items: TableToolItem[] }>("table_catalog"),
      requestBackend<{ groups: CharacterGroup[] }>("character_catalog"),
      requestBackend<{ groups: PictureSymbolGroup[] }>("picture_symbol_catalog"),
      requestBackend<{ fonts: string[] }>("font_catalog"),
    ]);
    setStyles(results[0].data?.items ?? []);
    setAutoTitleTemplates(results[1].data?.items ?? []);
    setForms(results[2].data?.items ?? []);
    setKedufineForms(results[3].data?.items ?? []);
    setPages(results[4].data?.items ?? []);
    setTableTools(results[5].data?.items ?? []);
    setCharacterGroups(results[6].data?.groups ?? []);
    setPictureGroups(results[7].data?.groups ?? []);
    setFontNames(results[8].data?.fonts?.length ? results[8].data.fonts : FONT_ROWS.map((font) => font.name));
  }, []);

  useEffect(() => {
    let alive = true;
    let updateTimer = 0;
    void (async () => {
      try {
        const settingsResponse = await requestBackend<{
          settings: AppSettings;
          integration: IntegrationStatus;
          had_user_data?: boolean;
        }>("settings_get");
        if (!alive) return;
        setHadUserData(Boolean(settingsResponse.data?.had_user_data));
        const loaded = { ...DEFAULT_SETTINGS, ...(settingsResponse.data?.settings ?? {}) };
        setSettings(loaded);
        setIntegration(settingsResponse.data?.integration ?? integration);
        const integrationResponse = await requestBackend<{ integration: IntegrationStatus }>("integration_prepare");
        if (integrationResponse.data?.integration) setIntegration(integrationResponse.data.integration);
        await setWindowPreferences(loaded.always_on_top, loaded.close_to_tray);
        await applyWindowPosition(loaded.start_position, loaded.last_geometry);
        const statusResponse = await requestBackend<{
          connected: boolean;
          selection: CellSelection;
        }>("status");
        if (!alive) return;
        setConnected(Boolean(statusResponse.ok && statusResponse.data?.connected));
        if (statusResponse.data?.selection) setSelection(statusResponse.data.selection);
        setStatus(statusResponse.message);
        await loadCatalogs();
        if (loaded.check_updates_on_startup) {
          updateTimer = window.setTimeout(() => void checkUpdate(false), 1800);
        }
        if (!loaded.tutorial_completed) setTutorialOpen(true);
      } catch (error) {
        if (alive) setStatus(`초기화 오류: ${String(error)}`);
      }
    })();
    return () => {
      alive = false;
      window.clearTimeout(updateTimer);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const timer = window.setInterval(async () => {
      if (
        settings.target_mode !== "hwp"
        || polling.current
        || busyRef.current
      ) return;
      polling.current = true;
      try {
        const response = await requestBackend<{ selection: CellSelection }>("selection_state");
        if (response.ok && response.data?.selection) setSelection(response.data.selection);
      } catch {
        setConnected(false);
      } finally {
        polling.current = false;
      }
    }, 220);
    return () => window.clearInterval(timer);
  }, [settings.target_mode]);
  useEffect(() => {
    if (!settings.remember_window_position || settingsOpen || hotkeyOpen) return undefined;
    let disposed = false;
    let saveTimer = 0;
    let unlisten: (() => void) | undefined;
    void getCurrentWindow().onMoved(({ payload }) => {
      window.clearTimeout(saveTimer);
      if (windowLayoutActiveRef.current || windowLayoutChangingRef.current || payload.x <= -10000 || payload.y <= -10000) return;
      const geometry = `${payload.x},${payload.y}`;
      setSettings((current) => ({ ...current, last_geometry: geometry }));
      saveTimer = window.setTimeout(() => {
        if (!disposed && !windowLayoutActiveRef.current && !windowLayoutChangingRef.current) {
          void requestBackend("settings_save", { changes: { last_geometry: geometry } });
        }
      }, 500);
    }).then((handler) => { unlisten = handler; });
    return () => {
      disposed = true;
      window.clearTimeout(saveTimer);
      unlisten?.();
    };
  }, [settings.remember_window_position, settingsOpen, hotkeyOpen]);

  const saveSettings = useCallback(async (changes: Partial<AppSettings>) => {
    const response = await execute<{ settings: AppSettings; integration: IntegrationStatus }>(
      "settings_save",
      { changes },
    );
    if (!response?.ok || !response.data?.settings) return false;
    const next = { ...DEFAULT_SETTINGS, ...response.data.settings };
    setSettings(next);
    if (response.data.integration) setIntegration(response.data.integration);

    try {
      await setWindowPreferences(next.always_on_top, next.close_to_tray);
      if ("start_position" in changes) {
        await applyWindowPosition(next.start_position, next.last_geometry);
      }
    } catch {
      setStatus("설정은 저장했지만 창 옵션을 적용하지 못했습니다.");
    }
    return true;
  }, [execute]);

  const toggleCardFavorite = useCallback(async (kind: FavoriteKind, key: string) => {
    const response = await execute<{ card_favorites: CardFavorites }>(
      "card_favorite_toggle", { kind, key }, { quiet: true },
    );
    if (response?.ok && response.data?.card_favorites) {
      setSettings((current) => ({ ...current, card_favorites: response.data.card_favorites }));
    } else if (response) {
      setStatus(response.message || "즐겨찾기를 저장하지 못했습니다.");
    }
  }, [execute]);

  const checkUpdate = useCallback(async (manual = false) => {
    if (updateBusyRef.current) return;
    updateBusyRef.current = true;
    setUpdateBusy(true);
    if (manual) setUpdateStatus("새 버전을 확인하는 중입니다.");
    try {
      const result = await prepareUpdate(setUpdateStatus);
      setUpdateStatus(result.message);
      if (result.ready && result.version) {
        setUpdateReadyVersion(result.version);
        setUpdateDismissed(false);
      }
    } catch (error) {
      const message = `업데이트 확인 실패: ${displayUpdateError(error)}`;
      setUpdateStatus(message);
      if (manual) setStatus(message);
    } finally {
      updateBusyRef.current = false;
      setUpdateBusy(false);
    }
  }, []);

  const applyUpdate = useCallback(async () => {
    if (busyRef.current) {
      setStatus("진행 중인 한글 작업이 끝난 뒤 업데이트를 적용해 주세요.");
      return;
    }
    if (updateBusyRef.current) return;
    updateBusyRef.current = true;
    setUpdateBusy(true);
    setUpdateStatus("업데이트를 적용하고 다시 시작합니다.");
    try {
      await applyPreparedUpdate();
    } catch (error) {
      const message = `업데이트 적용 실패: ${String(error)}`;
      setUpdateStatus(message);
      setStatus(message);
      updateBusyRef.current = false;
      setUpdateBusy(false);
    }
  }, []);

  const resetSettings = useCallback(async () => {
    if (!window.confirm("화면·시작·단축키·자동 서식 설정을 기본값으로 되돌릴까요?")) return;
    const response = await execute<{ settings: AppSettings; integration: IntegrationStatus }>("settings_reset");
    if (!response?.ok || !response.data?.settings) return;
    const next = { ...DEFAULT_SETTINGS, ...response.data.settings };
    setSettings(next);
    const nextIntegration = response.data.integration ?? integration;
    setIntegration(nextIntegration);
    await setWindowPreferences(next.always_on_top, next.close_to_tray);
    await applyWindowPosition(next.start_position, next.last_geometry);
    if (nextIntegration.startup) {
      const integrationResponse = await execute<{ integration: IntegrationStatus }>("integration_set", {
        kind: "startup",
        enabled: true,
        start_minimized: false,
      });
      if (integrationResponse?.data?.integration) setIntegration(integrationResponse.data.integration);
    }
    if (!preparedUpdateVersion()) {
      setUpdateStatus(`현재 버전 ${VERSION} · 업데이트 확인 대기`);
    }
    await loadCatalogs();
  }, [execute, integration, loadCatalogs]);

  const backupUserData = useCallback(async () => {
    await execute("user_data_backup");
  }, [execute]);

  const restoreUserData = useCallback(async () => {
    if (!window.confirm(
      "현재 설정과 내 자료를 선택한 백업 파일의 내용으로 바꿉니다.\n복원 전 상태는 자동으로 백업됩니다. 계속할까요?",
    )) return;

    const response = await execute<{
      restore: {
        cancelled?: boolean;
        integration?: { startup?: boolean; start_menu?: boolean };
      };
      settings: AppSettings;
      integration: IntegrationStatus;
    }>("user_data_restore");
    if (!response?.ok || response.data?.restore?.cancelled || !response.data?.settings) return;

    const next = { ...DEFAULT_SETTINGS, ...response.data.settings };
    setSettings(next);
    setConnected(false);
    if (next.target_mode === "kedufine" && ["symbol", "page"].includes(activeTab)) {
      setActiveTab("style");
    }
    if (next.target_mode === "kedufine" && editTab === "cell") {
      setEditTab("table");
    }
    await setWindowPreferences(next.always_on_top, next.close_to_tray);
    await applyWindowPosition(next.start_position, next.last_geometry);
    await loadCatalogs();

    let nextIntegration = response.data.integration ?? integration;
    const restoredIntegration = response.data.restore.integration;
    if (typeof restoredIntegration?.startup === "boolean") {
      const integrationResponse = await execute<{ integration: IntegrationStatus }>(
        "integration_set",
        {
          kind: "startup",
          enabled: restoredIntegration.startup,
          start_minimized: next.start_minimized,
        },
      );
      if (integrationResponse?.data?.integration) {
        nextIntegration = integrationResponse.data.integration;
      }
    }
    if (typeof restoredIntegration?.start_menu === "boolean") {
      const integrationResponse = await execute<{ integration: IntegrationStatus }>(
        "integration_set",
        {
          kind: "start_menu",
          enabled: restoredIntegration.start_menu,
        },
      );
      if (integrationResponse?.data?.integration) {
        nextIntegration = integrationResponse.data.integration;
      }
    }
    setIntegration(nextIntegration);
    setStatus("설정과 내 자료를 복원했습니다.");
  }, [activeTab, editTab, execute, integration, loadCatalogs]);

  const changeTargetMode = useCallback(async (mode: "hwp" | "kedufine") => {
    const response = await execute<{ connected: boolean; target_mode: "hwp" | "kedufine" }>(
      "set_target_mode",
      { mode },
    );
    setSettings((current) => ({ ...current, target_mode: mode }));
    setConnected(Boolean(response?.ok && response.data?.connected));
    if (mode === "kedufine" && ["symbol", "page"].includes(activeTab)) setActiveTab("style");
    if (mode === "kedufine" && editTab === "cell") setEditTab("table");
    await loadCatalogs();
  }, [activeTab, editTab, execute, loadCatalogs]);

  const startAutoFormat = useCallback(async () => {
    if (busyRef.current) return;
    setStopRequested(false);
    setStatus("선택 영역의 문서 구조를 분석하는 중입니다.");
    await execute("auto_format_report");
    setStopRequested(false);
  }, [execute]);

  const applySelectedAutoFormatRole = useCallback(async (role: DirectAutoFormatRoleKey) => {
    const response = await execute<{ reason?: string; role?: string }>(
      "auto_format_apply_role",
      { role },
    );
    if (!response?.ok && response?.data?.reason === "selection_required") {
      setAutoFormatRoleGuide(role);
    }
  }, [execute]);

  const stopAutoFormat = useCallback(async () => {
    if (busyRef.current !== "auto_format_report" || stopRequested) return;
    setStopRequested(true);
    setStatus("서식 자동 지정 중지를 요청하는 중입니다.");
    try {
      const response = await cancelAutoFormat();
      setStatus(response.message);
    } catch (error) {
      setStopRequested(false);
      setStatus(`중지 요청 오류: ${String(error)}`);
    }
  }, [stopRequested]);

  const isBusy = Boolean(busy);
  const visibleTabs = useMemo(() => {
    const allowed = settings.target_mode === "kedufine"
      ? new Set<TabId>(["style", "edit", "chars", "forms"])
      : new Set<TabId>(["style", "edit", "chars", "symbol", "forms", "page"]);
    const ordered = (settings.tab_order ?? [])
      .filter((id): id is TabId => id in TAB_LABELS && allowed.has(id as TabId));
    for (const id of Object.keys(TAB_LABELS) as TabId[]) {
      if (allowed.has(id) && !ordered.includes(id)) ordered.push(id);
    }
    return ordered;
  }, [settings.tab_order, settings.target_mode]);

  const documentTitleTemplates = useMemo(
    () => autoTitleTemplates.filter((item) => item.role === "document_title"),
    [autoTitleTemplates],
  );
  const levelOneTitleTemplates = useMemo(
    () => autoTitleTemplates.filter((item) => item.role === "title"),
    [autoTitleTemplates],
  );

  const activeAutoFormatProfile = useMemo(
    () => settings.auto_format_profiles.find(
      (profile) => profile.id === settings.active_auto_format_profile,
    ) ?? settings.auto_format_profiles[0],
    [settings.active_auto_format_profile, settings.auto_format_profiles],
  );

  const usableAutoFormatSettings = useCallback((value: AutoFormatSettings) => {
    const next = cloneAutoFormatSettings(value);
    if (!documentTitleTemplates.some((item) => item.key === next.document_title_template)) {
      next.document_title_template = "auto-title-builtin:document_title";
    }
    if (!levelOneTitleTemplates.some((item) => item.key === next.title_template)) {
      next.title_template = "auto-title-builtin:title";
    }
    return next;
  }, [documentTitleTemplates, levelOneTitleTemplates]);

  const nextAutoTitleName = (role: "document_title" | "title") => {
    const base = role === "document_title" ? "내 문서제목" : "내 1단계 제목";
    const used = new Set(
      autoTitleTemplates
        .filter((item) => item.role === role && item.user_item)
        .map((item) => item.title.trim().toLocaleLowerCase()),
    );
    if (!used.has(base.toLocaleLowerCase())) return base;
    let index = 2;
    while (used.has((base + " " + index).toLocaleLowerCase())) index += 1;
    return base + " " + index;
  };

  const openAutoFormatSettings = () => {
    const profiles = settings.auto_format_profiles.length
      ? cloneAutoFormatProfiles(settings.auto_format_profiles)
      : cloneAutoFormatProfiles(DEFAULT_SETTINGS.auto_format_profiles);
    const selected = profiles.find((profile) => profile.id === settings.active_auto_format_profile)
      ?? profiles[0];
    const draft = usableAutoFormatSettings(selected?.settings ?? settings.auto_format);
    setAutoFormatProfilesDraft(profiles);
    setAutoFormatProfileIdDraft(selected?.id ?? "default");
    setAutoFormatDraft(draft);
    setAutoFormatSettingsOpen(true);
  };

  const profilesWithCurrentDraft = useCallback((
    profiles: AutoFormatProfile[],
    profileId: string,
    draft: AutoFormatSettings,
  ) => profiles.map((profile) => profile.id === profileId
    ? { ...profile, settings: cloneAutoFormatSettings(draft) }
    : cloneAutoFormatProfile(profile)), []);

  const selectAutoFormatProfile = useCallback(async (profileId: string) => {
    const profile = settings.auto_format_profiles.find((item) => item.id === profileId);
    if (!profile) return;
    const selectedSettings = usableAutoFormatSettings(profile.settings);
    const profiles = settings.auto_format_profiles.map((item) => item.id === profile.id
      ? { ...item, settings: cloneAutoFormatSettings(selectedSettings) }
      : cloneAutoFormatProfile(item));
    await saveSettings({
      active_auto_format_profile: profile.id,
      auto_format_profiles: profiles,
      auto_format: selectedSettings,
    });
  }, [saveSettings, settings.auto_format_profiles, usableAutoFormatSettings]);

  const selectAutoFormatProfileDraft = (profileId: string) => {
    const profiles = profilesWithCurrentDraft(
      autoFormatProfilesDraft,
      autoFormatProfileIdDraft,
      autoFormatDraft,
    );
    const profile = profiles.find((item) => item.id === profileId);
    if (!profile) return;
    setAutoFormatProfilesDraft(profiles);
    setAutoFormatProfileIdDraft(profile.id);
    setAutoFormatDraft(usableAutoFormatSettings(profile.settings));
  };

  const nextAutoFormatProfileName = (base: string, profiles: AutoFormatProfile[]) => {
    const used = new Set(profiles.map((profile) => profile.name.trim().toLocaleLowerCase()));
    if (!used.has(base.toLocaleLowerCase())) return base;
    let index = 2;
    while (used.has(`${base} ${index}`.toLocaleLowerCase())) index += 1;
    return `${base} ${index}`;
  };

  const addAutoFormatProfile = (duplicate: boolean) => {
    const profiles = profilesWithCurrentDraft(
      autoFormatProfilesDraft,
      autoFormatProfileIdDraft,
      autoFormatDraft,
    );
    if (profiles.length >= MAX_AUTO_FORMAT_PROFILES) {
      setStatus(`자동 서식 설정은 최대 ${MAX_AUTO_FORMAT_PROFILES}개까지 저장할 수 있습니다.`);
      return;
    }
    const base = duplicate ? "복사한 설정" : "새 설정";
    askName(
      duplicate ? "자동 서식 설정 복제" : "새 자동 서식 설정",
      nextAutoFormatProfileName(base, profiles),
      "추가",
      async (name) => {
        if (profiles.some((profile) => profile.name.trim().toLocaleLowerCase() === name.toLocaleLowerCase())) {
          setStatus("같은 이름의 자동 서식 설정이 이미 있습니다.");
          return;
        }
        const settingsValue = duplicate
          ? cloneAutoFormatSettings(autoFormatDraft)
          : cloneAutoFormatSettings(DEFAULT_AUTO_FORMAT_SETTINGS);
        const profile = { id: createAutoFormatProfileId(), name, settings: settingsValue };
        setAutoFormatProfilesDraft([...profiles, profile]);
        setAutoFormatProfileIdDraft(profile.id);
        setAutoFormatDraft(cloneAutoFormatSettings(profile.settings));
        setNameDialog(null);
      },
    );
  };

  const renameAutoFormatProfile = () => {
    const profiles = profilesWithCurrentDraft(
      autoFormatProfilesDraft,
      autoFormatProfileIdDraft,
      autoFormatDraft,
    );
    const selected = profiles.find((profile) => profile.id === autoFormatProfileIdDraft);
    if (!selected) return;
    askName("자동 서식 설정 이름 변경", selected.name, "저장", async (name) => {
      if (profiles.some((profile) => profile.id !== selected.id
        && profile.name.trim().toLocaleLowerCase() === name.toLocaleLowerCase())) {
        setStatus("같은 이름의 자동 서식 설정이 이미 있습니다.");
        return;
      }
      setAutoFormatProfilesDraft(profiles.map((profile) => profile.id === selected.id
        ? { ...profile, name }
        : profile));
      setNameDialog(null);
    });
  };

  const deleteAutoFormatProfile = () => {
    if (autoFormatProfilesDraft.length <= 1) {
      setStatus("자동 서식 설정은 하나 이상 남아 있어야 합니다.");
      return;
    }
    const profiles = profilesWithCurrentDraft(
      autoFormatProfilesDraft,
      autoFormatProfileIdDraft,
      autoFormatDraft,
    );
    const selected = profiles.find((profile) => profile.id === autoFormatProfileIdDraft);
    if (!selected || !window.confirm(`'${selected.name}' 자동 서식 설정을 삭제할까요?`)) return;
    const remaining = profiles.filter((profile) => profile.id !== selected.id);
    setAutoFormatProfilesDraft(remaining);
    setAutoFormatProfileIdDraft(remaining[0].id);
    setAutoFormatDraft(cloneAutoFormatSettings(remaining[0].settings));
  };

  const updateAutoFormatRole = (
    role: AutoFormatRoleKey,
    changes: Partial<AutoFormatRoleStyle>,
  ) => {
    setAutoFormatDraft((current) => ({
      ...current,
      roles: {
        ...current.roles,
        [role]: { ...current.roles[role], ...changes },
      },
    }));
  };

  const saveAutoFormatSettings = async () => {
    const profiles = profilesWithCurrentDraft(
      autoFormatProfilesDraft,
      autoFormatProfileIdDraft,
      autoFormatDraft,
    );
    const selected = profiles.find((profile) => profile.id === autoFormatProfileIdDraft) ?? profiles[0];
    if (profiles.length > MAX_AUTO_FORMAT_PROFILES) {
      setStatus(`자동 서식 설정은 최대 ${MAX_AUTO_FORMAT_PROFILES}개까지 저장할 수 있습니다.`);
      return;
    }
    const saved = await saveSettings({
      auto_format_profiles: profiles,
      active_auto_format_profile: selected.id,
      auto_format: cloneAutoFormatSettings(selected.settings),
    });
    if (saved) setAutoFormatSettingsOpen(false);
  };

  const beginAutoTitleRegistration = async (role: "document_title" | "title") => {
    const result = await execute<AutoTitleAnalysis>("auto_title_template_analyze", { role });
    if (!result?.ok || !result.data?.pending_id) {
      if (result?.message?.includes("선택한 텍스트를 읽지 못했습니다")) {
        setAutoTitleSelectionGuideRole(role);
      }
      return;
    }
    setAutoTitleRegistration({
      ...result.data,
      name: nextAutoTitleName(role),
    });
  };

  const closeAutoTitleRegistration = () => {
    const pendingId = autoTitleRegistration?.pending_id;
    setAutoTitleRegistration(null);
    if (pendingId) {
      void requestBackend("auto_title_template_discard", { pending_id: pendingId }).catch(() => undefined);
    }
  };

  const saveAutoTitleRegistration = async () => {
    if (!autoTitleRegistration) return;
    const result = await execute<{ item: AutoTitleTemplate }>("auto_title_template_register", {
      role: autoTitleRegistration.role,
      title: autoTitleRegistration.name,
      pending_id: autoTitleRegistration.pending_id,
      title_sample: autoTitleRegistration.title_sample,
      number_sample: autoTitleRegistration.number_sample,
    });
    if (!result?.ok || !result.data?.item) {
      setAutoTitleRegistration((current) => current
        ? { ...current, error: result?.message || "제목 양식을 저장하지 못했습니다." }
        : current);
      return;
    }
    const key = "auto-title-user:" + result.data.item.id;
    setAutoFormatDraft((current) => autoTitleRegistration.role === "document_title"
      ? { ...current, document_title_template: key }
      : { ...current, title_template: key });
    setAutoTitleRegistration(null);
    await loadCatalogs();
  };

  const renameAutoTitleTemplate = (item: AutoTitleTemplate) => {
    askName(
      "제목 양식 이름 변경",
      item.title,
      "저장",
      async (title) => {
        const result = await execute("auto_title_template_update", {
          item_id: item.id,
          title,
        });
        if (result?.ok) {
          setNameDialog(null);
          await loadCatalogs();
        }
      },
    );
  };

  const deleteAutoTitleTemplate = async (item: AutoTitleTemplate) => {
    if (!window.confirm("'" + item.title + "' 제목 양식을 삭제할까요?")) return;
    const result = await execute("auto_title_template_delete", { item_id: item.id });
    if (!result?.ok) return;
    const removedKey = "auto-title-user:" + item.id;
    const withoutRemovedTemplate = (value: AutoFormatSettings) => ({
      ...cloneAutoFormatSettings(value),
      document_title_template: value.document_title_template === removedKey
        ? "auto-title-builtin:document_title"
        : value.document_title_template,
      title_template: value.title_template === removedKey
        ? "auto-title-builtin:title"
        : value.title_template,
    });
    setAutoFormatDraft((current) => withoutRemovedTemplate(current));
    setAutoFormatProfilesDraft((current) => current.map((profile) => ({
      ...profile,
      settings: withoutRemovedTemplate(profile.settings),
    })));
    const profiles = settings.auto_format_profiles.map((profile) => ({
      ...profile,
      settings: withoutRemovedTemplate(profile.settings),
    }));
    const active = profiles.find((profile) => profile.id === settings.active_auto_format_profile)
      ?? profiles[0];
    if (active) {
      await saveSettings({
        auto_format_profiles: profiles,
        active_auto_format_profile: active.id,
        auto_format: cloneAutoFormatSettings(active.settings),
      });
    }
    await loadCatalogs();
  };

  const askName = (
    title: string,
    initial: string,
    submitLabel: string,
    onSubmit: (value: string) => Promise<void>,
  ) => {
    setNameValue(initial);
    setNameDialog({ title, initial, submitLabel, onSubmit });
  };

  const addUserContentFromFile = async () => {
    setSourceKind(null);
    const picked = await execute<{ paths: string[]; suggested_title: string }>(
      "pick_files",
      { kind: "hwp" },
    );
    const path = picked?.data?.paths?.[0];
    if (!picked?.ok || !path) return;
    askName(
      "내 양식 이름",
      picked.data.suggested_title || "",
      "등록",
      async (title) => {
        const result = await execute("user_add_file", {
          kind: "form",
          title,
          source_path: path,
        });
        if (result?.ok) {
          setNameDialog(null);
          await loadCatalogs();
        }
      },
    );
  };

  const addKedufineForm = () => {
    setKedufineFormDraft({
      title: "",
      category: kedufineCategory === "legacy" ? "outgoing" : kedufineCategory,
      body: "",
    });
  };

  const saveKedufineForm = async () => {
    const draft = kedufineFormDraft;
    if (!draft || !draft.title.trim() || !draft.body.trim()) return;
    const result = await execute("user_save_kedufine_form", {
      item_id: draft.id || "",
      title: draft.title.trim(),
      category: draft.category,
      body: draft.body,
    });
    if (result?.ok) {
      setKedufineFormDraft(null);
      setKedufineCategory(draft.category);
      await loadCatalogs();
    }
  };

  const deleteKedufineForm = async (item: KedufineForm) => {
    if (!window.confirm(`'${item.title}' 양식을 삭제할까요?`)) return;
    const result = await execute("user_delete", { kind: "kedufine_form", item_id: item.id });
    if (result?.ok) {
      if (item.legacy && kedufineForms.filter((form) => form.legacy).length === 1) {
        setKedufineCategory("internal");
      }
      await loadCatalogs();
    }
  };

  const addUserContentFromBlock = (kind: "style" | "form") => {
    setSourceKind(null);
    askName(
      kind === "style" ? "블록 지정한 내용을 내 서식으로 추가" : "블록 지정한 내용을 내 양식으로 추가",
      "",
      "등록",
      async (title) => {
        const result = await execute("user_add_block", { kind, title });
        if (result?.ok) {
          setNameDialog(null);
          await loadCatalogs();
        }
      },
    );
  };

  const openPageEditor = (item: ContentItem | "new") => {
    setPageEditor(item);
    setPageTitle(item === "new" ? "" : item.title);
    setPageMargins(item === "new" ? DEFAULT_MARGINS : (item.margins ?? DEFAULT_MARGINS));
    setPageOrientation(item === "new" ? "portrait" : (item.orientation ?? "portrait"));
  };

  const savePageEditor = async () => {
    const result = await execute("user_save_page", {
      item_id: pageEditor === "new" || pageEditor === null ? "" : pageEditor.id,
      title: pageTitle,
      margins: pageMargins,
      orientation: pageOrientation,
    });
    if (result?.ok) {
      setPageEditor(null);
      await loadCatalogs();
    }
  };

  const openSymbolEditor = (item: CharacterGroup | "new") => {
    setSymbolEditor(item);
    setSymbolTitle(item === "new" ? "" : item.title);
    setSymbolValues(item === "new" ? "" : item.chars.join("\n"));
  };

  const saveSymbolEditor = async () => {
    const adding = symbolEditor === "new";
    const result = await execute<{ character_group_order: string[] }>("user_save_symbol_group", {
      item_id: symbolEditor === "new" || symbolEditor === null ? "" : symbolEditor.id,
      title: symbolTitle,
      chars: symbolValues,
    });
    if (result?.ok) {
      if (Array.isArray(result.data?.character_group_order)) {
        setSettings((current) => ({ ...current, character_group_order: result.data!.character_group_order }));
      }
      setSymbolEditor(null);
      await loadCatalogs();
      if (adding) document.querySelector(".content")?.scrollTo({ top: 0 });
    }
  };

  const deleteSymbolGroup = async () => {
    if (!symbolDeleteTarget || busyRef.current) return;
    setSymbolDeleteError("");
    const result = await execute("user_delete_symbol_group", { item_id: symbolDeleteTarget.id });
    if (result?.ok) {
      setSymbolDeleteTarget(null);
      await loadCatalogs();
    } else {
      setSymbolDeleteError(result?.message || "문자표를 삭제하지 못했습니다. 다시 시도하세요.");
    }
  };

  const addPictureSymbols = async () => {
    const picked = await execute<{ paths: string[] }>("pick_files", { kind: "picture_symbols" });
    const paths = picked?.data?.paths ?? [];
    if (!picked?.ok || !paths.length) return;
    const result = await execute("user_add_picture_symbols", { paths });
    if (result?.ok) {
      await loadCatalogs();
      setPictureGroupIndex(0);
    }
  };

  const renamePictureSymbol = (item: PictureSymbolItem) => {
    if (!item.id) return;
    askName("심볼 이름 수정", item.title, "저장", async (title) => {
      const result = await execute("user_update_picture_symbol", { item_id: item.id, title });
      if (result?.ok) {
        setNameDialog(null);
        await loadCatalogs();
      }
    });
  };

  const deletePictureSymbol = async (item: PictureSymbolItem) => {
    if (!item.id || !window.confirm(`'${item.title}' 심볼을 삭제할까요?`)) return;
    const result = await execute("user_delete_picture_symbol", { item_id: item.id });
    if (result?.ok) {
      await loadCatalogs();
      setPictureGroupIndex(0);
    }
  };
  const deleteUserItem = async (kind: ContentKind, item: ContentItem) => {
    if (!window.confirm(`'${item.title}' 항목을 삭제할까요?`)) return;
    const result = await execute("user_delete", { kind, item_id: item.id });
    if (result?.ok) await loadCatalogs();
  };


  const insertCellImages = useCallback(async () => {
    const picked = await execute<{ paths: string[] }>("pick_files", { kind: "images" });
    const paths = picked?.data?.paths ?? [];
    if (!paths.length) return;
    await execute("insert_cell_images", { paths, size_mode: imageMode });
  }, [execute, imageMode]);

  const completeTutorial = async () => {
    setTutorialOpen(false);
    setSettingsOpen(false);
    setActiveTab("style");
    contentRef.current?.scrollTo({ top: 0, behavior: "instant" });
    await saveSettings({ tutorial_completed: true });
  };

  const openTutorial = useCallback(() => {
    setSettingsOpen(false);
    setHotkeyOpen(false);
    setAutoFormatHelpOpen(false);
    setTutorialOpen(true);
  }, []);

  const navigateTutorial = useCallback((destination: TutorialDestination) => {
    if (destination.tab) setActiveTab(destination.tab);
    if (destination.editTab) setEditTab(destination.editTab);
    setSettingsOpen(Boolean(destination.settings));
  }, []);

  const hotkeyActions = useMemo<HotkeyAction[]>(() => {
    const actions: HotkeyAction[] = [
      { id: "feature:auto_format_report", category: "서식", label: "서식 자동 지정하기", special: "auto_format" },
      { id: "feature:cell_clean_spaces", category: "셀 정리", label: "불필요한 앞뒤 공백 제거", command: "cell_clean_spaces" },
      { id: "feature:cell_cleanup_excel_paste", category: "셀 정리", label: "공백·배경색 한 번에 정리", command: "cell_cleanup_excel" },
      { id: "feature:table_insert_images_into_cells", category: "표 작업", label: "셀에 그림 넣기", special: "insert_images" },
      { id: "feature:table_refit_images_in_cells", category: "표 작업", label: "기존 그림 다시 맞춤", command: "refit_cell_images", args: { size_mode: imageMode } },
      { id: "feature:char_spacing_cleanup_level_1", category: "글자 작업", label: "자간 정리 1단계", command: "spacing_cleanup", args: { adjust_count: 3 } },
      { id: "feature:char_spacing_cleanup_level_2", category: "글자 작업", label: "자간 정리 2단계", command: "spacing_cleanup", args: { adjust_count: 5 } },
      { id: "feature:char_spacing_reset", category: "글자 작업", label: "자간 초기화", command: "spacing_reset" },
    ];
    for (const tool of tableTools) {
      actions.push({
        id: `table:${tool.action_id}`,
        category: "표 작업",
        label: tool.title,
        command: "table_tool",
        args: { action_id: tool.action_id },
      });
    }
    const colors: Array<[string, number[]]> = [
      ["검정", [0, 0, 0]],
      ["빨강", [220, 0, 0]],
      ["파랑", [0, 70, 200]],
      ["흰색", [255, 255, 255]],
    ];
    for (const [label, rgb] of colors) {
      actions.push({
        id: `font-color:${rgb.join(",")}`,
        category: "글자 작업",
        label: `글자색 ${label}`,
        command: "apply_charshape",
        args: { font_color_rgb: rgb },
      });
    }
    for (const row of FONT_ROWS) {
      actions.push({
        id: `font:${row.name}`,
        category: "글자 작업",
        label: `글꼴 ${row.name}`,
        command: "apply_charshape",
        args: { font_name: row.name },
      });
      for (const size of row.sizes) {
        actions.push({
          id: `font-size:${row.name}:${size}`,
          category: "글자 작업",
          label: `${row.name} ${size}pt`,
          command: "apply_charshape",
          args: { font_name: row.name, font_size_pt: size },
        });
      }
    }
    const seen = new Set<string>();
    for (const group of characterGroups) {
      for (const value of group.chars) {
        const square = group.presentation === "square";
        const identity = `${square ? "square:" : ""}${value}`;
        if (!value || seen.has(identity)) continue;
        seen.add(identity);
        const encoded = Array.from(value).map((char) => char.codePointAt(0)?.toString(16)).join("-");
        actions.push({
          id: `${square ? "compose-square" : "insert-text"}:${encoded}`,
          category: "문자표",
          label: `${value}  (${group.title})`,
          command: square ? "compose_characters" : "insert_character",
          args: square ? { value, shape: "square" } : { value },
        });
      }
    }
    return actions;
  }, [characterGroups, imageMode, tableTools]);

  const triggerHotkey = useCallback(async (action: HotkeyAction) => {
    if (action.special === "auto_format") {
      await startAutoFormat();
      return;
    }
    if (action.special === "insert_images") {
      await insertCellImages();
      return;
    }
    if (action.command) await execute(action.command, action.args ?? {});
  }, [execute, insertCellImages, startAutoFormat]);

  useEffect(() => {
    const shortcut = normalizeShortcutForTauri(settings.toggle_hotkey.trim());
    if (!shortcut) {
      setToggleHotkeyError("");
      return undefined;
    }

    let cancelled = false;
    let mine = false;

    const run = async () => {
      try {
        if (await isRegistered(shortcut)) await unregister(shortcut);
        if (cancelled) return;

        await register(shortcut, async (event) => {
          if (event.state !== "Pressed") return;
          try {
            const appWindow = getCurrentWindow();
            const visible = await appWindow.isVisible();
            const minimized = await appWindow.isMinimized();
            if (visible && !minimized) {
              await appWindow.hide();
            } else {
              await appWindow.show();
              await appWindow.unminimize();
              await appWindow.setAlwaysOnTop(true);
              if (!settings.always_on_top) await appWindow.setAlwaysOnTop(false);
              await appWindow.setFocus();
            }
          } catch (error) {
            setToggleHotkeyError(
              `${shortcut}를 눌렀지만 창을 열거나 숨기지 못했습니다: ${String(error)}`,
            );
          }
        });

        if (cancelled) {
          await unregister(shortcut).catch(() => undefined);
          return;
        }
        mine = true;
        setToggleHotkeyError("");
      } catch (error) {
        if (!cancelled) {
          setToggleHotkeyError(
            `${shortcut}를 등록하지 못했습니다. 다른 프로그램이 사용 중인지 확인하세요. (${String(error)})`,
          );
        }
      }
    };
    void run();

    return () => {
      cancelled = true;
      if (mine) void unregister(shortcut).catch(() => undefined);
    };
  }, [settings.always_on_top, settings.toggle_hotkey]);

  useEffect(() => {
    let cancelled = false;
    const mine = new Set<string>();

    const run = async () => {
      if (!settings.global_hotkeys_enabled) return;
      const byId = new Map(hotkeyActions.map((action) => [action.id, action]));
      const toggleShortcut = normalizeShortcutForTauri(settings.toggle_hotkey).toLocaleLowerCase();
      for (const [actionId, shortcut] of Object.entries(settings.global_hotkeys ?? {})) {
        const action = byId.get(actionId);
        const normalized = normalizeShortcutForTauri(shortcut);
        if (!action || !normalized || cancelled) continue;
        if (normalized.toLocaleLowerCase() === toggleShortcut) continue;
        try {
          if (await isRegistered(normalized)) await unregister(normalized);
          if (cancelled) return;
          await register(normalized, (event) => {
            if (event.state === "Pressed") void triggerHotkey(action);
          });
          if (cancelled) {
            await unregister(normalized).catch(() => undefined);
            return;
          }
          mine.add(normalized);
        } catch (error) {
          if (!cancelled) setStatus(`기능 단축키 ${shortcut} 등록 실패: ${String(error)}`);
        }
      }
    };
    void run();

    return () => {
      cancelled = true;
      for (const shortcut of mine) void unregister(shortcut).catch(() => undefined);
    };
  }, [hotkeyActions, settings.global_hotkeys, settings.global_hotkeys_enabled, settings.toggle_hotkey, triggerHotkey]);
  const filteredHotkeyActions = useMemo(() => {
    const query = hotkeySearch.trim().toLocaleLowerCase();
    if (!query) return hotkeyActions;
    return hotkeyActions.filter((action) =>
      `${action.category} ${action.label}`.toLocaleLowerCase().includes(query),
    );
  }, [hotkeyActions, hotkeySearch]);

  const saveToggleHotkey = async (shortcut: string) => {
    const next = { ...(settings.global_hotkeys ?? {}) };
    const signature = normalizeShortcutForTauri(shortcut).toLocaleLowerCase();
    for (const [id, value] of Object.entries(next)) {
      if (normalizeShortcutForTauri(value).toLocaleLowerCase() === signature) delete next[id];
    }
    setCapturingToggleHotkey(false);
    await saveSettings({ toggle_hotkey: shortcut, global_hotkeys: next });
  };

  const saveHotkey = async (actionId: string, shortcut: string) => {
    if (
      shortcut
      && normalizeShortcutForTauri(shortcut).toLocaleLowerCase()
        === normalizeShortcutForTauri(settings.toggle_hotkey).toLocaleLowerCase()
    ) {
      setCapturingHotkey("");
      setStatus("이 단축키는 JB에듀 폼 열기/숨기기에 사용 중입니다.");
      return;
    }
    const next = { ...(settings.global_hotkeys ?? {}) };
    for (const [id, value] of Object.entries(next)) {
      if (id !== actionId && value === shortcut) delete next[id];
    }
    if (shortcut) next[actionId] = shortcut;
    else delete next[actionId];
    setCapturingHotkey("");
    await saveSettings({ global_hotkeys: next });
  };

  const userItemsForManager = managerKind === "style"
    ? styles.filter((item) => item.user_item)
    : managerKind === "form"
      ? forms.filter((item) => item.user_item)
      : pages.filter((item) => item.user_item);
  const showUpdateReady = Boolean(updateReadyVersion && !updateDismissed);
  const showReleaseNotice = Boolean(releaseNotice.notes.length && !releaseDetailsOpen);
  const bannerCount = Number(showUpdateReady) + Number(showReleaseNotice);

  return (
    <div className={`app-shell ${bannerCount ? "has-update" : ""} ${bannerCount > 1 ? "has-two-updates" : ""}`}>
      <header className="toolbar">
        <div className="target-switch" aria-label="적용 대상" data-tour="target">
          <span>적용 대상</span>
          <button
            type="button"
            className={settings.target_mode === "hwp" ? "is-active" : ""}
            disabled={isBusy}
            onClick={() => void changeTargetMode("hwp")}
          >
            일반 한글
          </button>
          <button
            type="button"
            className={settings.target_mode === "kedufine" ? "is-active" : ""}
            disabled={isBusy}
            onClick={() => void changeTargetMode("kedufine")}
          >
            K-에듀파인 기안창
          </button>
        </div>
        <div className="toolbar-actions">
          <span className={`connection ${connected ? "is-connected" : ""}`} title={connected ? "연결됨" : "연결 필요"}>
            <span className="connection-dot" />
          </span>
          <button
            type="button"
            className="icon-button is-borderless"
            title="한글 다시 연결"
            aria-label="한글 다시 연결"
            disabled={isBusy}
            onClick={() => void execute("connect")}
          >
            <RefreshCw size={17} className={busy === "connect" ? "spin" : ""} />
          </button>
          <button type="button" className="settings-button" title="설정" aria-label="설정" onClick={() => setSettingsOpen(true)} data-tour="settings">
            <Settings size={15} />
            <span>설정</span>
          </button>
          {settings.target_mode === "hwp" && (
            <button type="button" className="icon-button window-layout-button" data-tour="window-layout"
              title="한글과 나란히 배치" aria-label="한글과 나란히 배치"
              disabled={isBusy} onClick={() => void alignWindowLayout()}>
              <Columns2 size={17} />
            </button>
          )}
          <button
            type="button"
            className="manual-button"
            data-tour="manual"
            title="사용자 매뉴얼"
            aria-label="사용자 매뉴얼"
            disabled={isBusy}
            onClick={() => void execute("open_manual")}
          >
            <BookOpen size={15} />
            <span>매뉴얼</span>
          </button>
        </div>
      </header>

      {showUpdateReady && (
        <section className="update-banner" aria-live="polite">
          <div>
            <strong>새 버전 {displayVersion(updateReadyVersion)}을 받아 두었습니다.</strong>
            <span>진행 중인 한글 작업을 마친 뒤 적용해 주세요.</span>
          </div>
          <div className="update-banner-actions">
            <button type="button" onClick={() => setUpdateDismissed(true)} disabled={updateBusy}>나중에</button>
            <button type="button" className="is-primary" onClick={() => void applyUpdate()} disabled={isBusy || updateBusy}>
              {updateBusy ? "적용 중" : "지금 적용"}
            </button>
          </div>
        </section>
      )}

      {showReleaseNotice && (
        <section className="update-banner is-updated" aria-live="polite">
          <div>
            <strong><PartyPopper size={14} />새 버전 v.{releaseNotice.current} 업데이트가 끝났습니다.</strong>
            <span>무엇이 달라졌는지 바로 확인할 수 있습니다.</span>
          </div>
          <div className="update-banner-actions">
            <button type="button" onClick={releaseNotice.done}>닫기</button>
            <button type="button" className="is-primary" onClick={() => setReleaseDetailsOpen(true)}>업데이트 내용 보기</button>
          </div>
        </section>
      )}

      <nav className="tabs" aria-label="기능 탭" data-tour="tabs" style={{ gridTemplateColumns: `repeat(${visibleTabs.length}, minmax(0, 1fr))` }}>
        {visibleTabs.map((id) => (
          <button
            type="button"
            key={id}
            className={activeTab === id ? "is-active" : ""}
            onClick={() => setActiveTab(id)}
          >
            {TAB_LABELS[id]}
          </button>
        ))}
      </nav>

      <main className="content" ref={contentRef}>
        {activeTab === "style" && (
          <section className="section" data-tour="style-area">
            {settings.target_mode === "hwp" && (
              <div className="auto-format-group">
                <div className="auto-format-heading-row">
                  <h2>서식 자동 지정</h2>
                  <label className="auto-format-profile-picker">
                    <span>사용할 설정</span>
                    <select
                      value={activeAutoFormatProfile?.id ?? ""}
                      disabled={isBusy}
                      aria-label="사용할 자동 서식 설정"
                      onChange={(event) => void selectAutoFormatProfile(event.target.value)}
                    >
                      {settings.auto_format_profiles.map((profile) => (
                        <option key={profile.id} value={profile.id}>{profile.name}</option>
                      ))}
                    </select>
                  </label>
                </div>
                <div className="auto-format-toolbar" data-tour="auto-format-toolbar">
                  <button
                    type="button"
                    className="auto-format-primary"
                    disabled={isBusy}
                    onClick={() => void startAutoFormat()}
                  >
                    <WandSparkles size={18} />
                    <span>전체 서식 자동 지정하기</span>
                  </button>
                  <button
                    type="button"
                    className="auto-format-stop"
                    disabled={busy !== "auto_format_report" || stopRequested}
                    onClick={() => void stopAutoFormat()}
                  >
                    <Square size={13} fill="currentColor" />
                    <span>중지</span>
                  </button>
                  <button
                    type="button"
                    className="auto-format-secondary"
                    onClick={() => setAutoFormatHelpOpen(true)}
                  >
                    <CircleHelp size={17} />
                    <span>사용방법</span>
                  </button>
                  <button
                    type="button"
                    className="auto-format-secondary"
                    onClick={openAutoFormatSettings}
                    data-tour="auto-format-settings"
                  >
                    <Settings size={17} />
                    <span>서식 설정</span>
                  </button>
                </div>
                <div className="direct-auto-format-grid" data-tour="auto-format-direct">
                  {DIRECT_AUTO_FORMAT_ROLES.map((role) => (
                    <button
                      type="button"
                      key={role.key}
                      disabled={isBusy}
                      onClick={() => void applySelectedAutoFormatRole(role.key)}
                    >
                      {role.label}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <div data-tour="manual-styles">
              <div className="section-heading-row">
                <h2>서식 수동 지정</h2>
                <button type="button" className="section-refresh" onClick={() => void loadCatalogs()} aria-label="새로고침">
                  <RefreshCw size={15} />
                </button>
              </div>
              <ContentGrid
                items={styles.filter((item) => item.available !== false)}
                kind="style"
                busy={isBusy}
                favorites={settings.card_favorites.style}
                onToggleFavorite={(key) => void toggleCardFavorite("style", key)}
                onRun={(item) => void execute("insert_style", { style_key: item.key })}
              />
            </div>
            <div className="user-action-bar" data-tour="user-style">
              <button type="button" className="primary-command" onClick={() => settings.target_mode === "kedufine"
                ? window.alert("내 서식은 일반 한글에서 사용할 부분을 블록 지정한 뒤 추가할 수 있습니다.")
                : addUserContentFromBlock("style")}>
                <Plus size={16} /> 내 서식 추가
              </button>
              <button type="button" onClick={() => setManagerKind("style")}>사용자 서식 관리</button>
            </div>
          </section>
        )}

        {activeTab === "edit" && (
          <>
            <nav className="subtabs" aria-label="편집도구">
              {(["table", "cell", "text"] as EditTabId[])
                .filter((id) => settings.target_mode === "hwp" || id !== "cell")
                .map((id) => (
                  <button
                    type="button"
                    key={id}
                    className={editTab === id ? "is-active" : ""}
                    onClick={() => setEditTab(id)}
                  >
                    {{ table: "표 작업", cell: "셀 정리", text: "글자 작업" }[id]}
                  </button>
                ))}
            </nav>

            {editTab === "table" && (
              <section className="section" data-tour="table-tools">
                <h2>표 작업</h2>
                <div className="table-tool-grid">
                  {tableTools.map((tool) => (
                    <button
                      type="button"
                      className="table-tool-card"
                      key={tool.action_id}
                      disabled={isBusy}
                      onClick={() => void execute("table_tool", { action_id: tool.action_id })}
                    >
                      <span className="table-tool-preview">
                        {tool.preview ? <TableToolImage source={tool.preview} /> : <Table2 size={30} />}
                      </span>
                      <span>{tool.title}</span>
                    </button>
                  ))}
                  <button type="button" className="table-tool-card" data-tour="table-draw" disabled={isBusy} onClick={() => void startTableDrawing()}>
                    <span className="table-tool-preview"><TableToolPreview kind="draw" /></span>
                    <span>표 그리기</span>
                  </button>
                  <button type="button" className="table-tool-card" disabled={isBusy} onClick={() => void execute("object_treat_as_char", { enabled: true })}>
                    <span className="table-tool-preview"><TableToolPreview kind="inline" /></span>
                    <span>글자처럼 취급</span>
                  </button>
                  <button type="button" className="table-tool-card" disabled={isBusy} onClick={() => void execute("object_treat_as_char", { enabled: false })}>
                    <span className="table-tool-preview"><TableToolPreview kind="floating" /></span>
                    <span>글자처럼 취급 해제</span>
                  </button>
                </div>
                {settings.target_mode === "hwp" && (
                  <div className="picture-tool" data-tour="cell-images">
                    <h3>셀에 그림 넣기</h3>
                    <p>{selection.active ? selection.label : "한글 표에서 셀 범위를 드래그하세요."}</p>
                    <div className="segmented">
                      {[
                        ["셀 안에 맞춤", "fit_inside"],
                        ["셀 너비에 맞춤", "fit_width"],
                        ["셀 크기에 맞춤", "stretch_to_cell"],
                      ].map(([label, value]) => (
                        <button
                          type="button"
                          key={value}
                          className={imageMode === value ? "is-active" : ""}
                          onClick={() => setImageMode(value)}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                    <button
                      type="button"
                      className="primary-command full-width"
                      disabled={!selection.active || isBusy}
                      onClick={() => void insertCellImages()}
                    >
                      <ImagePlus size={17} /> 셀에 그림 넣기
                    </button>
                    <button
                      type="button"
                      className="secondary-command full-width"
                      disabled={!selection.active || isBusy}
                      onClick={() => void execute("refit_cell_images", { size_mode: imageMode })}
                    >
                      <FileImage size={17} /> 기존 그림 다시 맞춤
                    </button>
                  </div>
                )}
              </section>
            )}

            {editTab === "cell" && settings.target_mode === "hwp" && (
              <section className="section cell-tools" data-tour="cell-tools">
                <div className="selection-strip">
                  <div className={selection.active ? "selection-mark is-active" : "selection-mark"}>
                    {selection.active ? <Check size={16} /> : <Unlink size={16} />}
                  </div>
                  <div>
                    <strong>{selection.dragging ? "셀 범위 선택 중" : selection.label}</strong>
                    <span>{selection.active ? `${selection.rows}행 × ${selection.columns}열` : "한글 표에서 적용할 셀 범위를 드래그하세요."}</span>
                  </div>
                  <button type="button" className="text-button" disabled={!selection.active || isBusy} onClick={() => void execute("clear_selection")}>해제</button>
                </div>
                <div className="tool-band">
                  <h3>엑셀 붙여넣기 흔적 정리</h3>
                  <p>셀 앞뒤 공백과 문단 배경·글자 음영을 없애고 글자색을 검정으로 정리합니다.</p>
                  <button type="button" className="primary-command full-width" disabled={!selection.active || isBusy} onClick={() => void execute("cell_cleanup_excel")}>
                    <Brush size={17} /> 공백·배경색 한 번에 정리
                  </button>
                </div>
                <div className="tool-band">
                  <h3>앞뒤 공백 정리</h3>
                  <p>띄어쓰기는 유지하고 셀 내용 앞뒤의 일반·전각·숨은 공백만 제거합니다.</p>
                  <button type="button" className="secondary-command full-width" disabled={!selection.active || isBusy} onClick={() => void execute("cell_clean_spaces")}>
                    <Eraser size={17} /> 불필요한 앞뒤 공백 제거
                  </button>
                </div>
                <div className="tool-band">
                  <h3>셀 내용 찾아바꾸기</h3>
                  <label>찾을 내용<input value={findText} onPointerDown={activateCellTextInput} onChange={(event) => setFindText(event.target.value)} /></label>
                  <label>바꿀 내용<input value={replaceText} onPointerDown={activateCellTextInput} onChange={(event) => setReplaceText(event.target.value)} /></label>
                  <button type="button" className="secondary-command full-width" disabled={!selection.active || isBusy || !findText} onClick={() => void execute("cell_text_action", { action: "find_replace", value: findText, replacement: replaceText })}>
                    찾아바꾸기 실행
                  </button>
                </div>
                <div className="tool-band">
                  <h3>셀마다 문자 붙이기</h3>
                  <label>추가할 문자<input value={addText} onPointerDown={activateCellTextInput} onChange={(event) => setAddText(event.target.value)} /></label>
                  <div className="split-commands">
                    <button type="button" disabled={!selection.active || isBusy || !addText} onClick={() => void execute("cell_text_action", { action: "prefix", value: addText })}>내용 앞에 추가</button>
                    <button type="button" disabled={!selection.active || isBusy || !addText} onClick={() => void execute("cell_text_action", { action: "suffix", value: addText })}>내용 뒤에 추가</button>
                  </div>
                </div>
              </section>
            )}

            {editTab === "text" && (
              <section className="section text-tools" data-tour="text-tools">
                <div className="text-colors">
                  <h2>글자색</h2>
                  {[
                    ["검정", [0, 0, 0], "black"],
                    ["빨강", [220, 0, 0], "red"],
                    ["파랑", [0, 70, 200], "blue"],
                    ["흰색", [255, 255, 255], "white"],
                  ].map(([label, rgb, tone]) => (
                    <button
                      type="button"
                      className={`color-button is-${tone}`}
                      key={String(label)}
                      disabled={isBusy}
                      onClick={() => void execute("apply_charshape", { font_color_rgb: rgb })}
                    >
                      {String(label)}
                    </button>
                  ))}
                </div>
                <div className="font-list">
                  {FONT_ROWS
                    .filter((row) => settings.target_mode === "hwp" || row.name !== "휴먼명조")
                    .map((row) => (
                      <div className="font-row" key={row.name}>
                        <button type="button" disabled={isBusy} onClick={() => void execute("apply_charshape", { font_name: row.name })}>{row.name}</button>
                        {row.sizes.map((size) => (
                          <button type="button" key={size} disabled={isBusy} onClick={() => void execute("apply_charshape", { font_name: row.name, font_size_pt: size })}>{size}</button>
                        ))}
                      </div>
                    ))}
                </div>
                <div className="script-tools">
                  <h2>첨자</h2>
                  <div className="action-grid three-columns">
                    <ActionButton label="위첨자" icon={<Superscript size={24} />} onClick={() => void execute("apply_charshape", { script_mode: "super" })} disabled={isBusy} />
                    <ActionButton label="아래첨자" icon={<Subscript size={24} />} onClick={() => void execute("apply_charshape", { script_mode: "sub" })} disabled={isBusy} />
                    <ActionButton label="첨자 해제" icon={<Type size={24} />} onClick={() => void execute("apply_charshape", { script_mode: "normal" })} disabled={isBusy} />
                  </div>
                </div>
                {settings.target_mode === "hwp" && (
                  <div className="spacing-tools">
                    <h2>자간 정리</h2>
                    <div className="action-grid three-columns">
                      <ActionButton label="자간 정리 1단계" icon={<AlignHorizontalSpaceAround size={22} />} onClick={() => void execute("spacing_cleanup", { adjust_count: 3 })} disabled={isBusy} tone="accent" />
                      <ActionButton label="자간 정리 2단계" icon={<AlignHorizontalSpaceAround size={22} strokeWidth={2.4} />} onClick={() => void execute("spacing_cleanup", { adjust_count: 5 })} disabled={isBusy} tone="accent" />
                      <ActionButton label="자간 초기화" icon={<RotateCcw size={22} />} onClick={() => void execute("spacing_reset")} disabled={isBusy} />
                    </div>
                  </div>
                )}
              </section>
            )}
          </>
        )}

        {activeTab === "chars" && (
          <section className="section" data-tour="characters">
            <div className="user-action-bar is-top character-actions" data-tour="character-actions">
              <button type="button" className="primary-command" disabled={isBusy} onClick={() => openSymbolEditor("new")}><Plus size={16} /> 내 문자표 추가</button>
              <button type="button" disabled={isBusy} onClick={() => { setComposeError(""); setComposeOpen(true); }}><Combine size={16} /> 글자 겹치기</button>
              <button type="button" disabled={isBusy} aria-pressed={characterOrderEditing} onClick={() => setCharacterOrderEditing((current) => !current)}>
                {characterOrderEditing ? <Check size={16} /> : <ArrowUpDown size={16} />}{characterOrderEditing ? "완료" : "순서 변경"}
              </button>
            </div>
            {orderedCharacterGroups.map((group, groupIndex) => (
              <div className="character-group" key={group.id} data-character-group-id={group.id}>
                <div className="group-heading">
                  <h2>{group.user_item ? `내 문자표 · ${group.title}` : group.title}</h2>
                  {(group.user_item || characterOrderEditing) && (
                    <span className="inline-actions">
                      {characterOrderEditing && <>
                        <button type="button" disabled={isBusy || groupIndex === 0} title="맨 위로 이동" aria-label={`${group.title} 맨 위로 이동`} onClick={() => void moveCharacterGroup(group.id, "first")}><ArrowUpToLine size={14} /></button>
                        <button type="button" disabled={isBusy || groupIndex === 0} title="위로 이동" aria-label={`${group.title} 위로 이동`} onClick={() => void moveCharacterGroup(group.id, -1)}><ArrowUp size={14} /></button>
                        <button type="button" disabled={isBusy || groupIndex === orderedCharacterGroups.length - 1} title="아래로 이동" aria-label={`${group.title} 아래로 이동`} onClick={() => void moveCharacterGroup(group.id, 1)}><ArrowDown size={14} /></button>
                        <button type="button" disabled={isBusy || groupIndex === orderedCharacterGroups.length - 1} title="맨 아래로 이동" aria-label={`${group.title} 맨 아래로 이동`} onClick={() => void moveCharacterGroup(group.id, "last")}><ArrowDownToLine size={14} /></button>
                      </>}
                      {group.user_item && <>
                      <button type="button" disabled={isBusy} onClick={() => openSymbolEditor(group)} title="수정" aria-label="수정"><Pencil size={14} /></button>
                      <button
                        type="button"
                        disabled={isBusy}
                        onClick={() => { setSymbolDeleteError(""); setSymbolDeleteTarget(group); }}
                        title="삭제"
                        aria-label={`${group.title} 삭제`}
                      >
                        <Trash2 size={14} />
                      </button>
                      </>}
                    </span>
                  )}
                </div>
                <div className="character-grid">
                  {group.chars.map((value, index) => (
                    <button type="button" key={`${value}-${index}`} disabled={isBusy}
                      aria-label={group.presentation === "square" ? `네모문자 ${value}` : value}
                      onClick={() => void (group.presentation === "square" ? insertComposedCharacter(value, "square") : insertCharacter(value))}>
                      {group.presentation === "square" ? <span className="square-character">{value}</span> : value}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </section>
        )}

        {activeTab === "symbol" && settings.target_mode === "hwp" && (
          <section className="section" data-tour="symbols">

            <nav className="subtabs" aria-label="심볼 분류">
              {pictureGroups.map((group, index) => (
                <button type="button" key={group.title} className={pictureGroupIndex === index ? "is-active" : ""} onClick={() => setPictureGroupIndex(index)}>{group.title}</button>
              ))}
            </nav>
            <div className="symbol-grid">
              {orderFavoriteCards(pictureGroups[pictureGroupIndex]?.items ?? [], settings.card_favorites.symbol).map((item) => (
                <FavoriteCard key={item.key} title={item.title} active={settings.card_favorites.symbol.includes(cardFavoriteKey(item))}
                  busy={isBusy} onToggle={() => void toggleCardFavorite("symbol", cardFavoriteKey(item))}>
                  <button type="button" className="symbol-card" disabled={isBusy} onClick={() => void execute("insert_picture_symbol", { item_key: item.key })}>
                    <span className={`symbol-preview${item.preview_on_dark ? " symbol-preview-dark" : ""}`}>
                      {item.preview ? <img src={item.preview} alt="" /> : <FileImage size={30} />}
                    </span>
                    <strong>{item.title}</strong>
                  </button>
                </FavoriteCard>
              ))}
            </div>
            <div className="user-action-bar">
              <button type="button" className="primary-command" disabled={isBusy} onClick={() => void addPictureSymbols()}>
                <ImagePlus size={16} /> 내 심볼 추가
              </button>
              <button type="button" onClick={() => setPictureSymbolManagerOpen(true)}>관리</button>
            </div>
          </section>
        )}
        {activeTab === "forms" && settings.target_mode === "hwp" && (
          <section className="section" data-tour="forms">
            <div className="form-use-mode" role="group" aria-label="양식 사용 방식">
              <span>양식 사용 방식</span>
              <div>
                <button type="button" className={formUseMode === "insert" ? "is-active" : ""} onClick={() => setFormUseMode("insert")}>현재 문서에 삽입</button>
                <button type="button" className={formUseMode === "new_document" ? "is-active" : ""} onClick={() => setFormUseMode("new_document")}>새 문서로 열기</button>
              </div>
            </div>
            <ContentGrid items={forms} kind="form" busy={isBusy}
              favorites={settings.card_favorites.form}
              onToggleFavorite={(key) => void toggleCardFavorite("form", key)}
              onRun={(item) => void execute("insert_form", { item_key: item.key, mode: formUseMode })} />
            <div className="user-action-bar">
              <button type="button" className="primary-command" onClick={() => setSourceKind("form")}><Plus size={16} /> 내 양식 추가</button>
              <button type="button" onClick={() => setManagerKind("form")}>사용자 양식 관리</button>
            </div>
          </section>
        )}
        {activeTab === "forms" && settings.target_mode === "kedufine" && (
          <section className="section" data-tour="forms">
            <nav className="subtabs" role="tablist" aria-label="기안문 양식 분류">
              {(["internal", "outgoing", ...(kedufineForms.some((item) => item.legacy) ? ["legacy"] : [])] as KedufineCategory[]).map((category) => (
                <button key={category} type="button" role="tab" aria-selected={kedufineCategory === category}
                  className={kedufineCategory === category ? "is-active" : ""}
                  onClick={() => setKedufineCategory(category)}>
                  {category === "internal" ? "내부결재" : category === "outgoing" ? "발송용" : "이전 양식"}
                </button>
              ))}
            </nav>
            <div className="content-card-grid form-grid kedufine-form-grid">
              {orderFavoriteCards(kedufineForms.filter((item) => item.category === kedufineCategory), settings.card_favorites.kedufine_form).map((item) => (
                <FavoriteCard key={item.key} title={item.title} active={settings.card_favorites.kedufine_form.includes(item.key)}
                  busy={isBusy || item.legacy} onToggle={() => void toggleCardFavorite("kedufine_form", item.key)}>
                  <button type="button" className="content-card kedufine-form-card"
                    disabled={isBusy || item.legacy}
                    onClick={() => void execute("insert_kedufine_form", { item_key: item.key })}>
                    <span className="content-preview kedufine-form-preview">
                      {item.legacy ? "이전 파일 양식" : item.preview}
                    </span>
                    <strong className="content-title">{item.title}</strong>
                  </button>
                </FavoriteCard>
              ))}
            </div>
            <div className="user-action-bar">
              <button type="button" className="primary-command" disabled={isBusy} onClick={addKedufineForm}><Plus size={16} /> 내 기안문 양식 추가</button>
              <button type="button" onClick={() => setKedufineFormManagerOpen(true)}>사용자 양식 관리</button>
            </div>
          </section>
        )}

        {activeTab === "page" && settings.target_mode === "hwp" && (
          <section className="section" data-tour="pages">
            <div className="page-option-row">
              <span>적용 범위</span>
              <div className="segmented page-options" role="group" aria-label="편집용지 적용 범위">
                <button type="button" aria-pressed={pageScope === "document"} className={pageScope === "document" ? "is-active" : ""} disabled={isBusy} onClick={() => setPageScope("document")}>문서 전체</button>
                <button type="button" aria-pressed={pageScope === "page"} className={pageScope === "page" ? "is-active" : ""} disabled={isBusy} onClick={() => setPageScope("page")}>현재 페이지만</button>
              </div>
            </div>
            <ContentGrid items={pages} kind="page" busy={isBusy}
              favorites={settings.card_favorites.page}
              onToggleFavorite={(key) => void toggleCardFavorite("page", key)}
              onRun={(item) => void execute("apply_page", { item_key: item.key, scope: pageScope })} />
            <div className="user-action-bar">
              <button type="button" className="primary-command" onClick={() => openPageEditor("new")}><Plus size={16} /> 내 편집용지 추가</button>
              <button type="button" onClick={() => setManagerKind("page")}>사용자 편집용지 관리</button>
            </div>
          </section>
        )}
      </main>

      <footer className={`status-bar ${status.includes("오류") || status.includes("실패") ? "is-error" : ""}`} data-tour="status">
        {isBusy ? <LoaderCircle size={15} className="spin" /> : <span className="status-dot" />}
        <span>{status}</span>
      </footer>

      {settingsOpen && (
        <Modal title="설정" onClose={() => { setSettingsOpen(false); setCapturingToggleHotkey(false); }} wide className="settings-modal">
          <div className="settings-sections">
            <section>
              <h3>화면</h3>
              <label className="toggle-row">
                <span><strong>항상 위로 표시</strong><small>한글 편집 중에도 JB에듀 폼을 앞에 표시합니다.</small></span>
                <input type="checkbox" checked={settings.always_on_top} onChange={(event) => void saveSettings({ always_on_top: event.target.checked })} />
              </label>
              <label className="toggle-row">
                <span><strong>닫기 시 트레이로 최소화</strong><small>X 버튼으로 닫아도 알림 영역에서 계속 실행합니다.</small></span>
                <input
                  type="checkbox"
                  checked={settings.close_to_tray}
                  onChange={(event) => void (async () => {
                    const enabled = event.target.checked;
                    await saveSettings({
                      close_to_tray: enabled,
                      start_minimized: enabled ? settings.start_minimized : false,
                    });
                    if (!enabled && integration.startup) {
                      const result = await execute<{ integration: IntegrationStatus }>("integration_set", {
                        kind: "startup",
                        enabled: true,
                        start_minimized: false,
                      });
                      if (result?.data?.integration) setIntegration(result.data.integration);
                    }
                  })()}
                />
              </label>
              <label className="setting-field-row">
                <span><strong>시작 위치</strong><small>프로그램을 열 때 표시할 위치를 선택합니다.</small></span>
                <select
                  value={settings.start_position}
                  onChange={(event) => void saveSettings({
                    start_position: event.target.value as AppSettings["start_position"],
                  })}
                >
                  <option value="top_right">오른쪽 위</option>
                  <option value="center">가운데</option>
                  <option value="last">마지막 위치</option>
                </select>
              </label>
              <label className="toggle-row">
                <span><strong>마지막 위치 기억</strong><small>창을 옮긴 위치를 다음 실행 때 다시 사용합니다.</small></span>
                <input
                  type="checkbox"
                  checked={settings.remember_window_position}
                  onChange={(event) => void saveSettings({ remember_window_position: event.target.checked })}
                />
              </label>
            </section>
            <section>
              <h3>시작 동작</h3>
              <label className="setting-field-row">
                <span><strong>시작 시 적용 대상</strong><small>프로그램을 열었을 때 기본 작업 환경입니다.</small></span>
                <select
                  value={settings.start_mode}
                  onChange={(event) => void saveSettings({
                    start_mode: event.target.value as AppSettings["start_mode"],
                  })}
                >
                  <option value="hwp">일반 한글</option>
                  <option value="kedufine">K-에듀파인 기안창</option>
                </select>
              </label>
            </section>
            <section>
              <h3>Windows 통합</h3>
              <label className="toggle-row">
                <span><strong>Windows 시작 시 자동 실행</strong><small>현재 사용자 계정에 등록합니다.</small></span>
                <input
                  type="checkbox"
                  checked={integration.startup}
                  onChange={(event) => void (async () => {
                    const result = await execute<{ integration: IntegrationStatus }>("integration_set", {
                      kind: "startup",
                      enabled: event.target.checked,
                      start_minimized: settings.start_minimized,
                    });
                    if (result?.data?.integration) setIntegration(result.data.integration);
                  })()}
                />
              </label>
              <label className="toggle-row">
                <span><strong>Windows 시작 시 트레이로 시작</strong><small>자동 실행할 때 창을 바로 띄우지 않습니다.</small></span>
                <input
                  type="checkbox"
                  checked={settings.start_minimized}
                  disabled={!settings.close_to_tray || !integration.startup}
                  onChange={(event) => void (async () => {
                    const enabled = event.target.checked;
                    await saveSettings({ start_minimized: enabled });
                    const result = await execute<{ integration: IntegrationStatus }>("integration_set", {
                      kind: "startup",
                      enabled: true,
                      start_minimized: enabled,
                    });
                    if (result?.data?.integration) setIntegration(result.data.integration);
                  })()}
                />
              </label>
              <label className="toggle-row">
                <span><strong>시작 메뉴 등록</strong><small>Windows 검색에서 프로그램 이름으로 찾을 수 있게 합니다.</small></span>
                <input
                  type="checkbox"
                  checked={integration.start_menu}
                  onChange={(event) => void (async () => {
                    const result = await execute<{ integration: IntegrationStatus }>("integration_set", {
                      kind: "start_menu",
                      enabled: event.target.checked,
                    });
                    if (result?.data?.integration) setIntegration(result.data.integration);
                  })()}
                />
              </label>
            </section>
            <section>
              <h3>JB에듀 폼 열기/숨기기</h3>
              <div className="setting-field-row toggle-hotkey-setting">
                <span><strong>창 열기·숨기기 단축키</strong><small>기능 단축키 사용 여부와 관계없이 언제든 JB에듀 폼을 열거나 숨깁니다.</small></span>
                <div className="toggle-hotkey-actions">
                  <button
                    type="button"
                    className={capturingToggleHotkey ? "is-capturing" : ""}
                    onClick={() => setCapturingToggleHotkey(true)}
                  >{settings.toggle_hotkey || "지정"}</button>
                  <button
                    type="button"
                    className="icon-button"
                    disabled={settings.toggle_hotkey === "Ctrl+Alt+H"}
                    onClick={() => void saveToggleHotkey("Ctrl+Alt+H")}
                    title="기본 단축키로 되돌리기"
                    aria-label="기본 단축키로 되돌리기"
                  ><RotateCcw size={13} /></button>
                </div>
              </div>
              {capturingToggleHotkey && (
                <div
                  className="hotkey-capture standalone-hotkey-capture"
                  tabIndex={0}
                  autoFocus
                  onKeyDown={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    if (event.key === "Escape") {
                      setCapturingToggleHotkey(false);
                      return;
                    }
                    const shortcut = shortcutFromEvent(event);
                    if (shortcut === "") {
                      setStatus("Ctrl, Alt, Shift 또는 Win 중 하나를 함께 누르세요.");
                      return;
                    }
                    if (shortcut) void saveToggleHotkey(shortcut);
                  }}
                >
                  <strong>새 열기/숨기기 단축키를 누르세요.</strong>
                  <span>Esc를 누르면 취소합니다.</span>
                </div>
              )}
              {toggleHotkeyError && <p className="setting-warning">{toggleHotkeyError}</p>}
            </section>
            <section>
              <h3>기능 전역 단축키</h3>
              <label className="toggle-row">
                <span><strong>기능 단축키 사용</strong><small>JB에듀 폼이 트레이에 있어도 지정한 문서 기능을 실행합니다.</small></span>
                <input type="checkbox" checked={settings.global_hotkeys_enabled} onChange={(event) => void saveSettings({ global_hotkeys_enabled: event.target.checked })} />
              </label>
              <button type="button" className="secondary-command full-width" onClick={() => setHotkeyOpen(true)}>기능 단축키 설정</button>
            </section>
            <section data-tour="settings-updates">
              <h3>업데이트</h3>
              <label className="toggle-row">
                <span><strong>시작할 때 자동 업데이트 확인</strong><small>서명된 최신 설치파일을 미리 받아 두고 적용 시점을 선택합니다.</small></span>
                <input
                  type="checkbox"
                  checked={settings.check_updates_on_startup}
                  onChange={(event) => void saveSettings({ check_updates_on_startup: event.target.checked })}
                />
              </label>
              <div className="update-row">
                <span>{updateStatus}</span>
                <div className="update-actions">
                  <button type="button" onClick={() => void checkUpdate(true)} disabled={isBusy || updateBusy}>
                    {updateBusy ? <LoaderCircle size={13} className="spin" /> : <RefreshCw size={13} />}
                    지금 확인
                  </button>
                  {updateReadyVersion && (
                    <button type="button" onClick={() => void applyUpdate()} disabled={isBusy || updateBusy}>
                      지금 적용
                    </button>
                  )}
                  <button type="button" onClick={() => setReleaseHistoryOpen(true)}>
                    <History size={13} />
                    업데이트 내역
                  </button>
                </div>
              </div>
            </section>
            <section>
              <h3>탭 순서</h3>
              <div className="tab-order-list">
                {settings.tab_order.map((id, index) => (
                  <div key={id}>
                    <span>{TAB_LABELS[id as TabId] ?? id}</span>
                    <button
                      type="button"
                      disabled={index === 0}
                      onClick={() => {
                        const order = [...settings.tab_order];
                        [order[index - 1], order[index]] = [order[index], order[index - 1]];
                        void saveSettings({ tab_order: order });
                      }}
                      aria-label="위로"
                    ><ChevronUp size={15} /></button>
                    <button
                      type="button"
                      disabled={index === settings.tab_order.length - 1}
                      onClick={() => {
                        const order = [...settings.tab_order];
                        [order[index], order[index + 1]] = [order[index + 1], order[index]];
                        void saveSettings({ tab_order: order });
                      }}
                      aria-label="아래로"
                    ><ChevronDown size={15} /></button>
                  </div>
                ))}
              </div>
            </section>
            <section data-tour="settings-backup">
              <h3>백업과 복원</h3>
              <div className="settings-command-grid settings-backup-grid">
                <button type="button" onClick={() => void backupUserData()} disabled={isBusy}>
                  <Download size={14} />
                  설정·내 자료 백업
                </button>
                <button type="button" onClick={() => void restoreUserData()} disabled={isBusy}>
                  <Upload size={14} />
                  백업 파일 복원
                </button>
              </div>
            </section>
            <section>
              <h3>도움말과 관리</h3>
              <div className="settings-command-grid">
                <button type="button" onClick={openTutorial}>튜토리얼 다시 보기</button>
                <button type="button" onClick={() => void execute("open_manual")}><BookOpen size={14} /> 사용자 매뉴얼</button>
                <button type="button" onClick={() => void execute("open_support", { kind: "changelog" })}>변경 기록</button>
                <button type="button" onClick={() => void execute("open_support", { kind: "settings" })}>설정 폴더</button>
                <button type="button" onClick={() => void execute("open_support", { kind: "crash" })}>오류 기록</button>
                <button type="button" className="danger-command" onClick={() => void resetSettings()}>설정 초기화</button>
              </div>
              <p className="version-line">현재 버전 {VERSION}</p>
            </section>
          </div>
        </Modal>
      )}

      {releaseDetailsOpen && (
        <ReleaseNotesDialog
          title={`v.${releaseNotice.current} 업데이트 내용`}
          notes={releaseNotice.notes}
          current={releaseNotice.current}
          onClose={() => {
            setReleaseDetailsOpen(false);
            releaseNotice.done();
          }}
        />
      )}

      {releaseHistoryOpen && (
        <ReleaseNotesDialog
          title="업데이트 내역"
          notes={RELEASE_NOTES}
          current={releaseNotice.current}
          onClose={() => setReleaseHistoryOpen(false)}
        />
      )}

      {autoFormatHelpOpen && (
        <Modal title="서식 자동 지정하기 사용방법" onClose={() => setAutoFormatHelpOpen(false)} wide className="auto-format-help-modal">
          <div className="auto-format-help">
            <p>생성형 AI로 작성한 보고서·계획서 초안을 한글에 붙여 넣은 뒤, 원하는 범위를 선택하면 문서 구조에 맞춰 서식을 자동으로 적용합니다.</p>
            <ol>
              <li><strong>초안 작성</strong><span>GPT, Gemini, Claude 등 생성형 AI에서 보고서나 계획서 초안을 작성합니다.</span></li>
              <li><strong>한글에 붙여넣기</strong><span>완성된 초안 텍스트를 복사해 한글 문서에 붙여 넣습니다.</span></li>
              <li><strong>범위 선택</strong><span>서식을 적용할 텍스트 전체를 한글에서 블록 지정합니다.</span></li>
              <li><strong>자동 적용</strong><span>'전체 서식 자동 지정하기' 버튼을 누릅니다.</span></li>
            </ol>
            <div className="help-note">문서 제목은 선택 범위의 처음 부분에서 찾고, 제목·소제목·본문·참고·표 구조를 분석해 자동으로 정리합니다.</div>
            <button type="button" className="secondary-command full-width" onClick={() => void execute("open_manual", { section: "auto" })}>
              <BookOpen size={16} /> 매뉴얼에서 사용방법 보기
            </button>
            <button type="button" className="primary-command full-width" onClick={() => setAutoFormatHelpOpen(false)}>확인</button>
          </div>
        </Modal>
      )}

      {autoFormatSettingsOpen && (
        <Modal
          title="자동 서식 설정"
          onClose={() => setAutoFormatSettingsOpen(false)}
          wide
          className="auto-format-settings-modal"
        >
          <div className="auto-format-settings-form">
            <section className="auto-format-profile-section">
              <div className="auto-format-section-heading">
                <h3>저장된 설정</h3>
              </div>
              <div className="auto-format-profile-editor">
                <select
                  value={autoFormatProfileIdDraft}
                  aria-label="편집할 자동 서식 설정"
                  onChange={(event) => selectAutoFormatProfileDraft(event.target.value)}
                >
                  {autoFormatProfilesDraft.map((profile) => (
                    <option key={profile.id} value={profile.id}>{profile.name}</option>
                  ))}
                </select>
                <button type="button" disabled={autoFormatProfilesDraft.length >= MAX_AUTO_FORMAT_PROFILES} onClick={() => addAutoFormatProfile(false)}>
                  <Plus size={14} /> 새 설정
                </button>
                <button type="button" disabled={autoFormatProfilesDraft.length >= MAX_AUTO_FORMAT_PROFILES} onClick={() => addAutoFormatProfile(true)}>
                  <Copy size={14} /> 복제
                </button>
                <button type="button" onClick={renameAutoFormatProfile}>
                  <Pencil size={14} /> 이름 변경
                </button>
                <button
                  type="button"
                  className="danger-command"
                  disabled={autoFormatProfilesDraft.length <= 1}
                  onClick={deleteAutoFormatProfile}
                >
                  <Trash2 size={14} /> 삭제
                </button>
              </div>
            </section>
            <section className="auto-format-template-section">
              <div className="auto-format-section-heading">
                <h3>문서제목·1단계 제목 양식</h3>
              </div>
              <div className="auto-format-template-grid">
                <div className="auto-title-template-control">
                  <strong>문서제목</strong>
                  <select
                    value={autoFormatDraft.document_title_template}
                    onChange={(event) => setAutoFormatDraft((current) => ({
                      ...current,
                      document_title_template: event.target.value,
                    }))}
                  >
                    {!documentTitleTemplates.some((item) => item.key === autoFormatDraft.document_title_template) && (
                      <option value="auto-title-builtin:document_title">기본 문서제목</option>
                    )}
                    {documentTitleTemplates.map((item) => (
                      <option key={item.key} value={item.key}>
                        {item.user_item ? "내 제목 양식 · " + item.title : item.title}
                      </option>
                    ))}
                  </select>
                  <div className="auto-title-template-actions">
                    <button type="button" onClick={() => void beginAutoTitleRegistration("document_title")}>
                      기존 제목 양식 추가
                    </button>
                    <button type="button" onClick={() => setAutoTitleManagerRole("document_title")}>
                      관리
                    </button>
                  </div>
                </div>
                <div className="auto-title-template-control">
                  <strong>1단계 제목</strong>
                  <select
                    value={autoFormatDraft.title_template}
                    onChange={(event) => setAutoFormatDraft((current) => ({
                      ...current,
                      title_template: event.target.value,
                    }))}
                  >
                    {!levelOneTitleTemplates.some((item) => item.key === autoFormatDraft.title_template) && (
                      <option value="auto-title-builtin:title">기본 1단계 제목</option>
                    )}
                    {levelOneTitleTemplates.map((item) => (
                      <option key={item.key} value={item.key}>
                        {item.user_item ? "내 제목 양식 · " + item.title : item.title}
                      </option>
                    ))}
                  </select>
                  <div className="auto-title-template-actions">
                    <button type="button" onClick={() => void beginAutoTitleRegistration("title")}>
                      기존 제목 양식 추가
                    </button>
                    <button type="button" onClick={() => setAutoTitleManagerRole("title")}>
                      관리
                    </button>
                  </div>
                </div>
              </div>
            </section>

            <section className="auto-format-role-section">
              <div className="auto-format-section-heading">
                <h3>글자 및 번호 서식</h3>
                <p>문서제목부터 표 안 글자까지 글자 모양과 번호를 정합니다.</p>
              </div>
              <div className="auto-format-role-header" aria-hidden="true">
                <span>구분</span><span>글꼴</span><span>크기</span><span>굵게</span><span>번호/앞 기호</span>
              </div>
              <div className="auto-format-role-list">
                {AUTO_FORMAT_ROLES.map((role) => {
                  const value = autoFormatDraft.roles[role.key];
                  return (
                    <div className="auto-format-role-row" key={role.key}>
                      <span className="auto-format-role-name">
                        <strong>{role.label}</strong>
                        <small>{role.example}</small>
                      </span>
                      <input
                        type="text"
                        list="auto-format-font-list"
                        value={value.font}
                        title="글꼴 이름을 입력하거나 목록에서 선택"
                        aria-label={`${role.label} 글꼴`}
                        onChange={(event) => updateAutoFormatRole(role.key, { font: event.target.value })}
                      />
                      <input
                        type="number"
                        min={5}
                        max={72}
                        step={1}
                        value={value.size}
                        aria-label={`${role.label} 글자 크기`}
                        onChange={(event) => updateAutoFormatRole(role.key, { size: Number(event.target.value) })}
                      />
                      <label className="auto-format-bold-toggle" title="굵게">
                        <input
                          type="checkbox"
                          checked={value.bold}
                          aria-label={`${role.label} 굵게`}
                          onChange={(event) => updateAutoFormatRole(role.key, { bold: event.target.checked })}
                        />
                        <strong>B</strong>
                      </label>
                      {role.markerOptions ? (
                        <div className="auto-format-marker-control">
                          <select
                            value={value.marker ?? role.markerOptions[0].value}
                            aria-label={`${role.label} 번호 또는 앞 기호`}
                            onChange={(event) => updateAutoFormatRole(role.key, { marker: event.target.value })}
                          >
                            {role.markerOptions.map((option) => (
                              <option
                                key={option.value}
                                value={option.value}
                                disabled={
                                  (role.key === "title" || role.key === "subtitle" || role.key === "subsubtitle")
                                  && HEADING_SEQUENCE_MARKERS.has(option.value)
                                  && HEADING_ROLE_KEYS.some(
                                    (key) => key !== role.key && autoFormatDraft.roles[key].marker === option.value,
                                  )
                                }
                              >
                                {option.label}
                              </option>
                            ))}
                          </select>
                          {value.marker === "custom" && (
                            <input
                              type="text"
                              maxLength={8}
                              value={value.custom_marker ?? ""}
                              placeholder="예: ▶"
                              aria-label={`${role.label} 사용자 기호`}
                              onChange={(event) => updateAutoFormatRole(role.key, { custom_marker: event.target.value })}
                            />
                          )}
                        </div>
                      ) : (
                        <span className="auto-format-no-marker">-</span>
                      )}
                    </div>
                  );
                })}
              </div>
              <p className="auto-format-role-note">1·2·3단계 제목은 다른 단계에서 사용 중인 순번 형식을 중복 선택할 수 없습니다.</p>
              <datalist id="auto-format-font-list">
                {fontNames.map((font) => <option key={font} value={font} />)}
              </datalist>

            </section>

            <div className="auto-format-settings-actions">
              <button
                type="button"
                onClick={() => setAutoFormatDraft(cloneAutoFormatSettings(DEFAULT_AUTO_FORMAT_SETTINGS))}
              >
                기본값
              </button>
              <span />
              <button type="button" onClick={() => setAutoFormatSettingsOpen(false)}>취소</button>
              <button type="button" className="primary-command" onClick={() => void saveAutoFormatSettings()}>
                저장
              </button>
            </div>
          </div>
        </Modal>
      )}

      {hotkeyOpen && (
        <Modal title="기능 전역 단축키 설정" onClose={() => { setHotkeyOpen(false); setCapturingHotkey(""); }} wide>
          <div className="hotkey-editor">
            <input
              className="hotkey-search"
              value={hotkeySearch}
              onChange={(event) => setHotkeySearch(event.target.value)}
              placeholder="기능 검색"
              aria-label="기능 검색"
            />
            {capturingHotkey && (
              <div
                className="hotkey-capture"
                tabIndex={0}
                autoFocus
                onKeyDown={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  if (event.key === "Escape") {
                    setCapturingHotkey("");
                    return;
                  }
                  const shortcut = shortcutFromEvent(event);
                  if (shortcut === "") {
                    setStatus("Ctrl, Alt, Shift 또는 Win 중 하나를 함께 누르세요.");
                    return;
                  }
                  if (shortcut) void saveHotkey(capturingHotkey, shortcut);
                }}
              >
                <strong>새 단축키를 누르세요.</strong>
                <span>실제로 누른 보조키와 일반 키만 기록됩니다. Esc를 누르면 취소합니다.</span>
              </div>
            )}
            <div className="hotkey-list">
              {filteredHotkeyActions.map((action) => (
                <div className="hotkey-row" key={action.id}>
                  <span><small>{action.category}</small><strong>{action.label}</strong></span>
                  <button
                    type="button"
                    className={capturingHotkey === action.id ? "is-capturing" : ""}
                    onClick={() => setCapturingHotkey(action.id)}
                  >
                    {settings.global_hotkeys?.[action.id] || "지정"}
                  </button>
                  <button
                    type="button"
                    className="icon-button is-borderless"
                    disabled={!settings.global_hotkeys?.[action.id]}
                    onClick={() => void saveHotkey(action.id, "")}
                    aria-label="단축키 해제"
                  >
                    <X size={14} />
                  </button>
                </div>
              ))}
            </div>
          </div>
        </Modal>
      )}

      <TutorialOverlay
        open={tutorialOpen}
        targetMode={settings.target_mode}
        onNavigate={navigateTutorial}
        onClose={() => void completeTutorial()}
      />

      {sourceKind && (
        <Modal title="내 양식 추가" onClose={() => setSourceKind(null)}>
          <div className="source-choice">
            <button
              type="button"
              onClick={() => addUserContentFromBlock("form")}
            >
              <FilePlus2 size={25} />
              <strong>블록 지정한 내용으로 추가</strong>
              <span>한글 문서에서 추가할 내용을 먼저 블록 지정한 뒤 등록합니다.</span>
            </button>
            <button
              type="button"
              className="is-recommended"
              onClick={() => void addUserContentFromFile()}
            >
              <FileText size={25} /><strong>한글 파일에서 추가</strong><span>HWP 또는 HWPX 파일을 선택합니다.</span>
            </button>
          </div>
        </Modal>
      )}

      {autoFormatRoleGuide && (
        <Modal
          title="선택 영역 서식 적용 안내"
          onClose={() => setAutoFormatRoleGuide(null)}
          className="direct-auto-format-guide-modal"
        >
          <div className="auto-title-selection-guide">
            <p>
              한글에서 서식을 적용할 텍스트를 블록 지정한 후 ‘{DIRECT_AUTO_FORMAT_ROLES.find((role) => role.key === autoFormatRoleGuide)?.label}’ 버튼을 눌러주세요.
            </p>
            <button
              type="button"
              className="primary-command full-width"
              onClick={() => setAutoFormatRoleGuide(null)}
            >
              확인
            </button>
          </div>
        </Modal>
      )}

      {autoTitleSelectionGuideRole && (
        <Modal
          title="제목 양식 추가 안내"
          onClose={() => setAutoTitleSelectionGuideRole(null)}
          className="auto-title-selection-guide-modal"
        >
          <div className="auto-title-selection-guide">
            <p>
              {autoTitleSelectionGuideRole === "document_title"
                ? "기존 보고서에서 사용하던 문서제목 양식을 그대로 추가하려면, 한글에서 해당 문서제목 양식 전체를 블록 지정한 후 ‘기존 제목 양식 추가’ 버튼을 눌러주세요."
                : "기존 보고서에서 사용하던 1단계 제목 양식을 그대로 추가하려면, 한글에서 번호와 제목이 포함된 제목 양식 전체를 블록 지정한 후 ‘기존 제목 양식 추가’ 버튼을 눌러주세요."}
            </p>
            <button
              type="button"
              className="primary-command full-width"
              onClick={() => setAutoTitleSelectionGuideRole(null)}
            >
              확인
            </button>
          </div>
        </Modal>
      )}

      {autoTitleRegistration && (
        <Modal
          title={autoTitleRegistration.role === "document_title" ? "문서제목 양식 추가" : "1단계 제목 양식 추가"}
          onClose={closeAutoTitleRegistration}
          wide
          className="auto-title-register-modal"
        >
          <div className="auto-title-register-form">

            {autoTitleRegistration.preview && (
              <div className="auto-title-register-preview">
                <img src={autoTitleRegistration.preview} alt="등록할 제목 양식 미리보기" />
              </div>
            )}
            <label>
              <span>목록에 표시할 이름</span>
              <input
                type="text"
                value={autoTitleRegistration.name}
                onChange={(event) => setAutoTitleRegistration((current) => current
                  ? { ...current, name: event.target.value, error: "" }
                  : current)}
              />
            </label>
            {autoTitleRegistration.role === "title" && (
              <label>
                <span>번호로 바꿀 글자</span>
                <input
                  type="text"
                  value={autoTitleRegistration.number_sample}
                  onChange={(event) => setAutoTitleRegistration((current) => current
                    ? { ...current, number_sample: event.target.value, error: "" }
                    : current)}
                />
              </label>
            )}
            <label>
              <span>제목으로 바꿀 글자</span>
              <input
                type="text"
                value={autoTitleRegistration.title_sample}
                onChange={(event) => setAutoTitleRegistration((current) => current
                  ? { ...current, title_sample: event.target.value, error: "" }
                  : current)}
              />
            </label>
            {autoTitleRegistration.error && (
              <p className="auto-title-register-error" role="alert">{autoTitleRegistration.error}</p>
            )}
            <div className="auto-title-register-actions">
              <button type="button" onClick={closeAutoTitleRegistration}>취소</button>
              <button
                type="button"
                className="primary-command"
                disabled={
                  isBusy
                  || !autoTitleRegistration.name.trim()
                  || !autoTitleRegistration.title_sample.trim()
                  || (autoTitleRegistration.role === "title" && !autoTitleRegistration.number_sample.trim())
                }
                onClick={() => void saveAutoTitleRegistration()}
              >
                이 제목 양식 저장
              </button>
            </div>
          </div>
        </Modal>
      )}

      {autoTitleManagerRole && (
        <Modal
          title={autoTitleManagerRole === "document_title" ? "문서제목 양식 관리" : "1단계 제목 양식 관리"}
          onClose={() => setAutoTitleManagerRole(null)}
          wide
          className="auto-title-manager-modal"
        >
          <div className="manager-list auto-title-manager-list">
            {autoTitleTemplates
              .filter((item) => item.role === autoTitleManagerRole && item.user_item)
              .map((item) => (
                <div className="manager-row auto-title-manager-row" key={item.key}>
                  <span className="auto-title-manager-preview">
                    {item.preview ? <img src={item.preview} alt="" /> : <FileText size={28} />}
                  </span>
                  <strong>{item.title}</strong>
                  <div>
                    <button type="button" onClick={() => renameAutoTitleTemplate(item)}>
                      <Pencil size={14} /> 이름
                    </button>
                    <button type="button" className="danger-command" onClick={() => void deleteAutoTitleTemplate(item)}>
                      <Trash2 size={14} /> 삭제
                    </button>
                  </div>
                </div>
              ))}
            {!autoTitleTemplates.some((item) => item.role === autoTitleManagerRole && item.user_item) && (
              <p className="empty-state">등록한 제목 양식이 없습니다.</p>
            )}
          </div>
        </Modal>
      )}
      {nameDialog && (
        <Modal title={nameDialog.title} onClose={() => setNameDialog(null)}>
          <form
            className="dialog-form"
            onSubmit={(event) => {
              event.preventDefault();
              const value = nameValue.trim();
              if (value) void nameDialog.onSubmit(value);
            }}
          >
            <label>이름<input autoFocus value={nameValue} onChange={(event) => setNameValue(event.target.value)} maxLength={40} /></label>
            <div className="dialog-actions">
              <button type="button" onClick={() => setNameDialog(null)}>취소</button>
              <button type="submit" className="primary-command" disabled={!nameValue.trim() || isBusy}>{nameDialog.submitLabel}</button>
            </div>
          </form>
        </Modal>
      )}

      {kedufineFormDraft && (
        <Modal title={kedufineFormDraft.id ? "기안문 양식 수정" : "내 기안문 양식 추가"} onClose={() => setKedufineFormDraft(null)}>
          <form className="dialog-form" onSubmit={(event) => { event.preventDefault(); void saveKedufineForm(); }}>
            <label>양식 이름<input autoFocus value={kedufineFormDraft.title} maxLength={40} onChange={(event) => setKedufineFormDraft({ ...kedufineFormDraft, title: event.target.value })} /></label>
            <div className="kedufine-category-select" role="group" aria-label="기안문 양식 분류">
              <button type="button" className={kedufineFormDraft.category === "internal" ? "is-active" : ""} onClick={() => setKedufineFormDraft({ ...kedufineFormDraft, category: "internal" })}>내부결재</button>
              <button type="button" className={kedufineFormDraft.category === "outgoing" ? "is-active" : ""} onClick={() => setKedufineFormDraft({ ...kedufineFormDraft, category: "outgoing" })}>발송용</button>
            </div>
            <label>본문<textarea value={kedufineFormDraft.body} maxLength={20000} rows={12} onChange={(event) => setKedufineFormDraft({ ...kedufineFormDraft, body: event.target.value })} /></label>
            <div className="dialog-actions">
              <button type="button" onClick={() => setKedufineFormDraft(null)}>취소</button>
              <button type="submit" className="primary-command" disabled={isBusy || !kedufineFormDraft.title.trim() || !kedufineFormDraft.body.trim()}>{kedufineFormDraft.id ? "저장" : "등록"}</button>
            </div>
          </form>
        </Modal>
      )}

      {kedufineFormManagerOpen && (
        <Modal title="사용자 기안문 양식 관리" onClose={() => setKedufineFormManagerOpen(false)} wide>
          {kedufineForms.some((item) => item.user_item) ? (
            <div className="manager-list">
              {kedufineForms.filter((item) => item.user_item).map((item) => (
                <div className="manager-row" key={item.key}>
                  <span className="manager-preview"><FileText size={24} /></span>
                  <strong>{item.title}</strong>
                  <div>
                    <button type="button" onClick={() => { setKedufineFormManagerOpen(false); setKedufineFormDraft({ id: item.id, title: item.title, category: item.category === "internal" ? "internal" : "outgoing", body: item.body }); }}><Pencil size={14} /> 수정</button>
                    <button type="button" className="danger-command" onClick={() => void deleteKedufineForm(item)}><Trash2 size={14} /> 삭제</button>
                  </div>
                </div>
              ))}
            </div>
          ) : <div className="empty-state">등록된 사용자 양식이 없습니다.</div>}
        </Modal>
      )}

      {managerKind && (
        <Modal title={`사용자 ${managerKind === "style" ? "서식" : managerKind === "form" ? "양식" : "편집용지"} 관리`} onClose={() => setManagerKind(null)} wide>
          {userItemsForManager.length ? (
            <div className="manager-list">
              {userItemsForManager.map((item) => (
                <div className={`manager-row ${managerKind === "form" ? "is-form-manager" : ""}`} key={item.id}>
                  <span className="manager-preview">{managerKind === "page" ? <PagePreview margins={item.margins ?? DEFAULT_MARGINS} orientation={item.orientation} /> : item.preview ? <img src={item.preview} alt="" /> : <FileText size={24} />}</span>
                  <strong>{item.title}{managerKind === "style" && item.available === false ? " (다시 등록 필요)" : ""}</strong>
                  <div>
                    <button type="button" onClick={() => askName("이름 수정", item.title, "저장", async (title) => {
                      const result = await execute("user_update_title", { kind: managerKind, item_id: item.id, title });
                      if (result?.ok) { setNameDialog(null); await loadCatalogs(); }
                    })}><Pencil size={14} /> 이름</button>

                    {managerKind === "page" && <button type="button" onClick={() => openPageEditor(item)}><Pencil size={14} /> 설정</button>}
                    <button type="button" className="danger-command" onClick={() => void deleteUserItem(managerKind, item)}><Trash2 size={14} /> 삭제</button>
                  </div>
                </div>
              ))}
            </div>
          ) : <div className="empty-state">등록된 사용자 항목이 없습니다.</div>}
        </Modal>
      )}

      {pictureSymbolManagerOpen && (
        <Modal title="내 심볼 관리" onClose={() => setPictureSymbolManagerOpen(false)} wide>
          {pictureGroups.find((group) => group.user_group)?.items.length ? (
            <div className="manager-list">
              {pictureGroups.find((group) => group.user_group)?.items.map((item) => (
                <div className="manager-row is-picture-symbol-manager" key={item.key}>
                  <span className="manager-preview">{item.preview ? <img src={item.preview} alt="" /> : <FileImage size={24} />}</span>
                  <strong>{item.title}</strong>
                  <div>
                    <button type="button" onClick={() => renamePictureSymbol(item)}><Pencil size={14} /> 이름</button>
                    <button type="button" className="danger-command" onClick={() => void deletePictureSymbol(item)}><Trash2 size={14} /> 삭제</button>
                  </div>
                </div>
              ))}
            </div>
          ) : <div className="empty-state">등록한 내 심볼이 없습니다.</div>}
        </Modal>
      )}
      {pageEditor && (
        <Modal title={pageEditor === "new" ? "내 편집용지 추가" : "사용자 편집용지 수정"} onClose={() => setPageEditor(null)} wide>
          <form className="page-editor" onSubmit={(event) => { event.preventDefault(); void savePageEditor(); }}>
            <label className="page-title-field">편집용지 이름<input autoFocus value={pageTitle} onChange={(event) => setPageTitle(event.target.value)} maxLength={40} /></label>
            <div className="page-option-row">
              <span>용지 방향</span>
              <div className="segmented page-options" role="group" aria-label="용지 방향">
                <button type="button" aria-pressed={pageOrientation === "portrait"} className={pageOrientation === "portrait" ? "is-active" : ""} disabled={isBusy} onClick={() => setPageOrientation("portrait")}>세로</button>
                <button type="button" aria-pressed={pageOrientation === "landscape"} className={pageOrientation === "landscape" ? "is-active" : ""} disabled={isBusy} onClick={() => setPageOrientation("landscape")}>가로</button>
              </div>
            </div>
            <div className="margin-layout">
              <div className="margin-control is-top">
                {(["top", "header"] as const).map((key) => <label key={key}>{key === "top" ? "위쪽" : "머리말"}<input type="number" min={0} max={100} step={0.1} value={pageMargins[key]} onChange={(event) => setPageMargins({ ...pageMargins, [key]: Number(event.target.value) })} /><span>mm</span></label>)}
              </div>
              <div className="margin-control is-left">
                {(["left", "gutter"] as const).map((key) => <label key={key}>{key === "left" ? "왼쪽" : "제본"}<input type="number" min={0} max={100} step={0.1} value={pageMargins[key]} onChange={(event) => setPageMargins({ ...pageMargins, [key]: Number(event.target.value) })} /><span>mm</span></label>)}
              </div>
              <div className="page-margin-live"><PagePreview margins={pageMargins} orientation={pageOrientation} /></div>
              <div className="margin-control is-right">
                <label>오른쪽<input type="number" min={0} max={100} step={0.1} value={pageMargins.right} onChange={(event) => setPageMargins({ ...pageMargins, right: Number(event.target.value) })} /><span>mm</span></label>
              </div>
              <div className="margin-control is-bottom">
                {(["footer", "bottom"] as const).map((key) => <label key={key}>{key === "footer" ? "꼬리말" : "아래쪽"}<input type="number" min={0} max={100} step={0.1} value={pageMargins[key]} onChange={(event) => setPageMargins({ ...pageMargins, [key]: Number(event.target.value) })} /><span>mm</span></label>)}
              </div>
            </div>
            <div className="dialog-actions">
              <button type="button" onClick={() => setPageEditor(null)}>취소</button>
              <button type="submit" className="primary-command" disabled={!pageTitle.trim() || isBusy}>{pageEditor === "new" ? "등록" : "저장"}</button>
            </div>
          </form>
        </Modal>
      )}

      {composeOpen && (
        <Modal title="글자 겹치기" onClose={() => { if (!isBusy) setComposeOpen(false); }}>
          <form className="dialog-form" onSubmit={(event) => { event.preventDefault(); void insertComposedCharacter(composeValue, composeShape, true); }}>
            <label>글자<input autoFocus value={composeValue} maxLength={9} onChange={(event) => { setComposeValue(event.target.value); setComposeError(""); }} disabled={isBusy} /></label>
            <div className="compose-shapes" role="group" aria-label="겹치기 모양">
              {([["circle", "원", "○"], ["square", "네모", "□"]] as const).map(([shape, label, symbol]) => (
                <button type="button" key={shape} aria-label={label} title={label} aria-pressed={composeShape === shape}
                  disabled={isBusy} onClick={() => setComposeShape(shape)}>{symbol}</button>
              ))}
            </div>
            <div className="compose-preview" aria-label="겹치기 미리보기">
              <span className={`composed-character is-${composeShape}`}><span>{composeValue}</span></span>
            </div>
            {composeError && <p className="compose-error" role="alert">{composeError}</p>}
            <div className="dialog-actions">
              <button type="button" disabled={isBusy} onClick={() => setComposeOpen(false)}>취소</button>
              <button type="submit" className="primary-command" disabled={!composeValue.trim() || isBusy}>삽입</button>
            </div>
          </form>
        </Modal>
      )}

      {symbolDeleteTarget && (
        <Modal title="내 문자표 삭제" className="character-delete-modal" onClose={() => { if (!busyRef.current) setSymbolDeleteTarget(null); }}>
          <p className="character-delete-message">‘{symbolDeleteTarget.title}’ 문자표를 삭제할까요?</p>
          {symbolDeleteError && <p className="character-delete-error" role="alert">{symbolDeleteError}</p>}
          <div className="dialog-actions">
            <button type="button" autoFocus disabled={isBusy} onClick={() => setSymbolDeleteTarget(null)}>취소</button>
            <button type="button" className="danger-command" disabled={isBusy} onClick={() => void deleteSymbolGroup()}><Trash2 size={14} /> 삭제</button>
          </div>
        </Modal>
      )}

      {symbolEditor && (
        <Modal title={symbolEditor === "new" ? "내 문자표 추가" : "내 문자표 수정"} onClose={() => setSymbolEditor(null)}>
          <form className="dialog-form" onSubmit={(event) => { event.preventDefault(); void saveSymbolEditor(); }}>
            <label>문자표 이름<input autoFocus value={symbolTitle} onChange={(event) => setSymbolTitle(event.target.value)} maxLength={40} /></label>
            <label>문자·기호<textarea rows={9} value={symbolValues} onChange={(event) => setSymbolValues(event.target.value)} placeholder="공백, 쉼표 또는 줄바꿈으로 구분" /></label>
            <div className="dialog-actions">
              <button type="button" onClick={() => setSymbolEditor(null)}>취소</button>
              <button type="submit" className="primary-command" disabled={!symbolTitle.trim() || !symbolValues.trim() || isBusy}>저장</button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
