import { invoke } from "@tauri-apps/api/core";
import type { CardFavorites } from "./favorites";

export type BackendResponse<T = Record<string, unknown>> = {
  id: number;
  ok: boolean;
  message: string;
  data: T;
};

export type CellSelection = {
  active: boolean;
  dragging: boolean;
  label: string;
  start?: string;
  end?: string;
  rows?: number;
  columns?: number;
};

export type ContentItem = {
  key: string;
  id: string;
  title: string;
  source: "builtin" | "user";
  user_item: boolean;
  preview: string;
  available?: boolean;
  margins?: PageMargins;
  orientation?: "portrait" | "landscape";
};

export type AutoTitleTemplate = ContentItem & {
  role: "document_title" | "title";
};

export type AutoTitleAnalysis = {
  role: "document_title" | "title";
  pending_id: string;
  preview: string;
  title_sample: string;
  number_sample: string;
  segments: string[];
  combined: boolean;
};

export type PageMargins = {
  top: number;
  header: number;
  left: number;
  gutter: number;
  right: number;
  footer: number;
  bottom: number;
};

export type TableToolItem = {
  action_id: string;
  title: string;
  preview: string;
};

export type CharacterGroup = {
  id: string;
  title: string;
  chars: string[];
  user_item: boolean;
  presentation?: "square";
};

export type PictureSymbolItem = {
  id?: string;
  key: string;
  favorite_key?: string;
  title: string;
  preview: string;
  preview_on_dark: boolean;
  user_item?: boolean;
};

export type PictureSymbolGroup = {
  title: string;
  items: PictureSymbolItem[];
  user_group?: boolean;
};

export type AutoFormatRoleStyle = {
  font: string;
  size: number;
  bold: boolean;
  marker?: string;
  custom_marker?: string;
};

export type AutoFormatSettings = {
  document_title_template: string;
  title_template: string;
  roles: {
    document_title: AutoFormatRoleStyle;
    title: AutoFormatRoleStyle;
    subtitle: AutoFormatRoleStyle;
    subsubtitle: AutoFormatRoleStyle;
    body: AutoFormatRoleStyle;
    table: AutoFormatRoleStyle;
    reference: AutoFormatRoleStyle;
  };
};

export type AutoFormatProfile = {
  id: string;
  name: string;
  settings: AutoFormatSettings;
};

export type AppSettings = {
  always_on_top: boolean;
  target_mode: "hwp" | "kedufine";
  start_mode: "hwp" | "kedufine";
  start_position: "top_right" | "center" | "last";
  remember_window_position: boolean;
  last_geometry: string;
  close_to_tray: boolean;
  start_minimized: boolean;
  tutorial_completed: boolean;
  check_updates_on_startup: boolean;
  toggle_hotkey: string;
  global_hotkeys_enabled: boolean;
  global_hotkeys: Record<string, string>;
  card_favorites: CardFavorites;
  character_group_order: string[];
  tab_order: string[];
  auto_format: AutoFormatSettings;
  active_auto_format_profile: string;
  auto_format_profiles: AutoFormatProfile[];
};

export type IntegrationStatus = {
  startup: boolean;
  start_menu: boolean;
  settings_dir: string;
};

export async function requestBackend<T = Record<string, unknown>>(
  command: string,
  args: Record<string, unknown> = {},
): Promise<BackendResponse<T>> {
  return invoke<BackendResponse<T>>("hwp_request", { command, args });
}

export async function cancelAutoFormat(): Promise<{ ok: boolean; message: string }> {
  return invoke<{ ok: boolean; message: string }>("cancel_auto_format");
}

export async function setWindowPreferences(
  alwaysOnTop: boolean,
  closeToTray: boolean,
): Promise<void> {
  await invoke("set_window_preferences", {
    alwaysOnTop,
    closeToTray,
  });
}

export async function setWindowInputMode(enabled: boolean): Promise<void> {
  await invoke("set_window_input_mode", { enabled });
}

export async function focusExternalWindow(hwnd: number): Promise<void> {
  await invoke("focus_external_window", { hwnd });
}

export type WindowLayoutState = { active: boolean; message?: string };

export async function readWindowLayoutState(): Promise<WindowLayoutState> {
  return invoke<WindowLayoutState>("window_layout_state");
}

export async function arrangeHwpWindows(hwnd: number, pid: number): Promise<WindowLayoutState> {
  return invoke<WindowLayoutState>("arrange_hwp_windows", { hwpHwnd: hwnd, hwpPid: pid });
}


export async function applyWindowPosition(
  mode: AppSettings["start_position"],
  lastGeometry: string,
): Promise<{ ok: boolean; last_geometry: string }> {
  return invoke<{ ok: boolean; last_geometry: string }>("apply_window_position", {
    mode,
    lastGeometry,
  });
}
