"use client";

import { useActionState } from "react";
import type { FormState } from "@/app/actions";

export function ContactFix({
  action,
  kind,
}: {
  action: (state: FormState, form: FormData) => Promise<FormState>;
  kind: string;
}) {
  const [state, formAction, pending] = useActionState(action, {});
  return (
    <form action={formAction} className="row">
      <input type="hidden" name="kind" value={kind} />
      <input name="value" placeholder={`correct ${kind}, as on the visible page`} aria-label={`Correct ${kind}`} required />
      <button className="btn small" disabled={pending}>Save correction</button>
      {state.message && <span className="ok">{state.message}</span>}
      {state.error && <span className="err">{state.error}</span>}
    </form>
  );
}
