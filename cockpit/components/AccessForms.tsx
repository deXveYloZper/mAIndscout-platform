"use client";

import { useActionState, useState } from "react";
import type { FormState, LinkState, TwoStepState } from "@/app/actions";

type Act = (s: FormState, f: FormData) => Promise<FormState>;

function Message({ state }: { state: FormState }) {
  return (
    <>
      {state.error && <p className="err" role="alert">{state.error}</p>}
      {state.message && <p className="ok" role="status">{state.message}</p>}
    </>
  );
}

export function SignInForm({ action }: { action: Act }) {
  const [state, formAction, pending] = useActionState(action, {});
  return (
    <form action={formAction} className="stack">
      <label>Email<input name="email" type="email" autoComplete="username" required autoFocus /></label>
      <label>Password<input name="password" type="password" autoComplete="current-password" required /></label>
      <button className="btn primary" disabled={pending}>{pending ? "Signing in…" : "Sign in"}</button>
      <Message state={state} />
    </form>
  );
}

export function CodeForm({ action }: { action: Act }) {
  const [state, formAction, pending] = useActionState(action, {});
  return (
    <form action={formAction} className="stack">
      <label>Code from your authenticator app
        <input name="code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9 ]{6,7}" maxLength={7} required autoFocus />
      </label>
      <button className="btn primary" disabled={pending}>{pending ? "Checking…" : "Continue"}</button>
      <Message state={state} />
    </form>
  );
}

export function AcceptForm({ action, needsName, existing, reset }: { action: Act; needsName: boolean; existing: boolean; reset: boolean }) {
  const [state, formAction, pending] = useActionState(action, {});
  return (
    <form action={formAction} className="stack">
      {needsName && <label>Your name<input name="name" autoComplete="name" required /></label>}
      <label>{existing && !reset ? "Your current password" : "Choose a password (at least 12 characters)"}
        <input name="password" type="password" autoComplete={existing && !reset ? "current-password" : "new-password"} required minLength={existing && !reset ? 1 : 12} />
      </label>
      {(!existing || reset) && <label>Repeat it<input name="repeat" type="password" autoComplete="new-password" required /></label>}
      <button className="btn primary" disabled={pending}>{pending ? "Saving…" : reset ? "Set new password" : "Join the desk"}</button>
      <Message state={state} />
    </form>
  );
}

export function PasswordForm({ action }: { action: Act }) {
  const [state, formAction, pending] = useActionState(action, {});
  return (
    <form action={formAction} className="stack">
      <label>Current password<input name="current" type="password" autoComplete="current-password" required /></label>
      <label>New password (at least 12 characters)<input name="new" type="password" autoComplete="new-password" required minLength={12} /></label>
      <label>Repeat the new password<input name="repeat" type="password" autoComplete="new-password" required /></label>
      <button className="btn" disabled={pending}>{pending ? "Saving…" : "Change password"}</button>
      <Message state={state} />
    </form>
  );
}

export function TwoStepSetup({ start, confirm }: { start: (s: TwoStepState) => Promise<TwoStepState>; confirm: Act }) {
  const [setup, startAction, starting] = useActionState(start, {});
  const [state, confirmAction, confirming] = useActionState(confirm, {});
  if (!setup.secret) {
    return (
      <form action={startAction}>
        <button className="btn primary" disabled={starting}>{starting ? "Preparing…" : "Set up two-step verification"}</button>
        <Message state={setup} />
      </form>
    );
  }
  return (
    <div className="stack">
      <p>In your authenticator app (Google Authenticator, Microsoft Authenticator, 1Password…), add an account with this key:</p>
      <p><code className="secret">{setup.secret}</code></p>
      <p className="sub">On a phone you can open <a href={setup.uri}>this link</a> instead. Then type the code the app shows:</p>
      <form action={confirmAction} className="row">
        <input name="code" inputMode="numeric" autoComplete="one-time-code" maxLength={7} required aria-label="Code from your authenticator app" />
        <button className="btn primary" disabled={confirming}>{confirming ? "Checking…" : "Turn on"}</button>
      </form>
      <Message state={state} />
    </div>
  );
}

function Link({ state }: { state: LinkState }) {
  const [copied, setCopied] = useState(false);
  if (!state.link) return <Message state={state} />;
  return (
    <div className="stack">
      <p className="ok" role="status">{state.message}</p>
      <div className="row">
        <code className="secret">{state.link}</code>
        <button type="button" className="btn small" onClick={async () => {
          await navigator.clipboard?.writeText(state.link!).catch(() => {});
          setCopied(true);
        }}>{copied ? "Copied" : "Copy"}</button>
      </div>
    </div>
  );
}

export function InviteForm({ action }: { action: (s: LinkState, f: FormData) => Promise<LinkState> }) {
  const [state, formAction, pending] = useActionState(action, {});
  return (
    <form action={formAction} className="stack">
      <div className="row">
        <input name="email" type="email" required placeholder="their email" aria-label="Their email" />
        <select name="role" aria-label="Role" defaultValue="recruiter">
          <option value="recruiter">Recruiter</option>
          <option value="owner">Owner</option>
        </select>
        <button className="btn primary" disabled={pending}>{pending ? "Creating…" : "Create invitation link"}</button>
      </div>
      <Link state={state} />
    </form>
  );
}

export function ResetButton({ action, name }: { action: (s: LinkState) => Promise<LinkState>; name: string }) {
  const [state, formAction, pending] = useActionState(action, {});
  return (
    <form action={formAction}>
      <button className="btn small" disabled={pending} aria-label={`New sign-in link for ${name}`}>{pending ? "…" : "New sign-in link"}</button>
      <Link state={state} />
    </form>
  );
}
