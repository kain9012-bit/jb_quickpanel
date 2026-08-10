import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { getCurrentWindow } from "@tauri-apps/api/window";
import { register, unregisterAll } from "@tauri-apps/plugin-global-shortcut";
import {
  AlignHorizontalSpaceAround,
  Brush,
  Check,
  ChevronDown,
  ChevronUp,
  CircleHelp,
  Eraser,
  FileImage,
  FilePlus2,
  FileText,
  ImagePlus,
  Link,
  LoaderCircle,
  Minus,
  PaintBucket,
  Pencil,
  Plus,
  RefreshCw,
  RotateCcw,
  Settings,
  Square,
  Table2,
  Trash2,
  Type,
  Unlink,
  WandSparkles,
  X,
} from "lucide-react";
import {
  applyWindowPosition,
  cancelAutoFormat,
  requestBackend,

  setWindowInputMode,
  setWindowPreferences,
} from "./backend";
import type {
  AppSettings,
  BackendResponse,
  CellSelection,
  CharacterGroup,
  ContentItem,
  IntegrationStatus,
  PageMargins,
  PictureSymbolGroup,
  TableToolItem,
} from "./backend";

type TabId = "style" | "edit" | "chars" | "symbol" | "forms" | "page";
type EditTabId = "table" | "cell" | "text";
type ContentKind = "style" | "form" | "page";

const VERSION = "v4.0";

const DEFAULT_MARGINS: PageMargins = {
  top: 10,
  header: 10,
  left: 20,
  gutter: 0,
  right: 20,
  footer: 10,
  bottom: 15,
};
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
  global_hotkeys_enabled: true,
  global_hotkeys: {},
  tab_order: ["style", "edit", "chars", "symbol", "forms", "page"],
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
  special?: "toggle_window" | "auto_format" | "insert_images";
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

function ContentGrid({
  items,
  kind,
  busy,
  onRun,
}: {
  items: ContentItem[];
  kind: ContentKind;
  busy: boolean;
  onRun: (item: ContentItem) => void;
}) {
  return (
    <div className={kind === "form" ? "content-card-grid form-grid" : "content-card-grid"}>
      {items.map((item) => (
        <button
          type="button"
          className="content-card"
          key={item.key}
          disabled={busy}
          onClick={() => onRun(item)}
        >
          <span className="content-preview">
            {item.preview ? (
              <img src={item.preview} alt="" draggable={false} />
            ) : kind === "page" && item.margins ? (
              <PagePreview margins={item.margins} />
            ) : (
              <FileText size={32} />
            )}
          </span>
          <span className="content-title">{item.title}</span>
          {item.user_item && <span className="user-badge">내 {TAB_LABELS[kind === "form" ? "forms" : kind]}</span>}
        </button>
      ))}
    </div>
  );
}

function PagePreview({ margins }: { margins: PageMargins }) {
  return (
    <span className="page-preview" aria-hidden="true">
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
  const [activeTab, setActiveTab] = useState<TabId>("style");
  const [editTab, setEditTab] = useState<EditTabId>("table");
  const [styles, setStyles] = useState<ContentItem[]>([]);
  const [forms, setForms] = useState<ContentItem[]>([]);
  const [pages, setPages] = useState<ContentItem[]>([]);
  const [tableTools, setTableTools] = useState<TableToolItem[]>([]);
  const [characterGroups, setCharacterGroups] = useState<CharacterGroup[]>([]);
  const [pictureGroups, setPictureGroups] = useState<PictureSymbolGroup[]>([]);
  const [pictureGroupIndex, setPictureGroupIndex] = useState(0);
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
  const [updateStatus, setUpdateStatus] = useState(`현재 버전 ${VERSION} · 업데이트 정보 미설정`);
  const [updateDownload, setUpdateDownload] = useState("");
  const [selection, setSelection] = useState<CellSelection>({
    active: false,
    dragging: false,
    label: "선택된 셀 범위 없음",
  });
  const polling = useRef(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [autoFormatHelpOpen, setAutoFormatHelpOpen] = useState(false);
  const [hotkeyOpen, setHotkeyOpen] = useState(false);
  const [hotkeySearch, setHotkeySearch] = useState("");
  const [capturingHotkey, setCapturingHotkey] = useState("");
  const [tutorialOpen, setTutorialOpen] = useState(false);
  const [sourceKind, setSourceKind] = useState<Exclude<ContentKind, "page"> | null>(null);
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
  const [symbolEditor, setSymbolEditor] = useState<CharacterGroup | "new" | null>(null);
  const [symbolTitle, setSymbolTitle] = useState("");
  const [symbolValues, setSymbolValues] = useState("");
  const [findText, setFindText] = useState("");
  const [replaceText, setReplaceText] = useState("");
  const [addText, setAddText] = useState("");
  const [imageMode, setImageMode] = useState("fit_inside");

  const modalOpen = settingsOpen || hotkeyOpen || tutorialOpen || autoFormatHelpOpen || Boolean(
    sourceKind || managerKind || nameDialog || pageEditor || symbolEditor,
  );

  useEffect(() => {
    void setWindowInputMode(modalOpen).catch(() => undefined);
  }, [modalOpen]);



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

  const loadCatalogs = useCallback(async () => {
    const results = await Promise.all([
      requestBackend<{ items: ContentItem[] }>("style_catalog"),
      requestBackend<{ items: ContentItem[] }>("form_catalog"),
      requestBackend<{ items: ContentItem[] }>("page_catalog"),
      requestBackend<{ items: TableToolItem[] }>("table_catalog"),
      requestBackend<{ groups: CharacterGroup[] }>("character_catalog"),
      requestBackend<{ groups: PictureSymbolGroup[] }>("picture_symbol_catalog"),
    ]);
    setStyles(results[0].data?.items ?? []);
    setForms(results[1].data?.items ?? []);
    setPages(results[2].data?.items ?? []);
    setTableTools(results[3].data?.items ?? []);
    setCharacterGroups(results[4].data?.groups ?? []);
    setPictureGroups(results[5].data?.groups ?? []);
  }, []);

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const settingsResponse = await requestBackend<{
          settings: AppSettings;
          integration: IntegrationStatus;
        }>("settings_get");
        if (!alive) return;
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
          const updateResponse = await requestBackend<{ update: Record<string, unknown> }>("update_check");
          if (alive) {
            setUpdateStatus(updateResponse.message);
            setUpdateDownload(String(updateResponse.data?.update?.download ?? ""));
          }
        }
        if (!loaded.tutorial_completed) setTutorialOpen(true);
      } catch (error) {
        if (alive) setStatus(`초기화 오류: ${String(error)}`);
      }
    })();
    return () => { alive = false; };
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
      if (payload.x <= -10000 || payload.y <= -10000) return;
      window.clearTimeout(saveTimer);
      const geometry = `${payload.x},${payload.y}`;
      setSettings((current) => ({ ...current, last_geometry: geometry }));
      saveTimer = window.setTimeout(() => {
        if (!disposed) {
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
    if (!response?.ok || !response.data?.settings) return;
    const next = { ...DEFAULT_SETTINGS, ...response.data.settings };
    setSettings(next);
    if (response.data.integration) setIntegration(response.data.integration);

    await setWindowPreferences(next.always_on_top, next.close_to_tray);
    if ("start_position" in changes) {
      await applyWindowPosition(next.start_position, next.last_geometry);
    }
  }, [execute]);

  const checkUpdate = useCallback(async () => {
    const response = await execute<{ update: Record<string, unknown> }>("update_check");
    if (!response) return;
    setUpdateStatus(response.message);
    setUpdateDownload(String(response.data?.update?.download ?? ""));
  }, [execute]);

  const resetSettings = useCallback(async () => {
    if (!window.confirm("화면·시작·단축키 설정을 기본값으로 되돌릴까요?")) return;
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
    setUpdateStatus(`현재 버전 ${VERSION} · 업데이트 정보 미설정`);
    setUpdateDownload("");
    await loadCatalogs();
  }, [execute, integration, loadCatalogs]);

  const changeTargetMode = useCallback(async (mode: "hwp" | "kedufine") => {
    const response = await execute<{ connected: boolean; target_mode: "hwp" | "kedufine" }>(
      "set_target_mode",
      { mode },
    );
    setSettings((current) => ({ ...current, target_mode: mode }));
    setConnected(Boolean(response?.ok && response.data?.connected));
    if (mode === "kedufine" && ["symbol", "forms", "page"].includes(activeTab)) setActiveTab("style");
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
      ? new Set<TabId>(["style", "edit", "chars"])
      : new Set<TabId>(["style", "edit", "chars", "symbol", "forms", "page"]);
    const ordered = (settings.tab_order ?? [])
      .filter((id): id is TabId => id in TAB_LABELS && allowed.has(id as TabId));
    for (const id of Object.keys(TAB_LABELS) as TabId[]) {
      if (allowed.has(id) && !ordered.includes(id)) ordered.push(id);
    }
    return ordered;
  }, [settings.tab_order, settings.target_mode]);

  const askName = (
    title: string,
    initial: string,
    submitLabel: string,
    onSubmit: (value: string) => Promise<void>,
  ) => {
    setNameValue(initial);
    setNameDialog({ title, initial, submitLabel, onSubmit });
  };

  const addUserContentFromFile = async (kind: "style" | "form") => {
    setSourceKind(null);
    const picked = await execute<{ paths: string[]; suggested_title: string }>(
      "pick_files",
      { kind: "hwp" },
    );
    const path = picked?.data?.paths?.[0];
    if (!picked?.ok || !path) return;
    askName(
      kind === "style" ? "내 서식 이름" : "내 양식 이름",
      picked.data.suggested_title || "",
      "등록",
      async (title) => {
        const result = await execute("user_add_file", {
          kind,
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

  const addUserContentFromBlock = (kind: "style" | "form") => {
    setSourceKind(null);
    askName(
      kind === "style" ? "현재 블록을 내 서식으로 추가" : "현재 블록을 내 양식으로 추가",
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
  };

  const savePageEditor = async () => {
    const result = await execute("user_save_page", {
      item_id: pageEditor === "new" || pageEditor === null ? "" : pageEditor.id,
      title: pageTitle,
      margins: pageMargins,
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
    const result = await execute("user_save_symbol_group", {
      item_id: symbolEditor === "new" || symbolEditor === null ? "" : symbolEditor.id,
      title: symbolTitle,
      chars: symbolValues,
    });
    if (result?.ok) {
      setSymbolEditor(null);
      await loadCatalogs();
    }
  };

  const deleteUserItem = async (kind: ContentKind, item: ContentItem) => {
    if (!window.confirm(`'${item.title}' 항목을 삭제할까요?`)) return;
    const result = await execute("user_delete", { kind, item_id: item.id });
    if (result?.ok) await loadCatalogs();
  };

  const changePreview = async (
    kind: "style" | "form",
    item: ContentItem,
    mode: "auto" | "image" | "remove",
  ) => {
    let sourcePath = "";
    if (mode === "image") {
      const picked = await execute<{ paths: string[] }>("pick_files", { kind: "preview" });
      sourcePath = picked?.data?.paths?.[0] ?? "";
      if (!sourcePath) return;
    }
    const result = await execute("user_update_preview", {
      kind,
      item_id: item.id,
      mode,
      source_path: sourcePath,
    });
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
    await saveSettings({ tutorial_completed: true });
  };

  const hotkeyActions = useMemo<HotkeyAction[]>(() => {
    const actions: HotkeyAction[] = [
      { id: "app.toggle_window", category: "프로그램", label: "서식도우미 열기/숨기기", special: "toggle_window" },
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
        if (!value || seen.has(value)) continue;
        seen.add(value);
        const encoded = Array.from(value).map((char) => char.codePointAt(0)?.toString(16)).join("-");
        actions.push({
          id: `insert-text:${encoded}`,
          category: "문자표",
          label: `${value}  (${group.title})`,
          command: "insert_character",
          args: { value },
        });
      }
    }
    return actions;
  }, [characterGroups, imageMode, tableTools]);

  const triggerHotkey = useCallback(async (action: HotkeyAction) => {
    if (action.special === "toggle_window") {
      const window = getCurrentWindow();
      if (await window.isVisible()) await window.hide();
      else {
        await window.show();
        await window.unminimize();
      }
      return;
    }
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
    let disposed = false;
    void (async () => {
      try {
        await unregisterAll();
        if (!settings.global_hotkeys_enabled) return;
        const byId = new Map(hotkeyActions.map((action) => [action.id, action]));
        for (const [actionId, shortcut] of Object.entries(settings.global_hotkeys ?? {})) {
          const action = byId.get(actionId);
          if (!action || !shortcut || disposed) continue;
          await register(normalizeShortcutForTauri(shortcut), (event) => {
            if (event.state === "Pressed") void triggerHotkey(action);
          });
        }
      } catch (error) {
        if (!disposed) setStatus(`전역 단축키 등록 실패: ${String(error)}`);
      }
    })();
    return () => {
      disposed = true;
      void unregisterAll().catch(() => undefined);
    };
  }, [hotkeyActions, settings.global_hotkeys, settings.global_hotkeys_enabled, triggerHotkey]);

  const filteredHotkeyActions = useMemo(() => {
    const query = hotkeySearch.trim().toLocaleLowerCase();
    if (!query) return hotkeyActions;
    return hotkeyActions.filter((action) =>
      `${action.category} ${action.label}`.toLocaleLowerCase().includes(query),
    );
  }, [hotkeyActions, hotkeySearch]);

  const saveHotkey = async (actionId: string, shortcut: string) => {
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

  return (
    <div className="app-shell">
      <header className="toolbar">
        <div className="target-switch" aria-label="적용 대상">
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
          <button type="button" className="settings-button" onClick={() => setSettingsOpen(true)}>
            <Settings size={15} />
            <span>설정</span>
          </button>
        </div>
      </header>

      <nav className="tabs" aria-label="기능 탭" style={{ gridTemplateColumns: `repeat(${visibleTabs.length}, minmax(0, 1fr))` }}>
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

      <main className="content">
        {activeTab === "style" && (
          <section className="section">
            <div className="auto-format-toolbar">
              {settings.target_mode === "hwp" && (
                <>
                  <button
                    type="button"
                    className="auto-format-primary"
                    disabled={isBusy}
                    onClick={() => void startAutoFormat()}
                  >
                    <WandSparkles size={18} />
                    <span>서식 자동 지정하기</span>
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
                </>
              )}
              {settings.target_mode === "hwp" && (
                <button
                  type="button"
                  className="auto-format-secondary"
                  onClick={() => setAutoFormatHelpOpen(true)}
                >
                  <CircleHelp size={17} />
                  <span>사용방법</span>
                </button>
              )}
            </div>
            <div className="section-heading-row">
              <h2>서식</h2>
              <button type="button" className="section-refresh" onClick={() => void loadCatalogs()} aria-label="새로고침">
                <RefreshCw size={15} />
              </button>
            </div>
            <ContentGrid
              items={styles}
              kind="style"
              busy={isBusy}
              onRun={(item) => void execute("insert_style", { style_key: item.key })}
            />
            {settings.target_mode === "hwp" && (
              <div className="user-action-bar">
                <button type="button" className="primary-command" onClick={() => setSourceKind("style")}>
                  <Plus size={16} /> 내 서식 추가
                </button>
                <button type="button" onClick={() => setManagerKind("style")}>사용자 서식 관리</button>
              </div>
            )}
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
              <section className="section">
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
                        {tool.preview ? <img src={tool.preview} alt="" /> : <Table2 size={30} />}
                      </span>
                      <span>{tool.title}</span>
                    </button>
                  ))}
                </div>
                {settings.target_mode === "hwp" && (
                  <div className="picture-tool">
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
              <section className="section cell-tools">
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
                  <label>찾을 내용<input value={findText} onChange={(event) => setFindText(event.target.value)} /></label>
                  <label>바꿀 내용<input value={replaceText} onChange={(event) => setReplaceText(event.target.value)} /></label>
                  <button type="button" className="secondary-command full-width" disabled={!selection.active || isBusy || !findText} onClick={() => void execute("cell_text_action", { action: "find_replace", value: findText, replacement: replaceText })}>
                    찾아바꾸기 실행
                  </button>
                </div>
                <div className="tool-band">
                  <h3>셀마다 문자 붙이기</h3>
                  <label>추가할 문자<input value={addText} onChange={(event) => setAddText(event.target.value)} /></label>
                  <div className="split-commands">
                    <button type="button" disabled={!selection.active || isBusy || !addText} onClick={() => void execute("cell_text_action", { action: "prefix", value: addText })}>내용 앞에 추가</button>
                    <button type="button" disabled={!selection.active || isBusy || !addText} onClick={() => void execute("cell_text_action", { action: "suffix", value: addText })}>내용 뒤에 추가</button>
                  </div>
                </div>
              </section>
            )}

            {editTab === "text" && (
              <section className="section text-tools">
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
          <section className="section">
            <div className="user-action-bar is-top">
              <button type="button" className="primary-command" onClick={() => openSymbolEditor("new")}><Plus size={16} /> 내 문자표 추가</button>
              <button type="button" onClick={() => setManagerKind(null)} className="hidden-command">관리</button>
            </div>
            {characterGroups.map((group) => (
              <div className="character-group" key={group.id}>
                <div className="group-heading">
                  <h2>{group.user_item ? `내 문자표 · ${group.title}` : group.title}</h2>
                  {group.user_item && (
                    <span className="inline-actions">
                      <button type="button" onClick={() => openSymbolEditor(group)} aria-label="수정"><Pencil size={14} /></button>
                      <button
                        type="button"
                        onClick={() => void (async () => {
                          if (!window.confirm(`'${group.title}' 문자표를 삭제할까요?`)) return;
                          const result = await execute("user_delete_symbol_group", { item_id: group.id });
                          if (result?.ok) await loadCatalogs();
                        })()}
                        aria-label="삭제"
                      >
                        <Trash2 size={14} />
                      </button>
                    </span>
                  )}
                </div>
                <div className="character-grid">
                  {group.chars.map((value, index) => (
                    <button type="button" key={`${value}-${index}`} disabled={isBusy} onClick={() => void execute("insert_character", { value })}>{value}</button>
                  ))}
                </div>
              </div>
            ))}
          </section>
        )}

        {activeTab === "symbol" && settings.target_mode === "hwp" && (
          <section className="section">
            <nav className="group-tabs">
              {pictureGroups.map((group, index) => (
                <button type="button" key={group.title} className={pictureGroupIndex === index ? "is-active" : ""} onClick={() => setPictureGroupIndex(index)}>{group.title}</button>
              ))}
            </nav>
            <div className="symbol-grid">
              {(pictureGroups[pictureGroupIndex]?.items ?? []).map((item) => (
                <button type="button" className="symbol-card" key={item.key} disabled={isBusy} onClick={() => void execute("insert_picture_symbol", { item_key: item.key })}>
                  <span className={`symbol-preview${item.preview_on_dark ? " symbol-preview-dark" : ""}`}>
                    {item.preview ? <img src={item.preview} alt="" /> : <FileImage size={30} />}
                  </span>
                  <strong>{item.title}</strong>
                </button>
              ))}
            </div>
          </section>
        )}

        {activeTab === "forms" && settings.target_mode === "hwp" && (
          <section className="section">
            <ContentGrid items={forms} kind="form" busy={isBusy} onRun={(item) => void execute("insert_form", { item_key: item.key })} />
            <div className="user-action-bar">
              <button type="button" className="primary-command" onClick={() => setSourceKind("form")}><Plus size={16} /> 내 양식 추가</button>
              <button type="button" onClick={() => setManagerKind("form")}>사용자 양식 관리</button>
            </div>
          </section>
        )}

        {activeTab === "page" && settings.target_mode === "hwp" && (
          <section className="section">
            <ContentGrid items={pages} kind="page" busy={isBusy} onRun={(item) => void execute("apply_page", { item_key: item.key })} />
            <div className="user-action-bar">
              <button type="button" className="primary-command" onClick={() => openPageEditor("new")}><Plus size={16} /> 내 편집용지 추가</button>
              <button type="button" onClick={() => setManagerKind("page")}>사용자 편집용지 관리</button>
            </div>
          </section>
        )}
      </main>

      <footer className={`status-bar ${status.includes("오류") || status.includes("실패") ? "is-error" : ""}`}>
        {isBusy ? <LoaderCircle size={15} className="spin" /> : <span className="status-dot" />}
        <span>{status}</span>
      </footer>

      {settingsOpen && (
        <Modal title="설정" onClose={() => setSettingsOpen(false)} wide className="settings-modal">
          <div className="settings-sections">
            <section>
              <h3>화면</h3>
              <label className="toggle-row">
                <span><strong>항상 위로 표시</strong><small>한글 편집 중에도 서식도우미를 앞에 표시합니다.</small></span>
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
                <span><strong>시작 메뉴 등록</strong><small>Windows 검색에서 현재 버전을 찾을 수 있게 합니다.</small></span>
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
              <h3>전역 단축키</h3>
              <label className="toggle-row">
                <span><strong>전역 단축키 사용</strong><small>서식도우미가 트레이에 있어도 지정한 기능을 실행합니다.</small></span>
                <input type="checkbox" checked={settings.global_hotkeys_enabled} onChange={(event) => void saveSettings({ global_hotkeys_enabled: event.target.checked })} />
              </label>
              <button type="button" className="secondary-command full-width" onClick={() => setHotkeyOpen(true)}>단축키 설정</button>
            </section>            <section>
              <h3>업데이트</h3>
              <label className="toggle-row">
                <span><strong>시작할 때 최신 버전 확인</strong><small>업데이트 정보가 등록되면 새 버전을 안내합니다.</small></span>
                <input
                  type="checkbox"
                  checked={settings.check_updates_on_startup}
                  onChange={(event) => void saveSettings({ check_updates_on_startup: event.target.checked })}
                />
              </label>
              <div className="update-row">
                <span>{updateStatus}</span>
                <div className="update-actions">
                  <button type="button" onClick={() => void checkUpdate()} disabled={isBusy}>지금 확인</button>
                  {updateDownload && (
                    <button type="button" onClick={() => void execute("open_update_url", { url: updateDownload })}>다운로드 안내</button>
                  )}
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
            <section>
              <h3>도움말과 관리</h3>
              <div className="settings-command-grid">
                <button type="button" onClick={() => setTutorialOpen(true)}>튜토리얼 다시 보기</button>
                <button type="button" onClick={() => void execute("open_support", { kind: "readme" })}>README</button>
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

      {autoFormatHelpOpen && (
        <Modal title="서식 자동 지정하기 사용방법" onClose={() => setAutoFormatHelpOpen(false)} wide className="auto-format-help-modal">
          <div className="auto-format-help">
            <p>생성형 AI로 작성한 보고서·계획서 초안을 한글에 붙여 넣은 뒤, 원하는 범위를 선택하면 문서 구조에 맞춰 서식을 자동으로 적용합니다.</p>
            <ol>
              <li><strong>초안 작성</strong><span>GPT, Gemini, Claude 등 생성형 AI에서 보고서나 계획서 초안을 작성합니다.</span></li>
              <li><strong>한글에 붙여넣기</strong><span>완성된 초안 텍스트를 복사해 한글 문서에 붙여 넣습니다.</span></li>
              <li><strong>범위 선택</strong><span>서식을 적용할 텍스트 전체를 한글에서 블록 지정합니다.</span></li>
              <li><strong>자동 적용</strong><span>서식도우미의 '서식 자동 지정하기' 버튼을 누릅니다.</span></li>
            </ol>
            <div className="help-note">문서 제목은 선택 범위의 처음 부분에서 찾고, 제목·소제목·본문·참고·표 구조를 분석해 자동으로 정리합니다.</div>
            <button type="button" className="primary-command full-width" onClick={() => setAutoFormatHelpOpen(false)}>확인</button>
          </div>
        </Modal>
      )}

      {hotkeyOpen && (
        <Modal title="전역 단축키 설정" onClose={() => { setHotkeyOpen(false); setCapturingHotkey(""); }} wide>
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

      {tutorialOpen && (
        <Modal title="처음 사용 안내" onClose={() => void completeTutorial()} wide>
          <div className="tutorial">
            <section><strong>1. 적용 대상을 선택하세요.</strong><p>일반 한글과 K-에듀파인 기안창 중 지금 작업할 창을 선택합니다.</p></section>
            <section><strong>2. 한글에서 먼저 범위를 선택하세요.</strong><p>문자 서식은 텍스트 블록, 셀 정리는 표의 셀 범위를 드래그한 뒤 실행합니다.</p></section>
            <section><strong>3. 필요한 기능을 한 번 누르세요.</strong><p>서식·문자·양식은 현재 커서 위치에 들어가고, 편집도구는 선택한 범위에 적용됩니다.</p></section>
            <section><strong>4. 내 항목을 등록할 수 있습니다.</strong><p>서식, 양식, 편집용지와 문자표는 각 탭에서 직접 추가하고 관리합니다.</p></section>
            <button type="button" className="primary-command full-width" onClick={() => void completeTutorial()}>시작하기</button>
          </div>
        </Modal>
      )}

      {sourceKind && (
        <Modal title={sourceKind === "style" ? "내 서식 추가" : "내 양식 추가"} onClose={() => setSourceKind(null)}>
          <div className="source-choice">
            <button type="button" className={sourceKind === "style" ? "is-recommended" : ""} onClick={() => addUserContentFromBlock(sourceKind)}>
              <FilePlus2 size={25} /><strong>현재 블록에서 추가</strong><span>한글에서 선택한 블록을 그대로 등록합니다.</span>
            </button>
            <button type="button" className={sourceKind === "form" ? "is-recommended" : ""} onClick={() => void addUserContentFromFile(sourceKind)}>
              <FileText size={25} /><strong>한글 파일에서 추가</strong><span>HWP 또는 HWPX 파일을 선택합니다.</span>
            </button>
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

      {managerKind && (
        <Modal title={`사용자 ${managerKind === "style" ? "서식" : managerKind === "form" ? "양식" : "편집용지"} 관리`} onClose={() => setManagerKind(null)} wide>
          {userItemsForManager.length ? (
            <div className="manager-list">
              {userItemsForManager.map((item) => (
                <div className="manager-row" key={item.id}>
                  <span className="manager-preview">{item.preview ? <img src={item.preview} alt="" /> : <FileText size={24} />}</span>
                  <strong>{item.title}</strong>
                  <div>
                    <button type="button" onClick={() => askName("이름 수정", item.title, "저장", async (title) => {
                      const result = await execute("user_update_title", { kind: managerKind, item_id: item.id, title });
                      if (result?.ok) { setNameDialog(null); await loadCatalogs(); }
                    })}><Pencil size={14} /> 이름</button>
                    {managerKind !== "page" && (
                      <>
                        <button type="button" onClick={() => void changePreview(managerKind, item, "auto")}><RefreshCw size={14} /> 자동 미리보기</button>
                        <button type="button" onClick={() => void changePreview(managerKind, item, "image")}><FileImage size={14} /> 이미지 선택</button>
                      </>
                    )}
                    {managerKind === "page" && <button type="button" onClick={() => openPageEditor(item)}><Pencil size={14} /> 여백</button>}
                    <button type="button" className="danger-command" onClick={() => void deleteUserItem(managerKind, item)}><Trash2 size={14} /> 삭제</button>
                  </div>
                </div>
              ))}
            </div>
          ) : <div className="empty-state">등록된 사용자 항목이 없습니다.</div>}
        </Modal>
      )}

      {pageEditor && (
        <Modal title={pageEditor === "new" ? "내 편집용지 추가" : "사용자 편집용지 수정"} onClose={() => setPageEditor(null)} wide>
          <form className="page-editor" onSubmit={(event) => { event.preventDefault(); void savePageEditor(); }}>
            <label className="page-title-field">편집용지 이름<input autoFocus value={pageTitle} onChange={(event) => setPageTitle(event.target.value)} maxLength={40} /></label>
            <div className="margin-layout">
              <div className="margin-control is-top">
                {(["top", "header"] as const).map((key) => <label key={key}>{key === "top" ? "위쪽" : "머리말"}<input type="number" min={0} max={100} step={0.1} value={pageMargins[key]} onChange={(event) => setPageMargins({ ...pageMargins, [key]: Number(event.target.value) })} /><span>mm</span></label>)}
              </div>
              <div className="margin-control is-left">
                {(["left", "gutter"] as const).map((key) => <label key={key}>{key === "left" ? "왼쪽" : "제본"}<input type="number" min={0} max={100} step={0.1} value={pageMargins[key]} onChange={(event) => setPageMargins({ ...pageMargins, [key]: Number(event.target.value) })} /><span>mm</span></label>)}
              </div>
              <div className="page-margin-live"><PagePreview margins={pageMargins} /></div>
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
