import Link from "next/link";
import { answerBrief, briefAsked, briefDismiss } from "@/app/actions";
import { api, apiOr404 } from "@/lib/api";

export const metadata = { title: "Brief" };

type Item = { id: string; scope: "person" | "job"; kind: string; question: string; why: string | null; status: string;
  outcome: string | null; answer: string | null; answered_by: string | null };
type Brief = { available: boolean; reason?: string; items: Item[];
  header?: { summary: string | null; reading: string | null; band: string; tier: string | null; why: string | null } };
type GapHead = { job: { id: string; title: string }; person: { id: string; name: string | null } };

const OUTCOME: Record<string, string> = { confirmed: "Confirmed", not_met: "Not met", noted: "Noted" };

function Open({ item, path }: { item: Item; path: string }) {
  return (
    <li className={`brief-item ${item.status}`}>
      <div className="q">{item.question}</div>
      {item.why && <div className="why-line">Why: {item.why}</div>}
      <form action={answerBrief.bind(null, item.id, path)} className="row answer">
        <input name="answer" aria-label={`Answer: ${item.question}`} placeholder="what they said" size={34} />
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

export default async function BriefPage({ params, searchParams }: { params: Promise<{ id: string; cid: string }>;
  searchParams: Promise<{ force?: string }> }) {
  const { id, cid } = await params;
  const { force } = await searchParams;
  const [head, brief] = await Promise.all([
    apiOr404<GapHead>(`/v1/jobs/${id}/people/${cid}/gaps`),
    api<Brief>(`/v1/jobs/${id}/people/${cid}/brief${force ? "?force=true" : ""}`),
  ]);
  const path = `/jobs/${id}/people/${cid}/brief`;
  const live = brief.items.filter((i) => i.status === "open" || i.status === "asked");
  const done = brief.items.filter((i) => i.status === "answered");
  const gone = brief.items.filter((i) => i.status === "dismissed" || i.status === "expired");

  return (
    <>
      <p className="sub">
        <Link href={`/jobs/${id}`}>{head.job.title}</Link> · <Link href={`/jobs/${id}/people/${cid}`}>gap table</Link>
      </p>
      <h1>Brief: {head.person.name ?? "name not read"}</h1>
      {brief.header && (
        <div className="brief-head">
          {brief.header.summary && <div>{brief.header.summary}</div>}
          {brief.header.why && <div className="sub">On the call list because: {brief.header.why}</div>}
        </div>
      )}
      <p className="hint">What to ask on the call. Every answer you capture becomes an approved fact with you as the source, and the match is updated at once. Questions about the person are asked once and count for every job. Nothing here is ever sent to anyone.</p>
      {!brief.available ? (
        <section className="panel">
          <p>{brief.reason}</p>
          {!force && <Link className="btn small" href={`${path}?force=1`}>Make a Brief anyway</Link>}
        </section>
      ) : (
        <>
          {(["person", "job"] as const).map((scope) => {
            const items = live.filter((i) => i.scope === scope);
            return (
              <section key={scope}>
                <h2>{scope === "person" ? "About the person (once, for every job)" : "For this job"} ({items.length})</h2>
                {items.length === 0 ? <p className="empty">Nothing left to ask.</p> : (
                  <ul className="brief">{items.map((i) => <Open key={i.id} item={i} path={path} />)}</ul>
                )}
              </section>
            );
          })}
          {done.length > 0 && (
            <section>
              <h2>Answered ({done.length})</h2>
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
      )}
    </>
  );
}
