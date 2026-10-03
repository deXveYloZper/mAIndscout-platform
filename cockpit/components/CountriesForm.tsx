"use client";

import { useActionState } from "react";
import type { FormState } from "@/app/actions";

export function CountriesForm({ action, opened }: { action: (s: FormState, f: FormData) => Promise<FormState>; opened: string }) {
  const [state, formAction, pending] = useActionState(action, {});
  return (
    <form action={formAction} className="row">
      <label htmlFor="countries" className="sub">Also accept people living or working in</label>
      <input id="countries" name="countries" defaultValue={opened} placeholder="e.g. Brazil, Mexico" />
      <button className="btn small" disabled={pending}>{pending ? "Saving…" : "Save"}</button>
      {state.error && <span className="error" role="alert">{state.error}</span>}
      {state.message && <span className="sub" role="status">{state.message}</span>}
    </form>
  );
}
