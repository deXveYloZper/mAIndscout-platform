"use client";

import { useActionState, useState } from "react";
import type { FormState } from "@/app/actions";

type Act = (s: FormState, f: FormData) => Promise<FormState>;

const STATES: [string, string][] = [["open", "Open"], ["on_hold", "On hold"], ["filled", "Filled"], ["cancelled", "Cancelled"]];

/** Close a role (on hold, filled, cancelled: sourcing stops, everything is kept) or open it again; or delete a role
 *  added by mistake. */
export function RoleControls({ state, setState, remove, foundOnly }: { state: string; setState: Act; remove: Act; foundOnly: number }) {
  const [saved, saveAction, saving] = useActionState(setState, {});
  const [gone, removeAction, removing] = useActionState(remove, {});
  const [confirm, setConfirm] = useState("");
  return (
    <details className="move rolecontrols">
      <summary className="btn ghost">{state === "open" ? "Close or delete" : `Role ${STATES.find(([k]) => k === state)?.[1].toLowerCase() ?? state}`}</summary>
      <div className="movebox">
        <form action={saveAction} className="logact">
          <div className="row">
            <select name="state" defaultValue={state === "open" ? "filled" : "open"} aria-label="The role is now">
              {STATES.filter(([k]) => k !== state).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
            <input name="note" placeholder="note for the client's timeline (optional)" aria-label="Note" className="grow" />
            <button className="btn small primary" disabled={saving}>{saving ? "Saving…" : "Save"}</button>
          </div>
          <p className="hint">Closing stops its sourcing and takes it off the open lists. Its people, history and messages are kept.</p>
          {saved.error && <p className="error" role="alert">{saved.error}</p>}
        </form>
        <form action={removeAction} className="logact danger-zone">
          <p className="sub"><strong>Delete the role</strong>, for one added by mistake: its hiring profile, pairs, sourcing and ad go.
            Spend stays in the ledger.</p>
          {foundOnly > 0 && (
            <label className="check"><input type="checkbox" name="remove_people" /> also remove the {foundOnly} {foundOnly === 1 ? "person" : "people"} only
              its sourcing found (public profiles, on no other role)</label>
          )}
          <div className="row">
            <input value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder='type "delete"' aria-label="Type delete to confirm" />
            <button className="btn small danger" disabled={removing || confirm.trim().toLowerCase() !== "delete"}>{removing ? "Deleting…" : "Delete role"}</button>
          </div>
          {gone.error && <p className="error" role="alert">{gone.error}</p>}
        </form>
      </div>
    </details>
  );
}
