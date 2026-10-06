"use client";

import { useState } from "react";
import { FileUp } from "lucide-react";

/** A file input that looks like a drop area. The real input covers the area, so clicking opens the file picker and
 *  dropping files onto it works natively; forms submit it as usual. */
export function DropZone({
  name = "file", accept = "application/pdf,.pdf", multiple = false, required = false, disabled = false,
  title, hint, label, onFiles,
}: {
  name?: string; accept?: string; multiple?: boolean; required?: boolean; disabled?: boolean;
  title: string; hint?: string; label?: string; onFiles?: (files: File[]) => void;
}) {
  const [over, setOver] = useState(false);
  const [chosen, setChosen] = useState<string[]>([]);
  return (
    <div className={`dropzone${over ? " over" : ""}`} onDragEnter={() => setOver(true)} onDragLeave={() => setOver(false)} onDrop={() => setOver(false)}>
      <FileUp aria-hidden="true" />
      {chosen.length ? (
        <span className="files">{chosen.length === 1 ? chosen[0] : `${chosen.length} files: ${chosen.slice(0, 3).join(", ")}${chosen.length > 3 ? "…" : ""}`}</span>
      ) : (
        <span><strong>{title}</strong> or click to choose</span>
      )}
      {hint && <span className="mini">{hint}</span>}
      <input type="file" name={name} accept={accept} multiple={multiple} required={required} disabled={disabled}
        aria-label={label ?? title}
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          setChosen(files.map((f) => f.name));
          onFiles?.(files);
        }} />
    </div>
  );
}
