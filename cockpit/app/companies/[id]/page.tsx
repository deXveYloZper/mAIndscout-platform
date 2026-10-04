import Link from "next/link";
import { addContact, logActivity, removeContact, researchCompany } from "@/app/actions";
import { AddContact } from "@/components/AddContact";
import { Dates, LogActivity, Timeline, type TimelineRow } from "@/components/Relationship";
import { apiOr404 } from "@/lib/api";
import { period } from "@/lib/format";

export const metadata = { title: "Company" };

type Source = { url: string | null; quote: string | null; authority: string; seen: string | null };
type Fact = { id: string; claim_type: string; status: string; payload: Record<string, any>; flags: Record<string, unknown>; sources: Source[] };

type CompanyPage = {
  id: string;
  name: string;
  website: string | null;
  research_status: string | null;
  researched_at: string | null;
  facts: Fact[];
  aliases: string[];
  people_count: number;
  people: { candidate_id: string; name: string | null; current: boolean;
    roles: { title: string | null; valid_from: string | null; valid_to: string | null; current: boolean }[] }[];
  jobs: { id: string; title: string }[];
  contacts: { id: string; name: string; role: string | null; email: string | null; phone: string | null; linkedin: string | null;
    last_contacted: string | null }[];
  timeline: TimelineRow[];
  last_contacted: string | null;
};

const STAGE: Record<string, string> = {
  pre_seed: "Pre-seed", seed: "Seed", series_a: "Series A", series_b: "Series B", series_c: "Series C",
  series_d: "Series D", series_e_plus: "Series E or later", growth: "Growth", grant: "Grant", debt: "Debt", ipo: "IPO",
  acquisition: "Acquired", other: "Round",
};
const ORDER = ["CompanyDomainClaim", "CompanyTypeClaim", "CompanyFoundedClaim", "FundingRoundClaim", "TeamSizeClaim",
  "CompanyStatusClaim", "CompanyLocationClaim"];

function describe(f: Fact): [string, string] {
  const p = f.payload;
  switch (f.claim_type) {
    case "CompanyDomainClaim": return ["Works in", (p.domains ?? []).join(", ")];
    case "CompanyTypeClaim": return ["Kind", String(p.type).replace(/_/g, " ")];
    case "CompanyFoundedClaim": return ["Founded", p.founded];
    case "FundingRoundClaim":
      return ["Funding", [STAGE[p.stage] ?? p.stage, p.amount_raw, p.date && `(${p.date})`,
        p.investors?.length ? `led by or with ${p.investors.join(", ")}` : null].filter(Boolean).join(" ")];
    case "TeamSizeClaim": return ["Team size", `${p.raw}${p.as_of ? ` (as of ${p.as_of})` : ""}`];
    case "CompanyStatusClaim": return ["Status", String(p.status).replace(/_/g, " ")];
    case "CompanyLocationClaim": return ["Head office", p.hq_raw];
    default: return [f.claim_type, JSON.stringify(p)];
  }
}

const AUTHORITY: Record<string, string> = {
  verified_primary: "official register", employer_authored: "the company itself", web_inference: "a web page",
};

function researchLine(c: CompanyPage): string {
  if (!c.researched_at) return "Not researched yet. Research runs on its own when someone on the desk worked here recently.";
  const when = c.researched_at.slice(0, 10);
  if (c.research_status === "not_identified") return `Researched ${when}: no public record found that is surely this company.`;
  if (c.research_status === "failed") return `Research on ${when} did not finish. It will be tried again.`;
  return `Researched ${when}. Facts are shared public knowledge, each with the page it came from.`;
}

export default async function Company({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const c = await apiOr404<CompanyPage>(`/v1/companies/${id}`);
  const facts = [...c.facts].sort((a, b) => ORDER.indexOf(a.claim_type) - ORDER.indexOf(b.claim_type));
  return (
    <>
      <h1>{c.name}</h1>
      <p className="sub">
        We know {c.people_count} {c.people_count === 1 ? "person" : "people"} who worked here.
        {c.aliases.length > 1 && <> Also written as: {c.aliases.join(", ")}.</>}
        {c.website && <> <a href={c.website} target="_blank" rel="noreferrer">{c.website}</a></>}
      </p>

      <section className="panel relationship">
        <h3>Relationship</h3>
        <Dates lastContacted={c.last_contacted} lastVerified={c.researched_at} verifiedLabel="Public facts researched" />
        <h4>People we know there</h4>
        {c.contacts.length === 0 ? <p className="empty">No contacts yet.</p> : (
          <ul className="contacts">
            {c.contacts.map((k) => (
              <li key={k.id}>
                <strong>{k.name}</strong>{k.role ? ` · ${k.role}` : ""}
                <span className="sub">
                  {[k.email, k.phone].filter(Boolean).map((x) => ` · ${x}`)}
                  {k.linkedin && <> · <a href={k.linkedin.startsWith("http") ? k.linkedin : `https://${k.linkedin}`} target="_blank" rel="noreferrer">LinkedIn</a></>}
                  {" "}· last contacted {k.last_contacted ? new Date(k.last_contacted).toISOString().slice(0, 10) : "never"}
                </span>
                <form action={removeContact.bind(null, k.id, `/companies/${c.id}`)} className="inline">
                  <button className="btn small ghost" aria-label={`Forget contact ${k.name}`}>forget</button>
                </form>
              </li>
            ))}
          </ul>
        )}
        <AddContact action={addContact.bind(null, c.id, `/companies/${c.id}`)} />
        <h4>Log a call, email or meeting</h4>
        <LogActivity action={logActivity.bind(null, "companies", c.id, `/companies/${c.id}`)} jobs={c.jobs}
          contacts={c.contacts.map((k) => ({ id: k.id, name: k.name }))} />
        <details className="band">
          <summary>Timeline ({c.timeline.length})</summary>
          <Timeline rows={c.timeline} path={`/companies/${c.id}`} />
        </details>
      </section>

      <h2>What we know about the company</h2>
      <div className="research-bar">
        <span className="hint" style={{ width: "auto", marginTop: 0 }}>{researchLine(c)}</span>
        <form action={researchCompany.bind(null, c.id)}><button className="btn small">Research now</button></form>
      </div>
      {facts.length > 0 && (
        <ul className="facts">
          {facts.map((f) => {
            const [label, value] = describe(f);
            const src = f.sources[0];
            return (
              <li key={f.id}>
                <span className="label">{label}</span> {value}
                {f.status === "proposed" && <span className="warn">not yet checked by a person</span>}
                {"single_source_web" in f.flags && <span className="warn">one web source only</span>}
                {src?.url && (
                  <span className="src">
                    From {AUTHORITY[src.authority] ?? src.authority}: <a href={src.url} target="_blank" rel="noreferrer">{src.url}</a>
                    {src.quote && <> · <q>{src.quote}</q></>}
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {c.jobs.length > 0 && (
        <>
          <h2>Jobs from this company</h2>
          <ul className="reqs">{c.jobs.map((j) => <li key={j.id}><Link href={`/jobs/${j.id}`}>{j.title}</Link></li>)}</ul>
        </>
      )}

      <h2>People on the desk who worked here</h2>
      {c.people.length === 0 ? <p className="empty">Nobody yet.</p> : (
        <ul className="people">
          {c.people.map((p) => (
            <li key={p.candidate_id}>
              <Link href={`/people/${p.candidate_id}`}>{p.name ?? "name not read"}{p.current ? " (current)" : ""}</Link>
              <span className="roles">
                {p.roles.map((r, i) => (
                  <span key={i} className="role">{r.title} · {period({ valid_from: r.valid_from, valid_to: r.valid_to, temporal_precision: "month" })}</span>
                ))}
              </span>
              <span />
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
