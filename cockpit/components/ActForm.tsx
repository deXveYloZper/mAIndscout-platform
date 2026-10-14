"use client";

import { type CSSProperties, type ReactNode, useActionState } from "react";
import type { FormState } from "@/app/actions";

/** A form whose server action can say no: the API's reason shows under its button, instead of nothing happening or a
 *  crash page (x-ray A7, A8, 2026-10-13). A repeated click (already done, already gone) stays quiet. */
export function ActForm({ action, children, className, style, id }: { action: (form: FormData) => Promise<FormState>;
  children: ReactNode; className?: string; style?: CSSProperties; id?: string }) {
  const [state, formAction] = useActionState(async (_: FormState, form: FormData) => (await action(form)) ?? {}, {});
  return (
    <form action={formAction} className={className} style={style} id={id}>
      {children}
      {state.error && <span className="error" role="alert">{state.error}</span>}
      {state.message && <span className="sub" role="status">{state.message}</span>}
    </form>
  );
}
