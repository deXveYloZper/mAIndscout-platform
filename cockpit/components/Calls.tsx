import { FileText, Quote } from "lucide-react";
import { applyCallReview, dismissCallReview, rejectClaim, retryCallReview } from "@/app/actions";
import type { CallLine, CallReview, Preference } from "@/lib/api";
import { Refresh, TranscriptForm } from "./CallsClient";

const OUTCOME: Record<string, string> = { confirmed: "Confirmed", not_met: "Not met", noted: "Noted" };

function Detail({ line }: { line: CallLine }) {
  switch (line.kind) {
    case "brief_answer":
      return <><span className="sub">{line.question}</span> <strong>{OUTCOME[line.outcome ?? ""] ?? ""}</strong>: {line.text}</>;
    case "confirm":
      return <>{line.current}</>;
    case "correct":
      return <><s>{line.current}</s> → <strong>{line.value || line.text}</strong></>;
    case "dispute":
      return <><s>{line.current}</s> <span className="sub">they say this is wrong</span></>;
    case "new_fact":
      return line.fact_type === "career_step"
        ? <>{line.title ?? "a role"} at {line.company}</>
        : <>{line.fact_type}: <strong>{line.value}</strong></>;
    case "preference":
      return <><strong>{line.summary}</strong>{line.replaces && <span className="sub"> (was: {line.replaces})</span>}</>;
    default:
      return <>{line.text}</>;
  }
}

function Line({ line, open }: { line: CallLine; open: boolean }) {
  const body = (
    <>
      <span className="cl-what"><Detail line={line} /></span>
      {line.quote && <q className="cl-quote">{line.quote}</q>}
      {line.note && <span className="cl-note">{line.note}</span>}
      {!open && line.result && line.result !== "applied" && <span className="cl-note">{line.result}</span>}
    </>
  );
  if (!open) return <li className={`callline ${line.result === "applied" ? "done" : "dropped"}`}>{body}</li>;
  return (
    <li className="callline">
      <label>
        <input type="checkbox" name="tick" value={line.id} defaultChecked={line.ticked} aria-label={`Keep: ${line.text}`} />
        <span className="cl-body">{body}</span>
      </label>
    </li>
  );
}

/** One call, read: every line ticked unless it would overturn a fact a person approved. One click approves them all. */
export function CallReviewCard({ review, path }: { review: CallReview; path: string }) {
  const when = review.created_at ? new Date(review.created_at).toLocaleDateString("en-GB", { day: "numeric", month: "short" }) : "";
  const head = (
    <div className="callhead">
      <FileText aria-hidden="true" />
      <div>
        <strong>Call review</strong>
        <span className="sub"> · {review.filename ?? "transcript"} · added {when} by {review.created_by}</span>
      </div>
    </div>
  );
  if (review.status === "reading") {
    return (
      <section className="panel callreview reading" aria-busy="true">
        {head}
        <p className="sub">Reading the call… this takes a few seconds.</p>
        <Refresh />
      </section>
    );
  }
  if (review.status === "failed") {
    return (
      <section className="panel callreview">
        {head}
        <p className="warn">{review.error}</p>
        <div className="row">
          <form action={retryCallReview.bind(null, review.id, path)}><button className="btn small">Try again</button></form>
          <form action={dismissCallReview.bind(null, review.id, path)}><button className="btn small ghost">Dismiss</button></form>
        </div>
      </section>
    );
  }
  const open = review.status === "pending";
  const count = review.sections.reduce((n, s) => n + s.lines.length, 0);
  const lists = review.sections.map((s) => (
    <div key={s.kind} className="callsection">
      <h4>{s.title} <span className="sub">({s.lines.length})</span></h4>
      <ul>{s.lines.map((l) => <Line key={l.id} line={l} open={open} />)}</ul>
    </div>
  ));
  if (!open) {
    return (
      <details className="panel callreview closed">
        <summary>{head}<span className="sub">{review.status === "applied" ? `approved by ${review.resolved_by}` : "dismissed"}</span></summary>
        {lists}
      </details>
    );
  }
  return (
    <section className="panel callreview" aria-label="Call review">
      {head}
      {count === 0 ? (
        <>
          <p className="sub">{review.error ?? "Nothing about the candidate was found in this transcript."}</p>
          <form action={dismissCallReview.bind(null, review.id, path)}><button className="btn small">Close</button></form>
        </>
      ) : (
        <>
          <p className="sub">
            What the call said, in their own words <Quote aria-hidden="true" className="inline-icon" />. Untick anything that is wrong;
            facts a person already approved are only changed if you tick them.
          </p>
          <form action={applyCallReview.bind(null, review.id, path)} id={`call-${review.id}`}>
            {lists}
          </form>
          <div className="row callactions">
            <button className="btn primary" form={`call-${review.id}`}>Approve all ticked</button>
            <form action={dismissCallReview.bind(null, review.id, path)}><button className="btn ghost">Dismiss the call</button></form>
          </div>
        </>
      )}
    </section>
  );
}

const FACET: Record<string, string> = { company_size: "Company size", employer_kind: "Kind of employer", setting: "On site / remote",
  places: "Where", work: "Kind of work", employment: "Permanent / contract" };

/** What they said they want, as approved: matching uses a must as a wall and a prefer as a note. */
export function WhatTheyWant({ prefs, path }: { prefs: Preference[]; path: string }) {
  return (
    <section className="panel wants">
      <h3>What they want</h3>
      {prefs.length === 0 ? (
        <p className="sub">Nothing yet. Add a call transcript below: what they say they want next is read from it.</p>
      ) : (
        <ul className="wantlist">
          {prefs.map((p) => (
            <li key={p.claim_id}>
              <span className="facet">{FACET[p.facet] ?? p.facet}</span>
              <span className={`strength ${p.strength}`}>{p.strength === "must" ? "must" : "prefers"}</span>
              <span className="what">{p.summary.replace(/^(Must|Prefers): /, "")}</span>
              {p.said && <q className="cl-quote">{p.said}</q>}
              <span className="sub">{p.stale ? `said ${p.as_of}: ask again` : `said ${p.as_of}`}</span>
              <form action={rejectClaim.bind(null, p.claim_id, path, "outdated")}>
                <button className="btn small ghost" title="No longer what they want">Remove</button>
              </form>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function AddCall({ action }: { action: (s: { error?: string; message?: string }, f: FormData) => Promise<{ error?: string; message?: string }> }) {
  return (
    <section className="panel">
      <h3>Add a call transcript</h3>
      <p className="sub">From Zoom, Teams, Meet or a notetaker: paste the text or choose the file (.txt, .vtt, .srt, .docx). It is kept as a document of theirs.</p>
      <TranscriptForm action={action} />
    </section>
  );
}
