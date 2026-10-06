import { Link2, Mail, Phone } from "lucide-react";
import { answerBrief, briefAsked, briefDismiss } from "@/app/actions";

export type BriefItem = { id: string; scope: "person" | "job"; kind: string; question: string; why: string | null; status: string;
  outcome: string | null; answer: string | null; answered_by: string | null };
export type Contact = { kind: "phone" | "email" | "linkedin"; value: string; approved: boolean; unconfirmed: boolean };

const OUTCOME: Record<string, string> = { confirmed: "Confirmed", not_met: "Not met", noted: "Noted" };
const ICON = { phone: Phone, email: Mail, linkedin: Link2 };

function href(c: Contact): string {
  if (c.kind === "phone") return `tel:${c.value.replace(/[^\d+]/g, "")}`;
  if (c.kind === "email") return `mailto:${c.value}`;
  return c.value.startsWith("http") ? c.value : `https://${c.value.replace(/^\/+/, "")}`;
}

/** How to reach them, at the top of the Brief: one click to call, write or open LinkedIn. */
export function ContactCard({ contacts }: { contacts: Contact[] }) {
  if (!contacts.length) {
    return <div className="contactcard empty-contacts"><span className="sub">No phone, email or LinkedIn on file. Add one on their Facts tab.</span></div>;
  }
  return (
    <div className="contactcard" aria-label="How to reach them">
      {contacts.map((c) => {
        const Icon = ICON[c.kind];
        return (
          <a key={`${c.kind}-${c.value}`} href={href(c)} className={`contactchip ${c.unconfirmed ? "unconfirmed" : ""}`}
            target={c.kind === "linkedin" ? "_blank" : undefined} rel={c.kind === "linkedin" ? "noreferrer" : undefined}
            title={c.unconfirmed ? "Unconfirmed: the file disagrees with itself. Check it on the call." : c.approved ? "Approved" : "From the CV, not yet approved"}>
            <Icon aria-hidden="true" />
            <span>{c.kind === "linkedin" ? c.value.replace(/^https?:\/\/(www\.)?/, "") : c.value}</span>
            {c.unconfirmed && <em>check</em>}
          </a>
        );
      })}
    </div>
  );
}

function Open({ item, path }: { item: BriefItem; path: string }) {
  return (
    <li className={`brief-item ${item.status}`}>
      <div className="q">{item.question}</div>
      {item.why && <div className="why-line">Why: {item.why}</div>}
      <form action={answerBrief.bind(null, item.id, path)} className="row answer">
        <input name="answer" aria-label={`Answer: ${item.question}`} placeholder="what they said" className="grow" />
        <button className="btn small" name="outcome" value="confirmed">Confirmed</button>
        <button className="btn small" name="outcome" value="not_met">Not met</button>
        <button className="btn small ghost" name="outcome" value="noted">Note it</button>
      </form>
      <div className="row">
        {item.status === "open" && <form action={briefAsked.bind(null, item.id, path)}><button className="btn small ghost">Asked, waiting</button></form>}
        <form action={briefDismiss.bind(null, item.id, path)}><button className="btn small ghost">Not needed</button></form>
        {item.status === "asked" && <span className="sub">asked, waiting for the answer</span>}
      </div>
    </li>
  );
}

/** The questions, grouped: still to ask (person, then job), answered, and those no longer needed. */
export function BriefLists({ items, path, scopes }: { items: BriefItem[]; path: string; scopes: ("person" | "job")[] }) {
  const live = items.filter((i) => i.status === "open" || i.status === "asked");
  const done = items.filter((i) => i.status === "answered");
  const gone = items.filter((i) => i.status === "dismissed" || i.status === "expired");
  return (
    <>
      {scopes.map((scope) => {
        const mine = live.filter((i) => i.scope === scope);
        return (
          <section key={scope} className="panel">
            <h3>{scope === "person" ? "About the person (once, for every job)" : "For this job"} ({mine.length})</h3>
            {mine.length === 0 ? <p className="empty">Nothing left to ask.</p> : <ul className="brief">{mine.map((i) => <Open key={i.id} item={i} path={path} />)}</ul>}
          </section>
        );
      })}
      {done.length > 0 && (
        <section className="panel">
          <h3>Answered ({done.length})</h3>
          <ul className="brief">
            {done.map((i) => (
              <li key={i.id} className="brief-item answered">
                <div className="q">{i.question}</div>
                <div><strong>{OUTCOME[i.outcome ?? ""] ?? i.outcome}</strong>{i.answer ? `: ${i.answer}` : ""} <span className="sub">({i.answered_by}{i.scope === "person" ? ", counts for every job" : ""})</span></div>
              </li>
            ))}
          </ul>
        </section>
      )}
      {gone.length > 0 && (
        <details className="band">
          <summary>Not needed or no longer needed ({gone.length})</summary>
          <ul className="brief">
            {gone.map((i) => <li key={i.id} className="brief-item gone"><span className="q">{i.question}</span> <span className="sub">({i.status === "expired" ? "the reason went away" : "marked not needed"})</span></li>)}
          </ul>
        </details>
      )}
    </>
  );
}
