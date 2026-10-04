"use client";

import { useActionState, useState } from "react";
import type { FormState } from "@/app/actions";
import { PASS_REASONS, PIPELINE, STATE_LABEL } from "@/lib/format";

const NEEDS: Record<string, string> = {
  submitted: "to whom, how",
  withdrawn: "why they pulled out",
  client_rejected: "what the client said",
};
const ENDINGS = ["placed", "we_passed", "withdrawn", "client_rejected"];

/** The pair's place in the pipeline. Every move is recorded; nothing is ever deleted. */
export function StateControls({ state, action }: { state: string; action: (s: FormState, f: FormData) => Promise<FormState> }) {
  const [result, formAction, pending] = useActionState(action, {});
  const [target, setTarget] = useState("");
  const reopening = ENDINGS.includes(state) && target && !ENDINGS.includes(target);
  const hint = target === "we_passed" ? "note (optional)" : NEEDS[target] ?? (reopening ? "why reopen" : "note (optional)");
  return (
    <div className="statecontrols">
      <p>Stage: <span className={`statetag ${state}`}>{STATE_LABEL[state] ?? state}</span></p>
      <form action={formAction} className="row">
        <select name="state" aria-label="Move to" value={target} onChange={(e) => setTarget(e.target.value)} required>
          <option value="" disabled>move to…</option>
          {PIPELINE.filter(([k]) => k !== "new" && k !== state).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
        {target === "we_passed" && (
          <select name="reason" aria-label="Reason for passing" defaultValue="" required>
            <option value="" disabled>reason…</option>
            {PASS_REASONS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        )}
        <input name="note" placeholder={hint} aria-label="Note for this move" size={26}
          required={Boolean(NEEDS[target] || reopening)} />
        <button className="btn small primary" disabled={pending || !target}>{pending ? "Saving…" : "Move"}</button>
      </form>
      {target === "client_rejected" && <p className="hint">A client rejection blocks this person at this client (every job there) until someone lifts it.</p>}
      {result.error && <p className="err" role="alert">{result.error}</p>}
    </div>
  );
}
