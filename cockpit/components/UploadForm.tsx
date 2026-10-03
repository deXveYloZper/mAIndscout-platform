"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";
import type { FormState } from "@/app/actions";

function Submit({ label, busy }: { label: string; busy: string }) {
  const { pending } = useFormStatus();
  return (
    <button type="submit" className="btn primary" disabled={pending}>
      {pending ? busy : label}
    </button>
  );
}

export function UploadForm({
  action,
  label,
  busy,
  multiple = false,
  hint,
}: {
  action: (state: FormState, form: FormData) => Promise<FormState>;
  label: string;
  busy: string;
  multiple?: boolean;
  hint?: string;
}) {
  const [state, formAction] = useActionState(action, {});
  return (
    <form action={formAction} className="upload">
      <input type="file" name="file" accept="application/pdf,.pdf" multiple={multiple} required />
      <Submit label={label} busy={busy} />
      {hint && <p className="hint">{hint}</p>}
      {state.message && <p className="ok">{state.message}</p>}
      {state.error && <p className="err">{state.error}</p>}
    </form>
  );
}
