"use client";

import { useActionState } from "react";
import type { FormState } from "@/app/actions";

const KINDS = [
  ["name", "Name"],
  ["email", "Email"],
  ["phone", "Phone"],
  ["linkedin", "LinkedIn"],
] as const;

/** Type a fact yourself. It is saved as approved, with you as the source. */
export function FactForm({
  action,
  kinds = KINDS.map(([k]) => k),
  defaultKind = "name",
  label = "Save",
}: {
  action: (state: FormState, form: FormData) => Promise<FormState>;
  kinds?: readonly string[];
  defaultKind?: string;
  label?: string;
}) {
  const [state, formAction, pending] = useActionState(action, {});
  const options = KINDS.filter(([k]) => kinds.includes(k));
  return (
    <form action={formAction} className="row">
      {options.length > 1 ? (
        <select name="kind" defaultValue={defaultKind} aria-label="Kind of fact">
          {options.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
      ) : (
        <input type="hidden" name="kind" value={options[0][0]} />
      )}
      <input name="value" placeholder="as written on the visible page" aria-label="Value" required size={28} />
      <button className="btn primary" disabled={pending}>{pending ? "Saving…" : label}</button>
      {state.message && <span className="ok" role="status">{state.message}</span>}
      {state.error && <span className="err" role="alert">{state.error}</span>}
    </form>
  );
}
