"use client";

import { useActionState } from "react";
import type { FormState } from "@/app/actions";
import type { SourcingMode } from "@/lib/api";
import { MODE_LABEL } from "@/lib/format";

type Act = (s: FormState, f: FormData) => Promise<FormState>;
type Act0 = (s: FormState) => Promise<FormState>;

function Said({ state }: { state: FormState }) {
  return (
    <>
      {state.error && <p className="error" role="alert">{state.error}</p>}
      {state.message && <p className="sub" role="status">{state.message}</p>}
    </>
  );
}


/** How often the role searches, how many strong suggestions to keep waiting, and its monthly budget. */
export function PlanSettings({ action, mode, target, budget }: { action: Act; mode: SourcingMode; target: number; budget: number }) {
  const [state, formAction, pending] = useActionState(action, {});
  return (
    <form action={formAction} className="logact">
      <div className="row">
        <label className="field">How often
          <select name="mode" defaultValue={mode} aria-label="How often this role searches">
            {(Object.keys(MODE_LABEL) as SourcingMode[]).map((m) => <option key={m} value={m}>{MODE_LABEL[m]}</option>)}
          </select>
        </label>
        <label className="field">Strong suggestions to keep waiting
          <input name="target" type="number" min={1} max={200} defaultValue={target} aria-label="Target" />
        </label>
        <label className="field">Monthly budget ($)
          <input name="budget" type="number" min={0} max={1000} step="0.5" defaultValue={budget} aria-label="Monthly budget in dollars" />
        </label>
        <button className="btn small primary" disabled={pending}>{pending ? "Saving…" : "Save"}</button>
      </div>
      <Said state={state} />
    </form>
  );
}

/** The titles that mean the same work, and the countries to search in. */
export function PlanWords({ action, variants, countries }: { action: Act; variants: string[]; countries: string[] }) {
  const [state, formAction, pending] = useActionState(action, {});
  return (
    <form action={formAction} className="logact">
      <label className="field grow">Titles to search for (one per line)
        <textarea name="variants" rows={3} defaultValue={variants.join("\n")} aria-label="Titles to search for" />
      </label>
      <div className="row">
        <label className="field grow">Countries: where people must live (the hiring profile&apos;s, names or codes)
          <input name="countries" defaultValue={countries.join(", ")} aria-label="Countries to search in" placeholder="e.g. Italy, Spain" />
        </label>
        <button className="btn small" disabled={pending}>{pending ? "Saving…" : "Save"}</button>
      </div>
      <Said state={state} />
    </form>
  );
}

export function AddTarget({ action }: { action: Act }) {
  const [state, formAction, pending] = useActionState(action, {});
  return (
    <form action={formAction} className="row">
      <input name="name" placeholder="a company to search" aria-label="Company to add" className="grow" />
      <button className="btn small" disabled={pending}>{pending ? "Adding…" : "Add"}</button>
      <Said state={state} />
    </form>
  );
}

export function OneClick({ action, label, busy, primary }: { action: Act0; label: string; busy: string; primary?: boolean }) {
  const [state, formAction, pending] = useActionState(action, {});
  return (
    <form action={formAction} className="row">
      <button className={`btn small${primary ? " primary" : ""}`} disabled={pending}>{pending ? busy : label}</button>
      <Said state={state} />
    </form>
  );
}

/** What they said yes to: this role, other roles, or both. */
export function PermissionForm({ action, jobs }: { action: Act; jobs: { id: string; title: string }[] }) {
  const [state, formAction, pending] = useActionState(action, {});
  return (
    <form action={formAction} className="logact">
      <div className="row">
        <label className="check"><input type="checkbox" name="this_role" /> put forward for</label>
        <select name="job_id" aria-label="Which role" defaultValue={jobs[0]?.id ?? ""}>
          <option value="">choose the role…</option>
          {jobs.map((j) => <option key={j.id} value={j.id}>{j.title}</option>)}
        </select>
        <label className="check"><input type="checkbox" name="other_roles" /> other roles too</label>
      </div>
      <div className="row">
        <select name="how" aria-label="How they said it" defaultValue="message">
          <option value="message">in a message</option>
          <option value="call">on a call</option>
          <option value="email">by email</option>
          <option value="other">another way</option>
        </select>
        <input name="note" placeholder="their words, if useful (optional)" aria-label="Note" className="grow" />
        <button className="btn small" disabled={pending}>{pending ? "Saving…" : "Record"}</button>
      </div>
      <Said state={state} />
    </form>
  );
}

export function LiftStop({ action }: { action: Act }) {
  const [state, formAction, pending] = useActionState(action, {});
  return (
    <form action={formAction} className="row">
      <input name="note" placeholder="why they may be contacted again" aria-label="Why" required className="grow" />
      <button className="btn small" disabled={pending}>Contact again</button>
      <Said state={state} />
    </form>
  );
}

export function DeskBudget({ action, budget }: { action: Act; budget: number }) {
  const [state, formAction, pending] = useActionState(action, {});
  return (
    <form action={formAction} className="row">
      <label className="field">The desk&apos;s monthly sourcing budget ($)
        <input name="budget" type="number" min={0} max={10000} step="1" defaultValue={budget} aria-label="Desk sourcing budget" />
      </label>
      <button className="btn small" disabled={pending}>{pending ? "Saving…" : "Save"}</button>
      <Said state={state} />
    </form>
  );
}

export function AddOffLimits({ action }: { action: Act }) {
  const [state, formAction, pending] = useActionState(action, {});
  return (
    <form action={formAction} className="logact">
      <div className="row">
        <input name="name" placeholder="company never to source from" aria-label="Company" className="grow" />
        <label className="field">until (optional)<input name="until" type="date" aria-label="Off-limits until" /></label>
      </div>
      <div className="row">
        <input name="note" placeholder="why (optional)" aria-label="Why" className="grow" />
        <button className="btn small" disabled={pending}>{pending ? "Adding…" : "Add"}</button>
      </div>
      <Said state={state} />
    </form>
  );
}
