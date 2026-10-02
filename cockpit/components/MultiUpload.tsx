"use client";

import Link from "next/link";
import { useState } from "react";
import { dropOneCv, refreshAfterUpload, type DropResult } from "@/app/actions";
import { BAND_LABEL, reasonWords } from "@/lib/format";
import type { Band } from "@/lib/api";

/** Drop several CVs; they are read one after another, and each result appears as soon as it is ready. */
export function MultiUpload({ jobId }: { jobId: string | null }) {
  const [files, setFiles] = useState<File[]>([]);
  const [results, setResults] = useState<DropResult[]>([]);
  const [current, setCurrent] = useState<string | null>(null);
  const busy = current !== null;

  async function start(e: React.FormEvent) {
    e.preventDefault();
    if (!files.length || busy) return;
    setResults([]);
    for (const file of files) {
      setCurrent(file.name);
      const form = new FormData();
      form.append("file", file);
      const r = await dropOneCv(jobId, form);
      setResults((prev) => [...prev, r]);
    }
    setCurrent(null);
    setFiles([]);
    (e.target as HTMLFormElement).reset();
    await refreshAfterUpload(jobId);
  }

  const done = results.length;
  return (
    <form onSubmit={start} className="upload" aria-busy={busy}>
      <input type="file" name="file" accept="application/pdf,.pdf" multiple required disabled={busy}
        onChange={(e) => setFiles(Array.from(e.target.files ?? []))} aria-label="CV files (PDF)" />
      <button type="submit" className="btn primary" disabled={busy || !files.length}>
        {busy ? `Reading ${Math.min(done + 1, files.length)} of ${files.length}…` : files.length > 1 ? `Read and band ${files.length} CVs` : "Read and band"}
      </button>
      <p className="hint">
        Every file is read (about 15 s each).{" "}
        {jobId ? "Each person is placed in a band against this job. A band is not a score." : "People join the pool with no job; put them on a job from their page."}
      </p>
      {busy && <p className="sub" role="status">Reading {current}…</p>}
      {results.length > 0 && (
        <ul className="results" aria-live="polite">
          {results.map((r, i) => (
            <li key={i} className={r.ok ? "" : "err"}>
              <span className="file">{r.file}</span>
              {r.ok && r.personId ? (
                <>
                  <Link href={`/people/${r.personId}`}>{r.name ?? "name not read"}</Link>
                  <span className={`bandtag ${r.band ?? ""}`}>{r.band ? BAND_LABEL[r.band as Band] : "in the pool"}</span>
                  <span className="sub">{reasonWords(r.reason ?? null)}</span>
                </>
              ) : r.status === "suppressed" ? (
                <span>Not stored: this person was erased earlier.</span>
              ) : (
                <span>{r.error ?? r.status}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </form>
  );
}
