"use client";

import { useRouter } from "next/navigation";
import { useActionState, useEffect, useRef, useTransition } from "react";
import type { FormState } from "@/app/actions";

/** While something runs in the background: look again every few seconds (up to a limit). A new look starts only once
 * the last one has arrived: a slow page refreshed every 3 seconds piled its refreshes on top of each other, cutting
 * each other off, while a search ran (2026-10-22). */
export function Refresh({ every = 3000, upTo = 120000 }: { every?: number; upTo?: number }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const busy = useRef(false);
  busy.current = pending;
  useEffect(() => {
    const started = Date.now();
    const id = setInterval(() => {
      if (Date.now() - started > upTo) return clearInterval(id);
      if (!busy.current && document.visibilityState === "visible") startTransition(() => router.refresh());
    }, every);
    return () => clearInterval(id);
  }, [router, every, upTo]);
  return null;
}

export function TranscriptForm({ action }: { action: (s: FormState, f: FormData) => Promise<FormState> }) {
  const [state, formAction, pending] = useActionState(action, {});
  return (
    <form action={formAction} className="transcript">
      <textarea name="text" rows={5} aria-label="Paste the call transcript"
        placeholder="Paste the call transcript here, as it was written down" />
      <div className="row">
        <input type="file" name="file" accept=".txt,.vtt,.srt,.docx,text/plain" aria-label="Transcript file" />
        <button className="btn" disabled={pending}>{pending ? "Sending…" : "Read the call"}</button>
      </div>
      {state.error && <p className="error" role="alert">{state.error}</p>}
      {state.message && <p className="sub" role="status">{state.message}</p>}
    </form>
  );
}
