"use client";

import { type ReactNode, useActionState, useState } from "react";
import type { FormState } from "@/app/actions";

type Act = (s: FormState, f: FormData) => Promise<FormState>;

/** A fold that stays as the person left it when the page refreshes (a notes form stays open while its result shows). */
export function Fold({ summary, open: initial = false, className, children }: { summary: ReactNode; open?: boolean;
  className?: string; children: ReactNode }) {
  const [open, setOpen] = useState(initial);
  return (
    <details className={className} open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>{summary}</summary>
      {children}
    </details>
  );
}

/** The answer to one of the brief's questions, in the uploader's own words: read like notes from the hiring manager. */
export function AnswerForm({ action, id }: { action: Act; id: string }) {
  const [state, formAction, pending] = useActionState(action, {});
  return (
    <form action={formAction} className="answer">
      <textarea id={id} name="answer" rows={2} aria-label="Your answer"
        placeholder="Your answer, in your own words (it is read like your notes)" />
      <div className="row">
        <button className="btn small primary" disabled={pending}>{pending ? "Reading the answer…" : "Answer"}</button>
        {state.error && <span className="error" role="alert">{state.error}</span>}
        {state.message && <span className="sub" role="status">{state.message}</span>}
      </div>
    </form>
  );
}
