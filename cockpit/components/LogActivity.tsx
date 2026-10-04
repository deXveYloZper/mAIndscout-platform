"use client";

import { useActionState } from "react";
import type { FormState } from "@/app/actions";

export function LogActivity({ action, jobs = [], contacts = [] }: { action: (s: FormState, f: FormData) => Promise<FormState>;
  jobs?: { id: string; title: string }[]; contacts?: { id: string; name: string }[] }) {
  const [state, formAction, pending] = useActionState(action, {});
  return (
    <form action={formAction} className="logact">
      <div className="row">
        <select name="kind" aria-label="What happened" defaultValue="call">
          <option value="call">Call</option>
          <option value="email">Email</option>
          <option value="meeting">Meeting</option>
          <option value="message">Message</option>
          <option value="note">Note</option>
        </select>
        <select name="direction" aria-label="Who reached out" defaultValue="out">
          <option value="out">we reached out</option>
          <option value="in">they reached out</option>
          <option value="">not relevant</option>
        </select>
        <input name="occurred_at" type="date" aria-label="When (default today)" />
        {contacts.length > 0 && (
          <select name="contact_id" aria-label="With whom" defaultValue="">
            <option value="">no one in particular</option>
            {contacts.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        )}
        {jobs.length > 0 && (
          <select name="job_id" aria-label="About which job" defaultValue="">
            <option value="">no particular job</option>
            {jobs.map((j) => <option key={j.id} value={j.id}>{j.title}</option>)}
          </select>
        )}
      </div>
      <div className="row">
        <input name="summary" aria-label="What happened, in a line" placeholder="what happened, in a line" className="grow" />
        <button className="btn small" disabled={pending}>{pending ? "Saving…" : "Log it"}</button>
      </div>
      {state.error && <p className="error" role="alert">{state.error}</p>}
      {state.message && <p className="sub" role="status">{state.message}</p>}
    </form>
  );
}
