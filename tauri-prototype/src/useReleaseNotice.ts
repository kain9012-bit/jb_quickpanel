import { useEffect, useState } from "react";

import { compareVersion, notesBetween, type ReleaseNote } from "./releaseNotes";

const SEEN_VERSION_KEY = "jbedu-form:seen-version";

function normalizedVersion(version: string) {
  return version.trim().replace(/^[vV]\.?(?=\d)/, "");
}

function readSeenVersion() {
  try {
    return localStorage.getItem(SEEN_VERSION_KEY);
  } catch {
    return null;
  }
}

function writeSeenVersion(version: string) {
  try {
    localStorage.setItem(SEEN_VERSION_KEY, version);
  } catch {
    // 저장이 막힌 환경에서도 업데이트 안내 외의 기능은 그대로 사용한다.
  }
}

/** 업데이트 뒤 첫 실행에서만 위쪽 업데이트 내용 안내를 준비한다. */
export function useReleaseNotice(version: string, usedBefore: boolean | null) {
  const current = normalizedVersion(version);
  const [notes, setNotes] = useState<ReleaseNote[]>([]);

  useEffect(() => {
    if (usedBefore === null || !current) return;

    const seen = readSeenVersion();
    if (seen && compareVersion(seen, current) >= 0) {
      if (seen !== current) writeSeenVersion(current);
      setNotes([]);
      return;
    }

    if (!seen && !usedBefore) {
      writeSeenVersion(current);
      setNotes([]);
      return;
    }

    const nextNotes = notesBetween(seen ?? "", current);
    if (nextNotes.length) setNotes(nextNotes);
    else writeSeenVersion(current);
  }, [current, usedBefore]);

  return {
    current,
    notes,
    done: () => {
      if (current) writeSeenVersion(current);
      setNotes([]);
    },
  };
}
