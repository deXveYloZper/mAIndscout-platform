"use client";

import { useActionState } from "react";
import type { FormState } from "@/app/actions";
import type { WorkLineKind } from "@/lib/api";

type Act = (s: FormState, f: FormData) => Promise<FormState>;

const LABEL: Record<WorkLineKind, [string, string]> = {
  work: ["One thing the hire will do", "One thing the hire will do, in plain words"],
  not: ["A job that looks like this one but is a different job", "A job with the same words but different work"],
  title: ["A title people doing this work carry", "A title as people write it on a profile"],
  not_title: ["The title of a look-alike job", "A title with the same words but different work"],
  word: ["The work in a word, for a small company's search", "The work in one to three words"],
};

/** A line of the role's work in your own words; for a work line, whether it makes the job what it is. */
export function WorkLineForm({ action, kind, words = "", central = false, submit }: { action: Act; kind: WorkLineKind;
  words?: string; central?: boolean | null; submit: string }) {
  const [state, formAction, pending] = useActionState(action, {});
  return (
    <form action={formAction} className="editreq workline">
      <textarea name="words" defaultValue={words} rows={kind === "work" || kind === "not" ? 2 : 1}
        aria-label={LABEL[kind][0]} placeholder={LABEL[kind][1]} />
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
