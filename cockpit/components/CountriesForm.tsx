"use client";

import { useActionState } from "react";
import type { FormState } from "@/app/actions";

/** Where people must live for this role: the one place its countries are kept (names or codes). */
export function CountriesForm({ action, current }: { action: (s: FormState, f: FormData) => Promise<FormState>; current: string }) {
  const [state, formAction, pending] = useActionState(action, {});
  return (
    <form action={formAction} className="row">
      <label htmlFor="countries" className="sub">Must live in or work from</label>
      <input id="countries" name="countries" defaultValue={current} placeholder="e.g. Italy, Spain (empty: no limit)" className="grow" />
      <button className="btn small" disabled={pending}>{pending ? "Saving…" : "Save"}</button>
      {state.error && <span className="error" role="alert">{state.error}</span>}
      {state.message && <span className="sub" role="status">{state.message}</span>}
    </form>
  );
}
