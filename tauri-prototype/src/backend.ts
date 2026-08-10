import { invoke } from "@tauri-apps/api/core";

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
  margins?: PageMargins;
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
};

export type PictureSymbolGroup = {
  title: string;
  items: Array<{ key: string; title: string; preview: string; preview_on_dark: boolean }>;
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
  tab_order: string[];
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

export async function applyWindowPosition(
  mode: AppSettings["start_position"],
  lastGeometry: string,
): Promise<{ ok: boolean; last_geometry: string }> {
  return invoke<{ ok: boolean; last_geometry: string }>("apply_window_position", {
    mode,
    lastGeometry,
  });
}
