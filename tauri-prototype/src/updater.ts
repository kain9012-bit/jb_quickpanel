import { invoke } from "@tauri-apps/api/core";

interface BoardUpdate {
  version: string;
  download: string;
  signature: string;
}

interface BoardUpdateCheck {
  configured: boolean;
  current: string;
  update: BoardUpdate | null;
  message: string;
}

export interface UpdatePreparation {
  configured: boolean;
  current: string;
  version: string;
  ready: boolean;
  message: string;
}

let pendingPath = "";
let pendingVersion = "";

export function displayVersion(version: string): string {
  const normalized = String(version || "")
    .trim()
    .replace(/^[vV]\.?/, "");
  return normalized ? `v.${normalized}` : "";
}

export function displayUpdateError(error: unknown): string {
  const message = String(error ?? "").trim();
  const conciseMessages = [
    "게시글을 열지 못했습니다",
    "게시글을 읽지 못했습니다",
    "연결을 준비하지 못했습니다",
  ];
  const concise = conciseMessages.find((item) => message.includes(item));
  return concise ? `${concise}.` : message;
}

export function preparedUpdateVersion(): string {
  return pendingVersion;
}

export async function prepareUpdate(
  onProgress?: (message: string) => void,
): Promise<UpdatePreparation> {
  const check = await invoke<BoardUpdateCheck>("check_board_update");
  if (!check.configured || !check.update) {
    return {
      configured: check.configured,
      current: check.current,
      version: "",
      ready: false,
      message: check.message,
    };
  }

  if (pendingPath && pendingVersion === check.update.version) {
    return {
      configured: true,
      current: check.current,
      version: pendingVersion,
      ready: true,
      message: `${displayVersion(pendingVersion)} 업데이트가 준비되어 있습니다.`,
    };
  }

  onProgress?.(`${displayVersion(check.update.version)} 설치파일을 받는 중입니다.`);
  pendingPath = await invoke<string>("download_board_update", { update: check.update });
  pendingVersion = check.update.version;
  return {
    configured: true,
    current: check.current,
    version: pendingVersion,
    ready: true,
    message: `${displayVersion(pendingVersion)} 업데이트 준비가 완료되었습니다.`,
  };
}

export async function applyPreparedUpdate(): Promise<void> {
  if (!pendingPath) {
    throw new Error("받아 둔 업데이트 설치파일이 없습니다.");
  }
  await invoke("apply_board_update", { path: pendingPath });
}
