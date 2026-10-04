"use client";

import { useActionState, useState } from "react";
import type { FormState, MessageState } from "@/app/actions";
import type { MessageView } from "@/lib/api";

const KIND: Record<MessageView["kind"], string> = {
  candidate_outreach: "First contact",
  follow_up: "Follow-up",
  client_submission: "Introduction to the client",
  interview_confirm: "Interview confirmation",
  decline: "Not this time",
};

const STATUS: Record<MessageView["status"], string> = {
  draft: "draft here",
  in_mailbox: "in your mailbox drafts",
  sent: "sent",
  replied: "replied",
  cancelled: "cancelled (they replied)",
};

type Act = (s: FormState, f: FormData) => Promise<FormState>;

/** Draft a message. Written only from approved facts, the job's public details and what was said on the call. */
export function DraftMessage({ action, hasEmail, jobs, contacts }: { action: Act; hasEmail: boolean;
  jobs: { id: string; title: string }[]; contacts: { id: string; name: string; role: string | null; job_id: string; job: string }[] }) {
  const [state, formAction, pending] = useActionState(action, {});
  const [kind, setKind] = useState(hasEmail ? "candidate_outreach" : "client_submission");
  const toClient = kind === "client_submission";
  return (
    <form action={formAction} className="logact">
      <div className="row">
        <select name="kind" aria-label="What kind of message" value={kind} onChange={(e) => setKind(e.target.value)}>
          {hasEmail && <option value="candidate_outreach">First contact</option>}
          <option value="client_submission">Introduce to the client</option>
          {hasEmail && <option value="interview_confirm">Interview confirmation</option>}
          {hasEmail && <option value="decline">Not this time</option>}
        </select>
        {toClient ? (
          <select name="contact_id" aria-label="Who at the client" defaultValue="">
            <option value="" disabled>{contacts.length ? "to whom at the client…" : "no client contacts with an email yet"}</option>
            {contacts.map((c) => <option key={`${c.id}|${c.job_id}`} value={`${c.id}|${c.job_id}`}>{c.name}{c.role ? ` (${c.role})` : ""} · {c.job}</option>)}
          </select>
        ) : jobs.length > 0 && (
          <select name="job_id" aria-label="About which job" defaultValue={jobs[0]?.id}>
            <option value="">no particular job</option>
            {jobs.map((j) => <option key={j.id} value={j.id}>{j.title}</option>)}
          </select>
        )}
      </div>
      <div className="row">
        <input name="note" aria-label="Your line to include (optional)" placeholder={kind === "interview_confirm" ? "when and where, e.g. Tue 14:00, video" : "a line of your own to include (optional)"} className="grow" />
        <button className="btn small" disabled={pending}>{pending ? "Drafting…" : "Draft"}</button>
      </div>
      {!hasEmail && <p className="hint">No email for this person yet, so only an introduction to a client can be drafted.</p>}
      {state.error && <p className="error" role="alert">{state.error}</p>}
      {state.message && <p className="sub" role="status">{state.message}</p>}
    </form>
  );
}

type MsgAct = (s: MessageState, f: FormData) => Promise<MessageState>;

export function MessageCard({ m, connected, provider, edit, toMailbox, markSent, markReplied }: {
  m: MessageView; connected: boolean; provider: string | null; edit: MsgAct; toMailbox: (s: MessageState) => Promise<MessageState>;
  markSent: () => Promise<void>; markReplied: () => Promise<void> }) {
  const [saved, saveAction, saving] = useActionState(edit, {});
  const [boxed, boxAction, boxing] = useActionState(toMailbox, {});
  const [copied, setCopied] = useState(false);
  const mailboxName = provider === "microsoft" ? "Outlook" : "Gmail";
  const when = (m.replied_at ?? m.sent_at ?? m.created_at ?? "").slice(0, 10);
  return (
    <li className="message">
      <div className="row">
        <strong>{KIND[m.kind]}</strong>
        <span className="sub">to {m.to} · {STATUS[m.status]}{when ? ` · ${when}` : ""}</span>
        {m.status === "sent" && m.follow_up_due && <span className="sub">· follow-up drafted {m.follow_up_due.slice(0, 10)} unless they reply</span>}
      </div>
      {m.status === "draft" ? (
        <form action={saveAction} className="message-edit">
          <input name="subject" aria-label="Subject" defaultValue={m.subject} className="grow" />
          <textarea name="body" aria-label="Message" defaultValue={m.body} rows={8} />
          <div className="row">
            <button className="btn small" disabled={saving}>{saving ? "Saving…" : "Save edits"}</button>
            <button type="button" className="btn small" onClick={async () => {
              await navigator.clipboard?.writeText(`${m.subject}\n\n${m.body}`).catch(() => {});
              setCopied(true);
            }}>{copied ? "Copied" : "Copy"}</button>
            {connected && <button type="submit" formAction={boxAction} className="btn small primary" disabled={boxing}>
              {boxing ? "Putting it there…" : `Put in my ${mailboxName} drafts`}</button>}
            <button type="submit" formAction={markSent} className="btn small">I sent it myself</button>
          </div>
          {saved.error && <p className="error" role="alert">{saved.error}</p>}
          {boxed.error && <p className="error" role="alert">{boxed.error}</p>}
          {saved.message && !boxed.message && <p className="sub" role="status">{saved.message}</p>}
        </form>
      ) : (
        <details>
          <summary>{m.subject}</summary>
          <pre className="message-body">{m.body}</pre>
        </details>
      )}
      {boxed.message && <p className="sub" role="status">{boxed.message} {boxed.link && <a href={boxed.link} target="_blank" rel="noreferrer">Open it</a>}</p>}
      {(m.status === "in_mailbox" || m.status === "sent") && (
        <form className="row">
          {m.status === "in_mailbox" && <button formAction={markSent} className="btn small">Mark sent</button>}
          <button formAction={markReplied} className="btn small">They replied</button>
        </form>
      )}
    </li>
  );
}
