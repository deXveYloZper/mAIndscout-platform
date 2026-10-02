"use client";

import { useActionState } from "react";
import type { FormState } from "@/app/actions";
import { PASS_REASONS, STATE_LABEL } from "@/lib/format";

/** The recruiter's progress on a pair. Every move is recorded; nothing is ever deleted. */
export function StateControls({ state, action }: { state: string; action: (s: FormState, f: FormData) => Promise<FormState> }) {
  const [result, formAction, pending] = useActionState(action, {});
  const closed = state === "we_passed" || state === "submitted";
  return (
    <div className="statecontrols">
      <p>Status: <span className={`statetag ${state}`}>{STATE_LABEL[state] ?? state}</span></p>
      {state === "new" && (
        <form action={formAction}>
          <input type="hidden" name="state" value="seen" />
          <button className="btn small" disabled={pending}>Mark seen</button>
        </form>
      )}
      {!closed && (
        <>
          <form action={formAction} className="row">
            <input type="hidden" name="state" value="submitted" />
            <input name="note" placeholder="to whom, how" aria-label="Submission note" required size={28} />
            <button className="btn small primary" disabled={pending}>Submitted</button>
          </form>
          <form action={formAction} className="row">
            <input type="hidden" name="state" value="we_passed" />
            <select name="reason" aria-label="Reason for passing" defaultValue="" required>
              <option value="" disabled>reason…</option>
              {PASS_REASONS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
            <input name="note" placeholder="note (optional)" aria-label="Note for passing" size={22} />
            <button className="btn small" disabled={pending}>We passed</button>
          </form>
        </>
      )}
      {closed && (
        <form action={formAction} className="row">
          <input type="hidden" name="state" value="seen" />
          <input name="note" placeholder="why reopen" aria-label="Reason to reopen" required size={28} />
          <button className="btn small" disabled={pending}>Reopen</button>
        </form>
      )}
      {result.error && <p className="err" role="alert">{result.error}</p>}
    </div>
  );
}
