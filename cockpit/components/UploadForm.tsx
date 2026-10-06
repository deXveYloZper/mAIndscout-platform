"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";
import type { FormState } from "@/app/actions";
import { DropZone } from "./DropZone";

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
  drop = "Drop the PDF here",
}: {
  action: (state: FormState, form: FormData) => Promise<FormState>;
  label: string;
  busy: string;
  multiple?: boolean;
  hint?: string;
  drop?: string;
}) {
  const [state, formAction] = useActionState(action, {});
  return (
    <form action={formAction} className="upload-form">
      <DropZone title={drop} multiple={multiple} required hint={hint} />
      <div className="row"><Submit label={label} busy={busy} /></div>
      {state.message && <p className="ok">{state.message}</p>}
      {state.error && <p className="err">{state.error}</p>}
    </form>
  );
}
