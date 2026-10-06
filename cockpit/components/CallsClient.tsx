"use client";

import { useRouter } from "next/navigation";
import { useActionState, useEffect } from "react";
import type { FormState } from "@/app/actions";

/** While a call is being read: look again every few seconds (for two minutes at most). */
export function Refresh({ every = 3000, upTo = 120000 }: { every?: number; upTo?: number }) {
  const router = useRouter();
  useEffect(() => {
    const started = Date.now();
    const id = setInterval(() => (Date.now() - started > upTo ? clearInterval(id) : router.refresh()), every);
    return () => clearInterval(id);
  }, [router, every, upTo]);
  return null;
}

export function TranscriptForm({ action }: { action: (s: FormState, f: FormData) => Promise<FormState> }) {
  const [state, formAction, pending] = useActionState(action, {});
  return (
    <form action={formAction} className="transcript">
      <textarea name="text" rows={5} aria-label="Paste the call transcript"
        placeholder={"Recruiter: What are you looking for next?\nAna Silva: Honestly I'm tired of start-ups, nothing under 200 people…"} />
      <div className="row">
        <input type="file" name="file" accept=".txt,.vtt,.srt,.docx,text/plain" aria-label="Transcript file" />
        <button className="btn" disabled={pending}>{pending ? "Sending…" : "Read the call"}</button>
      </div>
      {state.error && <p className="error" role="alert">{state.error}</p>}
      {state.message && <p className="sub" role="status">{state.message}</p>}
    </form>
  );
}
