"use client";

import { useActionState } from "react";
import type { FormState } from "@/app/actions";

export function FindMore({ action, tokens, byProfile }: { action: (s: FormState, f: FormData) => Promise<FormState>; tokens: string;
  byProfile?: string[] | null }) {
  const [state, formAction, pending] = useActionState(action, {});
  return (
    <form action={formAction} className="row">
      <label className="sub" htmlFor="cap">Look at up to</label>
      <input id="cap" name="cap" type="number" min={1} max={200} defaultValue={25} style={{ width: 70 }} aria-label="Cap" />
      <span className="sub">
        {byProfile?.length
          ? <>people on the desk whose career profile fits: {byProfile.join("; ")}</>
          : <>people already on the desk who mention {tokens || "the must-haves"}</>}
      </span>
      <button className="btn primary" disabled={pending}>{pending ? "Searching…" : "Find more people"}</button>
      {state.message && <p className="ok" role="status" style={{ width: "100%" }}>{state.message}</p>}
      {state.error && <p className="err" role="alert" style={{ width: "100%" }}>{state.error}</p>}
    </form>
  );
}
