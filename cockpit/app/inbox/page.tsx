import Link from "next/link";
import { approveClaim, correctContact, rejectClaim, resolveDecision } from "@/app/actions";
import { Snippet } from "@/components/Claim";
import { ContactFix } from "@/components/ContactFix";
import { api, type InboxItem, type JobSummary, type Side } from "@/lib/api";
import { summary } from "@/lib/format";

export const metadata = { title: "Inbox" };

const KIND: Record<InboxItem["kind"], string> = {
  ocr_contact: "Confirm a contact",
  identity_note: "Who is this?",
  revision_diff: "A source disagrees with what we believe",
  duplicate_stint: "Same job, or two?",
  contradiction: "These cannot both be true",
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
          <ContactFix kind={item.claim.payload.kind} action={correctContact.bind(null, item.subject.id, item.claim.claim_id, path)} />
          <div className="row" style={{ marginTop: 8 }}>
            <form action={approveClaim.bind(null, item.claim.claim_id, path)}><button className="btn small">It is right: approve</button></form>
            <form action={rejectClaim.bind(null, item.claim.claim_id, path, "wrong")}><button className="btn small ghost">Not theirs: reject</button></form>
          </div>
        </>
      )}

      {item.kind === "identity_note" && (
        <>
          <p>{item.context?.reason}.</p>
          {item.context?.candidate_ids?.length > 0 && (
            <p>Possibly: {item.context!.candidate_ids.map((cid: string) => <Link key={cid} href={`/people/${cid}`} style={{ marginRight: 8 }}>{cid.slice(0, 8)}</Link>)}</p>
          )}
          <p className="sub">Kept as a separate person. A wrong merge is worse than a duplicate.</p>
          <form action={act("acknowledge")}><button className="btn small">Understood</button></form>
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
  const { job, band = "priority" } = await searchParams;
  const qs = new URLSearchParams();
  if (job) qs.set("job_id", job);
  qs.set("band", band);
  const [items, jobs] = await Promise.all([api<InboxItem[]>(`/v1/inbox?${qs}`), api<JobSummary[]>("/v1/jobs")]);
  const jobName = jobs.find((j) => j.id === job)?.title;
  const path = `/inbox?${new URLSearchParams({ ...(job ? { job } : {}), band })}`;
  const link = (b: string) => `/inbox?${new URLSearchParams({ ...(job ? { job } : {}), band: b })}`;

  return (
    <>
      <h1>Inbox{jobName ? `: ${jobName}` : ""}</h1>
      <p className="sub">Only what the system may not decide itself. Identity and contact questions first, then oldest first.</p>
      <nav className="tabs">
        <Link href={link("priority")} aria-current={band === "priority" ? "page" : undefined}>Priority people</Link>
        <Link href={link("all")} aria-current={band === "all" ? "page" : undefined}>Everyone</Link>
        {job && <Link href="/inbox?band=all">All jobs</Link>}
      </nav>
      {!job && band === "priority" && <p className="sub">Pick a job to see its priority people, or choose Everyone.</p>}
      {items.length === 0 ? <p className="empty">Nothing waiting.</p> : items.map((i) => <Card key={i.id} item={i} path={path} />)}
    </>
  );
}
