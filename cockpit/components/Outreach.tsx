"use client";

import { type ReactNode, useState, useTransition } from "react";
import { ExternalLink, Undo2 } from "lucide-react";
import { outreachStep } from "@/app/actions";
import type { CardKeys, ContactChannel, ReplyOutcome } from "@/lib/api";

/* The owner's fast workflow on a role's suggestions (docs/next/PLAN.md section 4c): open the profile, come back, decide in
   one click; then contacted, replied, call booked. Every step stays on the page. */

const CHANNELS: [ContactChannel, string][] = [
  ["linkedin_invite", "LinkedIn request"], ["linkedin_message", "LinkedIn message"], ["inmail", "InMail / Recruiter"], ["email", "Email"],
];
const PASS: [string, string][] = [["level", "Level"], ["skills", "Skills"], ["location", "Location"], ["domain", "Field"], ["other", "Other"]];
const OUTCOMES: [ReplyOutcome, string][] = [
  ["interested", "Interested"], ["not_now", "Not now"], ["not_interested", "Not interested"], ["stop", "Asked to stop"],
];

const link = (profile: string) => (profile.startsWith("http") ? profile : `https://${profile}`);

function useStep(jobId: string, candidateId: string) {
  const [pending, start] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const go = (step: string, body: Record<string, unknown> = {}) =>
    start(async () => {
      const r = await outreachStep(jobId, candidateId, step, body);
      setError(r.error ?? null);
    });
  return { pending, error, go };
}

const host = (u: string) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return u; } };

/** Their public profile one click from the name (owner, 2026-10-20): LinkedIn first, then pages of their own (a
    portfolio, GitHub). Opening one marks the suggestion seen, so coming back to the desk shows where you were. */
export function QuickLinks({ jobId, s }: { jobId: string; s: CardKeys }) {
  const { go } = useStep(jobId, s.candidate_id);
  const links = s.links ?? (s.profile ? [{ kind: "linkedin" as const, url: link(s.profile) }] : []);
  if (!links.length) return null;
  const seen = Boolean(s.contact?.viewed_at);
  return (
    <span className="quicklinks">
      {links.map((l) => (
        <a key={l.url} className={`quicklink${seen ? " seen" : ""}`} href={l.url} target="_blank" rel="noreferrer"
           title={`${l.kind === "linkedin" ? "Their LinkedIn profile" : "Their own page"}, in a new tab${seen ? " (opened before)" : ""}`}
           onClick={() => { if (!seen) go("viewed"); }}>
          {l.kind === "linkedin" ? "LinkedIn" : host(l.url)}<ExternalLink aria-hidden="true" />
        </a>
      ))}
      {seen && <span className="quickseen" title="You opened their profile">seen</span>}
    </span>
  );
}

/** The buttons for where this person is: decide, contacted how, their reply, the call. */
export function Triage({ jobId, s }: { jobId: string; s: CardKeys }) {
  const { pending, error, go } = useStep(jobId, s.candidate_id);
  const [passing, setPassing] = useState(false);
  const [callAt, setCallAt] = useState("");
  const t = s.contact ?? {};
  const undo = (
    <button className="btn small ghost" disabled={pending} onClick={() => go("undo")} title="Back to the suggestions">
      <Undo2 aria-hidden="true" />Undo
    </button>
  );
  const outcomes = (
    <div className="row" role="group" aria-label="Their reply">
      <span className="hint">They replied:</span>
      {OUTCOMES.map(([o, label]) => (
        <button key={o} className={`btn small${o === "interested" ? " primary" : ""}`} disabled={pending}
                onClick={() => go("replied", { outcome: o })}>{label}</button>
      ))}
    </div>
  );
  let body: ReactNode = null;
  if (s.stage === "to_review" || s.stage === "later") {
    body = (
      <>
        <div className="row" role="group" aria-label="Decide">
          <button className="btn small primary" disabled={pending} onClick={() => go("decide", { choice: "reach_out" })}>Reach out</button>
          {s.stage === "to_review" && <button className="btn small" disabled={pending} onClick={() => go("decide", { choice: "later" })}>Later</button>}
          <button className="btn small ghost" disabled={pending} aria-expanded={passing} onClick={() => setPassing(!passing)}>Not for this role</button>
          {s.stage === "later" && undo}
        </div>
        {passing && (
          <div className="row" role="group" aria-label="Why not">
            <span className="hint">Why?</span>
            {PASS.map(([r, label]) => (
              <button key={r} className="chip small" disabled={pending} onClick={() => go("decide", { choice: "pass", reason: r })}>{label}</button>
            ))}
          </div>
        )}
      </>
    );
  } else if (s.stage === "to_contact") {
    body = (
      <div className="row" role="group" aria-label="Contacted how">
        <span className="hint">Contacted by:</span>
        {CHANNELS.map(([c, label]) => (
          <button key={c} className="btn small" disabled={pending} onClick={() => go("contacted", { channel: c })}>{label}</button>
        ))}
        {undo}
      </div>
    );
  } else if (s.stage === "contacted") {
    body = (
      <>
        {t.unclear && (
          <div className="warn" role="group" aria-label="Which person">
            LinkedIn&apos;s email &ldquo;{t.unclear.subject}&rdquo; names someone with this name, and {t.unclear.others} other
            {t.unclear.others === 1 ? " person" : " people"} you contacted share it. Is it about this person?
            <div className="row">
              <button className="btn small" disabled={pending} onClick={() => go("linkedin-email", { mine: true })}>Yes, this one</button>
              <button className="btn small ghost" disabled={pending} onClick={() => go("linkedin-email", { mine: false })}>No</button>
            </div>
          </div>
        )}
        {outcomes}
      </>
    );
  } else if (s.stage === "replied") {
    body = t.reply && !t.reply.outcome ? outcomes : t.reply?.outcome === "interested" ? (
      <div className="row" role="group" aria-label="Book the call">
        <input type="datetime-local" value={callAt} onChange={(e) => setCallAt(e.target.value)} aria-label="When is the call (optional)" />
        <button className="btn small primary" disabled={pending}
                onClick={() => go("call-booked", { when: callAt ? new Date(callAt).toISOString() : null })}>Call booked</button>
      </div>
    ) : null;
  } else if (s.stage === "passed" && !t.contacted_at) {
    body = <div className="row">{undo}</div>;
  }
  return (
    <div className="triage">
      {body}
      {pending && <p className="sub" role="status">Saving…</p>}
      {error && <p className="error" role="alert">{error}</p>}
    </div>
  );
}
