"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { checkTasks, queueCv, refreshAfterUpload, type TaskView } from "@/app/actions";
import { BAND_LABEL, reasonWords } from "@/lib/format";
import type { Band } from "@/lib/api";

type Row = { file: string; taskId?: string; error?: string; task?: TaskView };

/** Drop several CVs: each is stored at once and read in the background; rows fill in as each read finishes. */
export function MultiUpload({ jobId }: { jobId: string | null }) {
  const [files, setFiles] = useState<File[]>([]);
  const [rows, setRows] = useState<Row[]>([]);
  const [uploading, setUploading] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const rowsRef = useRef<Row[]>([]);
  rowsRef.current = rows; // the interval always reads the latest rows, never a stale copy
  const pending = rows.filter((r) => r.taskId && !["done", "failed"].includes(r.task?.status ?? "queued"));

  useEffect(() => {
    if (!pending.length) {
      if (timer.current) {
        clearInterval(timer.current);
        timer.current = null;
        refreshAfterUpload(jobId);
      }
      return;
    }
    if (timer.current) return;
    timer.current = setInterval(async () => {
      const ids = rowsRef.current.filter((r) => r.taskId).map((r) => r.taskId!);
      const views = await checkTasks(ids);
      setRows((prev) => prev.map((r) => ({ ...r, task: views.find((v) => v.id === r.taskId) ?? r.task })));
    }, 2000);
  }, [pending.length, jobId]);

  useEffect(() => () => { if (timer.current) clearInterval(timer.current); }, []);

  async function start(e: React.FormEvent) {
    e.preventDefault();
    if (!files.length || uploading) return;
    setUploading(true);
    const queued: Row[] = [];
    for (const file of files) {
      const form = new FormData();
      form.append("file", file);
      queued.push(await queueCv(jobId, form));
      setRows([...queued]);
    }
    setUploading(false);
    setFiles([]);
    (e.target as HTMLFormElement).reset();
  }

  const busy = uploading || pending.length > 0;
  const done = rows.filter((r) => r.task?.status === "done").length;
  return (
    <form onSubmit={start} className="upload" aria-busy={busy}>
      <input type="file" name="file" accept="application/pdf,.pdf" multiple required disabled={uploading}
        onChange={(e) => setFiles(Array.from(e.target.files ?? []))} aria-label="CV files (PDF)" />
      <button type="submit" className="btn primary" disabled={uploading || !files.length}>
        {uploading ? "Uploading…" : files.length > 1 ? `Read and band ${files.length} CVs` : "Read and band"}
      </button>
      <p className="hint">
        Files are stored at once and read in the background (about 15 s each, several at a time); you can leave this page.{" "}
        {jobId ? "Each person is placed in a band against this job. A band is not a score." : "People join the pool with no job; put them on a job from their page."}
      </p>
      {busy && rows.length > 0 && <p className="sub" role="status">Reading {done} of {rows.length} done…</p>}
      {rows.length > 0 && (
        <ul className="results" aria-live="polite">
          {rows.map((r, i) => {
            const t = r.task;
            const res = t?.result ?? {};
            return (
              <li key={i} className={r.error || t?.status === "failed" ? "err" : ""}>
                <span className="file">{r.file}</span>
                {r.error ? <span>{r.error}</span>
                  : !t || t.status === "queued" ? <span className="sub">waiting</span>
                  : t.status === "running" ? <span className="sub">reading…</span>
                  : t.status === "failed" ? <span>{t.error}</span>
                  : res.status === "suppressed" ? <span>Not stored: this person was erased earlier.</span>
                  : res.subject_id ? (
                    <>
                      <Link href={`/people/${res.subject_id}`}>{t.name ?? "name not read"}</Link>
                      <span className={`bandtag ${res.band ?? ""}`}>{res.band ? BAND_LABEL[res.band as Band] : "in the pool"}</span>
                      <span className="sub">{reasonWords(res.reason ?? null)}</span>
                    </>
                  ) : <span>{res.status}</span>}
              </li>
            );
          })}
        </ul>
      )}
    </form>
  );
}
