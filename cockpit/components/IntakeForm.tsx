"use client";

import { useActionState } from "react";
import type { FormState } from "@/app/actions";

export function IntakeForm({ action }: { action: (s: FormState, f: FormData) => Promise<FormState> }) {
  const [state, formAction, pending] = useActionState(action, {});
  return (
    <form action={formAction} className="intake">
      <label htmlFor="intake-text" className="sub">Notes from the call with the hiring manager</label>
      <textarea id="intake-text" name="text" rows={6}
        placeholder="e.g. Really wants early-stage start-up experience (strong plus). Procurement domain is a strong plus and can replace the start-up experience. No candidates from big consultancies. Permanent." />
      <button className="btn" disabled={pending}>{pending ? "Reading the notes…" : "Read the notes"}</button>
      {state.error && <p className="error" role="alert">{state.error}</p>}
      {state.message && <p className="sub" role="status">{state.message}</p>}
    </form>
  );
}
