"use client";

import { useActionState } from "react";
import type { FormState } from "@/app/actions";

export function AddContact({ action }: { action: (s: FormState, f: FormData) => Promise<FormState> }) {
  const [state, formAction, pending] = useActionState(action, {});
  return (
    <form action={formAction} className="row addcontact">
      <input name="name" aria-label="Contact name" placeholder="name" size={16} />
      <input name="role" aria-label="Role" placeholder="role, e.g. Head of Engineering" size={22} />
      <input name="email" aria-label="Email" placeholder="email" size={18} />
      <input name="phone" aria-label="Phone" placeholder="phone" size={12} />
      <input name="linkedin" aria-label="LinkedIn" placeholder="LinkedIn" size={14} />
      <button className="btn small" disabled={pending}>{pending ? "Adding…" : "Add contact"}</button>
      {state.error && <span className="error" role="alert">{state.error}</span>}
      {state.message && <span className="sub" role="status">{state.message}</span>}
    </form>
  );
}
