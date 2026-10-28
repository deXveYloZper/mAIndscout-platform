"use client";

import { type ReactNode, useActionState, useEffect, useRef, useState } from "react";
import type { FormState } from "@/app/actions";
import { STRENGTHS } from "@/lib/format";

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

/** "change" on a line: a small box that closes with Escape, a click outside it, or its ✕, without doing anything
    (owner, 2026-10-20: "i cannot exit that box once it pops up without taking action"). */
export function Change({ children, label = "Change this requirement" }: { children: ReactNode; label?: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    const click = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("keydown", key);
    document.addEventListener("mousedown", click);
    return () => { document.removeEventListener("keydown", key); document.removeEventListener("mousedown", click); };
  }, [open]);
  return (
    <div className="change" ref={ref}>
      <button type="button" className="changelink" aria-expanded={open} onClick={() => setOpen(!open)}>change</button>
      {open && (
        <div className="changebox" role="dialog" aria-label={label}>
          <button type="button" className="changeclose" aria-label="Close without changing" onClick={() => setOpen(false)}>✕</button>
          {children}
        </div>
      )}
    </div>
  );
}

/** A requirement in the recruiter's own words and how much it matters: the desk reads changed words again. */
export function EditForm({ action, text, strength }: { action: Act; text: string; strength: string }) {
  const [state, formAction, pending] = useActionState(action, {});
  return (
    <form action={formAction} className="editreq">
      <textarea name="text" defaultValue={text} rows={Math.max(2, Math.min(6, Math.ceil(text.length / 50)))}
        aria-label="The requirement, in your words" />
      <div className="row">
        <select name="strength" defaultValue={strength} aria-label="How much it matters">
          {STRENGTHS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          {!STRENGTHS.some(([v]) => v === strength) && <option value={strength}>{strength}</option>}
        </select>
        <button className="btn small primary" disabled={pending}>{pending ? "Reading your words…" : "Save"}</button>
      </div>
      {state.error && <p className="error" role="alert">{state.error}</p>}
      <p className="hint">Change the words and the desk reads them again: 5 years instead of 7, a company size, any wording.</p>
    </form>
  );
}

/** Anything about the role in the recruiter's own words: read like notes, the brief read again. */
export function TellForm({ action, asked }: { action: Act; asked: boolean }) {
  const [state, formAction, pending] = useActionState(action, {});
  return (
    <form action={formAction} className="tell">
      <label htmlFor="tell-text" className="sub">{asked ? "Or tell the desk anything else about the role" : "Tell the desk anything about the role"}</label>
      <textarea id="tell-text" name="text" rows={3}
        placeholder="In your own words: a new must-have, a correction, anything the hiring manager said." />
      <div className="row">
        <button className="btn small primary" disabled={pending}>{pending ? "Reading…" : "Add to the profile"}</button>
        {state.error && <span className="error" role="alert">{state.error}</span>}
        {state.message && <span className="sub" role="status">{state.message}</span>}
      </div>
    </form>
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
