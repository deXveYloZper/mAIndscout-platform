"use client";

import { useEffect, useRef } from "react";

const KEYS: [string[], string][] = [
  [["Ctrl", "K"], "Find a person, job or company, or run an action"],
  [["/"], "Find (same as Ctrl K)"],
  [["g", "t"], "Go to Today"],
  [["g", "j"], "Go to Jobs"],
  [["g", "i"], "Go to Inbox"],
  [["g", "p"], "Go to People"],
  [["g", "c"], "Go to Companies"],
  [["g", "s"], "Go to Search"],
  [["g", "r"], "Go to Refresh"],
  [["?"], "Show these shortcuts"],
];

export function Shortcuts({ onClose }: { onClose: () => void }) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    box.current?.focus();
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose]);
  return (
    <div className="palette-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="palette" role="dialog" aria-modal="true" aria-label="Keyboard shortcuts" tabIndex={-1} ref={box}>
        <div className="q"><strong style={{ padding: "16px 0" }}>Keyboard shortcuts</strong></div>
        <ul>
          {KEYS.map(([keys, what]) => (
            <li key={what} role="option" aria-selected="false" style={{ cursor: "default" }}>
              <span style={{ display: "inline-flex", gap: 4, minWidth: 92 }}>{keys.map((k) => <kbd key={k}>{k}</kbd>)}</span>
              <span>{what}</span>
            </li>
          ))}
        </ul>
        <div className="foot"><span><kbd>Esc</kbd> close</span><span>Shortcuts wait while you type in a field.</span></div>
      </div>
    </div>
  );
}
