import { useEffect, useRef } from "react";
import { X } from "lucide-react";

import type { ReleaseNote } from "./releaseNotes";

export function ReleaseNotesDialog({
  title,
  notes,
  current,
  onClose,
}: {
  title: string;
  notes: ReleaseNote[];
  current?: string;
  onClose: () => void;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div className="release-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="release-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="release-dialog-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="release-head">
          <h2 id="release-dialog-title">{title}</h2>
          <button type="button" className="icon-button is-borderless" onClick={onClose} aria-label="닫기">
            <X size={18} />
          </button>
        </header>
        <div className="release-body">
          {notes.map((note) => (
            <section key={note.version} className="release-version">
              <h3>
                v.{note.version}
                {note.version === current && <em>현재 버전</em>}
              </h3>
              {(
                [
                  ["added", "새로 추가", note.added],
                  ["changed", "수정", note.changed],
                ] as const
              )
                .filter(([, , entries]) => entries.length > 0)
                .map(([kind, label, entries]) => (
                  <div key={kind} className={`release-group is-${kind}`}>
                    <span className="release-tag">{label}</span>
                    <ul className="release-tools">
                      {entries.map((entry) => (
                        <li key={`${kind}-${entry.tool}`}>
                          <strong>{entry.tool}</strong>
                          <ul>
                            {entry.items.map((item) => <li key={item}>{item}</li>)}
                          </ul>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
            </section>
          ))}
        </div>
        <footer className="release-actions">
          <button ref={closeRef} type="button" className="primary-command" onClick={onClose}>확인</button>
        </footer>
      </section>
    </div>
  );
}
