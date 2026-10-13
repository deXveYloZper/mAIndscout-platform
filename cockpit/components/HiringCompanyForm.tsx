"use client";

import { useActionState } from "react";
import type { FormState } from "@/app/actions";

/** Who is hiring: typed when the ad is anonymised, or changed. */
export function HiringCompanyForm({ action, current }: { action: (s: FormState, f: FormData) => Promise<FormState>; current?: string }) {
  const [state, formAction, pending] = useActionState(action, {});
  return (
    <form action={formAction} className="row">
      <input name="name" defaultValue={current ?? ""} placeholder="hiring company, e.g. Buona Ventura" aria-label="Hiring company" className="grow" />
      <button className="btn small primary" disabled={pending}>{pending ? "Saving…" : "Save"}</button>
      {state.error && <span className="error" role="alert">{state.error}</span>}
      {state.message && <span className="sub" role="status">{state.message}</span>}
    </form>
  );
}
