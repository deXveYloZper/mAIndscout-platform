"use client";

import { useActionState } from "react";
import type { FormState } from "@/app/actions";

export function EraseForm({ action }: { action: (state: FormState, form: FormData) => Promise<FormState> }) {
  const [state, formAction, pending] = useActionState(action, {});
  return (
    <details className="panel danger">
      <summary>Forget this person</summary>
      <p>
        Deletes every fact, document, original file and review item about this person, then checks that nothing is
        left. Their email, phone and LinkedIn are kept only as one-way hashes, so a later upload of them is blocked.
        This cannot be undone.
      </p>
      <form action={formAction} className="row">
        <input name="reason" placeholder="reason (optional, no personal details)" aria-label="Reason" size={32} />
        <input name="confirm" placeholder='type "forget"' aria-label='Type forget to confirm' required size={14} />
        <button className="btn danger" disabled={pending}>{pending ? "Erasing…" : "Erase"}</button>
      </form>
      {state.error && <p className="err">{state.error}</p>}
    </details>
  );
}
