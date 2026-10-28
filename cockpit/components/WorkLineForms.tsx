"use client";

import { useActionState } from "react";
import type { FormState } from "@/app/actions";

type Act = (s: FormState, f: FormData) => Promise<FormState>;

/** A line of the role's work in your own words; for a work line, whether it makes the job what it is. */
export function WorkLineForm({ action, kind, words = "", central = false, submit }: { action: Act; kind: "work" | "not";
  words?: string; central?: boolean | null; submit: string }) {
  const [state, formAction, pending] = useActionState(action, {});
  return (
    <form action={formAction} className="editreq workline">
      <textarea name="words" defaultValue={words} rows={2}
        aria-label={kind === "work" ? "One thing the hire will do" : "A job that looks like this one but is a different job"}
        placeholder={kind === "work" ? "One thing the hire will do, in plain words" : "A job with the same words but different work"} />
      <div className="row">
        {kind === "work" && (
          <label className="check" title="It makes this job what it is, as opposed to work any similar job has">
            <input type="checkbox" name="central" defaultChecked={Boolean(central)} /> at the heart of the job
          </label>
        )}
        <button className="btn small primary" disabled={pending}>{pending ? "Saving…" : submit}</button>
      </div>
      {state.error && <p className="error" role="alert">{state.error}</p>}
      {state.message && <p className="sub" role="status">{state.message}</p>}
    </form>
  );
}
