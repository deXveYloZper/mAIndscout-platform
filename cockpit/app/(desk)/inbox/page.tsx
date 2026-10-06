import Link from "next/link";
import { addFact, approveClaim, correctContact, mergePeople, rejectClaim, resolveDecision } from "@/app/actions";
import { Snippet } from "@/components/Claim";
import { ContactFix } from "@/components/ContactFix";
import { FactForm } from "@/components/FactForm";
import { api, type CallReview, type InboxItem, type JobSummary, type Side } from "@/lib/api";
import { summary } from "@/lib/format";

export const metadata = { title: "Inbox" };

const KIND: Record<InboxItem["kind"], string> = {
  ocr_contact: "Confirm a contact",
  identity_note: "Who is this?",
  revision_diff: "A source disagrees with what we believe",
  duplicate_stint: "Same job, or two?",
  contradiction: "These cannot both be true",
  company_same: "Same company?",
};

function SideBox({ side, title }: { side: Side; title: string }) {
  return (
    <div className="side">
      <h3>{title}</h3>
      <p>{summary(side)}</p>
      <Snippet ev={{ type: "document_span", document_id: null, filename: side.filename, page: side.page, snippet: side.snippet, note: null, observed_as_of: null }} />
    </div>
  );
}

function View({ view, changed }: { view: Record<string, any>; changed: string[] }) {
  return (
    <ul>
      {Object.entries(view).map(([k, v]) => (
        <li key={k} className={changed.includes(k) ? "changed" : undefined}>
          {k}: {typeof v === "object" ? JSON.stringify(v) : String(v)}
        </li>
      ))}
    </ul>
  );
}

function Card({ item, path }: { item: InboxItem; path: string }) {
  const act = (action: string, claimId: string | null = null) => resolveDecision.bind(null, item.id, action, claimId, path);
  return (
    <article className={`card${item.blocking ? " blocking" : ""}`}>
      <header>
        <span className="kind">{KIND[item.kind]}</span>
        <Link href={`/people/${item.subject.id}`}>{item.subject.name ?? "name not read"}</Link>
      </header>

      {item.kind === "ocr_contact" && item.claim && (
        <>
          <p>The file&apos;s text says <strong>{item.claim.payload.value}</strong>. {item.note ?? "It may be a text-layer error."}</p>
          <p className="sub">It will not be used to match people or send mail until you confirm it.</p>
          <Snippet ev={{ type: "document_span", document_id: null, filename: item.claim.filename, page: item.claim.page, snippet: item.claim.snippet, note: null, observed_as_of: null }} />
          <div className="row decide">
            <form action={approveClaim.bind(null, item.claim.claim_id, path)}><button className="btn small primary">It is right: approve</button></form>
            <form action={rejectClaim.bind(null, item.claim.claim_id, path, "wrong")}><button className="btn small">Not theirs: reject</button></form>
          </div>
          <details className="fix">
            <summary>Or correct it</summary>
            <ContactFix kind={item.claim.payload.kind} action={correctContact.bind(null, item.subject.id, item.claim.claim_id, path)} />
          </details>
        </>
      )}

      {item.kind === "identity_note" && (
        <>
          <p>{item.context?.reason ? item.context.reason[0].toUpperCase() + item.context.reason.slice(1) : ""}.</p>
          {item.possibly && item.possibly.length > 0 && (
            <p>
              Possibly the same as:{" "}
              {item.possibly.map((p) => <Link key={p.id} href={`/people/${p.id}`} style={{ marginRight: 10 }}>{p.name ?? "name not read"}</Link>)}
            </p>
          )}
          <p className="sub">
            Kept as a separate person until you say: a wrong merge is worse than a duplicate.
            {item.document_id && <> <a href={`/files/${item.document_id}`} target="_blank" rel="noreferrer">Open the CV</a>.</>}
          </p>
          {item.possibly && item.possibly.length === 1 && (
            <form action={mergePeople.bind(null, item.subject.id, item.possibly[0].id, path)} className="row" style={{ marginTop: 8 }}>
              <button className="btn small primary">Same person: merge</button>
              <span className="sub">Everything moves onto one record (the older one). It can be undone from their page.</span>
            </form>
          )}
          {!item.subject.name && (
            <FactForm action={addFact.bind(null, item.subject.id, path, null, item.id)} kinds={["name"]} label="Save name" />
          )}
          <form action={act(item.possibly && item.possibly.length ? "different" : "acknowledge")} style={{ marginTop: 8 }}>
            <button className="btn small">{item.possibly && item.possibly.length ? "Different people" : "Understood"}</button>
          </form>
        </>
      )}

      {item.kind === "revision_diff" && (
        <>
          <div className="two">
            <div className="side"><h3>Official now</h3><View view={item.old_view ?? {}} changed={item.changed_paths ?? []} /></div>
            <div className="side"><h3>New source says</h3><View view={item.new_view ?? {}} changed={item.changed_paths ?? []} /></div>
          </div>
          <div className="row" style={{ marginTop: 10 }}>
            <form action={act("keep_old")}><button className="btn">Keep official</button></form>
            <form action={act("accept_new")}><button className="btn primary">Accept new</button></form>
          </div>
        </>
      )}

      {item.kind === "duplicate_stint" && item.left && item.right && (
        <>
          <div className="two"><SideBox side={item.left} title="Entry A" /><SideBox side={item.right} title="Entry B" /></div>
          <div className="row" style={{ marginTop: 10 }}>
            <form action={act("same")}><button className="btn">Same job</button></form>
            <form action={act("two")}><button className="btn">Two jobs</button></form>
          </div>
        </>
      )}

      {item.kind === "company_same" && item.context && (
        <>
          <p>
            A CV names <strong>{item.context.new.name}</strong>. The desk already knows <strong>{item.context.existing.name}</strong>. Are they the same company?
          </p>
          <p className="sub">Merging links everyone who worked at either. A wrong merge mixes two companies&apos; people, so only merge when you are sure.</p>
          <div className="row" style={{ marginTop: 10 }}>
            <form action={act("same")}><button className="btn">Same company</button></form>
            <form action={act("different")}><button className="btn">Different companies</button></form>
          </div>
        </>
      )}

      {item.kind === "contradiction" && item.left && item.right && (
        <>
          <div className="two"><SideBox side={item.left} title="Option A" /><SideBox side={item.right} title="Option B" /></div>
          <div className="row" style={{ marginTop: 10 }}>
            <form action={act("pick", item.left.claim_id)}><button className="btn">A is true</button></form>
            <form action={act("pick", item.right.claim_id)}><button className="btn">B is true</button></form>
          </div>
        </>
      )}
    </article>
  );
}

export default async function Inbox({ searchParams }: { searchParams: Promise<{ job?: string; band?: string }> }) {
  const params = await searchParams;
  const job = params.job;
  // With a job open, the default is its priority people (the handoff rule). Without one, show everything.
  const band = job ? params.band ?? "priority" : "all";
  const qs = new URLSearchParams();
  if (job) qs.set("job_id", job);
  qs.set("band", band);
  const [items, jobs, calls] = await Promise.all([api<InboxItem[]>(`/v1/inbox?${qs}`), api<JobSummary[]>("/v1/jobs"),
    job ? Promise.resolve([] as CallReview[]) : api<CallReview[]>("/v1/call-reviews")]);
  const jobName = jobs.find((j) => j.id === job)?.title;
  const path = "/inbox"; // revalidation works on the path; the query string is kept by the browser
  const link = (b: string) => `/inbox?${new URLSearchParams({ ...(job ? { job } : {}), band: b })}`;

  return (
    <>
      <h1>Inbox{jobName ? `: ${jobName}` : ": all jobs"}</h1>
      <p className="sub">Only what the system may not decide itself. Identity and contact questions first, then oldest first.</p>
      <form className="row" action="/inbox" method="get">
        <select name="job" defaultValue={job ?? ""} aria-label="Job" className="jobpick">
          <option value="">All jobs, everyone</option>
          {jobs.map((j) => <option key={j.id} value={j.id}>{j.title}</option>)}
        </select>
        <button className="btn small">Show</button>
      </form>
      {job && (
        <nav className="tabs">
          <Link href={link("priority")} aria-current={band === "priority" ? "page" : undefined}>Priority people</Link>
          <Link href={link("all")} aria-current={band === "all" ? "page" : undefined}>Everyone on this job</Link>
        </nav>
      )}
      {calls.length > 0 && (
        <section className="panel">
          <h3>Calls to approve ({calls.length})</h3>
          <ul className="people">
            {calls.map((c) => (
              <li key={c.id}>
                <Link href={`/people/${c.candidate_id}`}>{c.person ?? "Name not read"}</Link>
                <span className="sub">
                  {c.status === "reading" ? "reading the call…" : c.status === "failed" ? "could not be read: try again"
                    : `${c.sections.reduce((n, s) => n + s.lines.length, 0)} lines to approve`}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
      {items.length === 0 && calls.length === 0 ? <p className="empty">Nothing waiting.</p> : items.length === 0 ? null : items.map((i) => <Card key={i.id} item={i} path={path} />)}
    </>
  );
}
