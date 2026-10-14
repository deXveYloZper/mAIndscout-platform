"use client";

import { useActionState } from "react";
import type { FormState } from "@/app/actions";

/** A company's website or LinkedIn page: how Exa confirms it is this company (a similar name is never enough). */
export function CompanyKeysForm({ action, website, linkedin }: { action: (s: FormState, f: FormData) => Promise<FormState>;
  website: string | null; linkedin: string | null }) {
  const [state, formAction, pending] = useActionState(action, {});
  return (
    <form action={formAction} className="row">
      <input name="website" defaultValue={website ?? ""} placeholder="website, e.g. buonaventura.it" aria-label="Company website" />
      <input name="linkedin" defaultValue={linkedin ? `linkedin.com/company/${linkedin}` : ""} placeholder="linkedin.com/company/…"
        aria-label="Company LinkedIn page" />
      <button className="btn small" disabled={pending}>{pending ? "Saving…" : "Save"}</button>
      {state.error && <span className="error" role="alert">{state.error}</span>}
      {state.message && <span className="sub" role="status">{state.message}</span>}
    </form>
  );
}
