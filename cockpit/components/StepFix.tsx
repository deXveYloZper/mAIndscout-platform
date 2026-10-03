"use client";

import { useActionState } from "react";
import type { FormState } from "@/app/actions";
import { FAMILY_LABEL, LEVELS } from "@/lib/format";

export function StepFix({ action, family, level }: { action: (s: FormState, f: FormData) => Promise<FormState>; family: string; level: string | null }) {
  const [state, formAction, pending] = useActionState(action, {});
  return (
    <form action={formAction} className="row stepfix">
      <select name="role_family" defaultValue={family} aria-label="Kind of work">
        {Object.entries(FAMILY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
      </select>
      <select name="level" defaultValue={level ?? ""} aria-label="Level">
        <option value="">level not clear</option>
        {LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}
      </select>
      <button className="btn small" disabled={pending}>{pending ? "Saving…" : "Correct"}</button>
      {state.error && <span className="error" role="alert">{state.error}</span>}
      {state.message && <span className="sub" role="status">{state.message}</span>}
    </form>
  );
}
