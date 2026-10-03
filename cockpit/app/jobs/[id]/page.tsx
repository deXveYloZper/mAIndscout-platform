import Link from "next/link";
import { overrideBand, setJobCountries, startCampaign } from "@/app/actions";
import { CountriesForm } from "@/components/CountriesForm";
import { FindMore } from "@/components/FindMore";
import { Snippet } from "@/components/Claim";
import { MultiUpload } from "@/components/MultiUpload";
import { api, apiOr404, type Band, type InboxItem, type JobPage, type PersonOnJob } from "@/lib/api";
import { BAND_LABEL, countryName, reasonWords, STATE_LABEL } from "@/lib/format";

export const metadata = { title: "Job" };

type Campaign = { id: string; source: string; query: { tokens: string[] }; cap: number; spent: number; added: number;
  priority_added: number; status: string; stop_reason: string | null; created_at: string };
type CampaignList = { priority: number; default_target: number; campaigns: Campaign[] };

const STOP_WORDS: Record<string, string> = { cap: "stopped at cap", target_reached: "target reached", human: "stopped by hand" };

const REQUIREMENT_GROUPS: [string, string][] = [
  ["skill", "Skills"],
  ["seniority", "Experience"],
  ["education", "Education"],
  ["language", "Languages"],
  ["authorization", "Authorisation"],
  ["location", "Location"],
  ["other", "Other"],
];

const FACET_LABEL: Record<string, string> = {
  residence: "Must live in or work from",
  visa_sponsorship: "Visa sponsorship",
  relocation_assistance: "Relocation assistance",
};

function facetValue(m: { facet: string; countries?: string[] | null; offered?: boolean | null }): string {
  if (m.facet === "residence") return (m.countries ?? []).map(countryName).join(", ") || "not stated";
  return m.offered === true ? "offered" : m.offered === false ? "not offered" : "not stated";
}

function People({ jobId, people }: { jobId: string; people: PersonOnJob[] }) {
  if (!people.length) return <p className="empty">Nobody here.</p>;
  return (
    <ul className="people">
      {people.map((p) => (
        <li key={p.candidate_id} className={p.state === "we_passed" ? "passed" : undefined}>
          <span>
            <Link href={`/jobs/${jobId}/people/${p.candidate_id}`}>{p.name ?? "name not read"}</Link>
            {p.state && p.state !== "new" && <span className={`statetag ${p.state}`}>{STATE_LABEL[p.state]}</span>}
            {p.coverage && !p.coverage.met && p.coverage.applicable > 0 && (
              <span className="thintag" title={p.coverage.words}>thin</span>
            )}
            {p.open_decisions > 0 && <span className="pill">{p.open_decisions} to review</span>}
          </span>
          <span className="reason">
            {reasonWords(p.reason)}
            {p.gaps && (
              <span className="mini">
                {" "}· {p.gaps.evidence} evidence · {p.gaps.missing} missing{p.gaps.conflict ? ` · ${p.gaps.conflict} conflict` : ""} · {p.gaps.question} to ask
              </span>
            )}
          </span>
          <form action={overrideBand.bind(null, jobId, p.candidate_id)} className="row">
            <select name="band" defaultValue={p.band} aria-label="Band">
              {(Object.keys(BAND_LABEL) as Band[]).map((b) => <option key={b} value={b}>{BAND_LABEL[b]}</option>)}
            </select>
            <input name="reason" placeholder="why" aria-label="Reason for changing the band" size={10} />
            <button className="btn small">Set</button>
          </form>
        </li>
      ))}
    </ul>
  );
}

export default async function Job({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [job, waiting, sourcing] = await Promise.all([
    apiOr404<JobPage>(`/v1/jobs/${id}`),
    api<InboxItem[]>(`/v1/inbox?job_id=${id}&band=priority`),
    api<CampaignList>(`/v1/jobs/${id}/campaigns`),
  ]);
  const thin = sourcing.priority < sourcing.default_target;
  const tokens = job.requirements
    .filter((r) => r.payload.category === "skill" && r.payload.distinctive && r.payload.normalized_token)
    .map((r) => r.payload.normalized_token)
    .join(", ");
  const places = job.requirements.filter((r) => r.payload.category === "location" && r.payload.strength === "unknown" && !r.payload.mobility);
  const mobility = job.requirements.filter((r) => r.payload.mobility);
  const must = job.requirements.filter((r) => r.payload.category !== "process" && !places.includes(r) && !mobility.includes(r));
  const groups = REQUIREMENT_GROUPS.map(([cat, title]) => [title, must.filter((r) => r.payload.category === cat)] as const)
    .filter(([, items]) => items.length > 0);
  const dates = job.requirements.filter((r) => r.payload.category === "process");

  return (
    <>
      <h1>{job.title}</h1>
      <p className="sub">
        {job.hiring_company ?? "Hiring company not stated"} · {job.people.priority.length} priority · {job.people.review_later.length} later · {job.people.do_not_submit.length} do not submit ·{" "}
        <Link href={`/inbox?job=${job.id}`}>{waiting.length ? `${waiting.length} to review` : "inbox clear"}</Link>
      </p>
      {places.length > 0 && <p className="where">Where: {places.map((p) => p.payload.text_raw).join(" · ")}</p>}
      {job.process_stale && (
        <p className="warn">This posting&apos;s own process dates have passed. Confirm it is still open before submitting anyone.</p>
      )}

      <section className="panel">
        <h3>Drop CVs onto this job</h3>
        <MultiUpload jobId={job.id} />
      </section>

      {(thin || sourcing.campaigns.length > 0) && (
        <section className="panel">
          <h3>Find more people {thin ? `(priority is thin: ${sourcing.priority} of ${sourcing.default_target})` : ""}</h3>
          {thin ? <FindMore action={startCampaign.bind(null, job.id)} tokens={tokens} /> : <p className="sub">Priority has {sourcing.priority}; sourcing is for a thin queue.</p>}
          <p className="hint">Searches the desk&apos;s own people only. Everyone found is banded by the same rules as an uploaded CV; being found never changes a band.</p>
          {sourcing.campaigns.length > 0 && (
            <ul className="campaigns">
              {sourcing.campaigns.map((c) => (
                <li key={c.id}>
                  <span className="sub">{c.created_at.slice(0, 16).replace("T", " ")}</span> · desk · {c.query.tokens.join(", ")} ·
                  looked at {c.spent}/{c.cap} · added {c.added} ({c.priority_added} priority) · {c.status === "exhausted" ? "no more matches" : STOP_WORDS[c.stop_reason ?? ""] ?? c.status}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      <h2>{BAND_LABEL.priority} ({job.people.priority.length})</h2>
      <People jobId={job.id} people={job.people.priority} />

      <details className="band">
        <summary>{BAND_LABEL.review_later} ({job.people.review_later.length})</summary>
        <People jobId={job.id} people={job.people.review_later} />
      </details>
      <details className="band">
        <summary>{BAND_LABEL.do_not_submit} ({job.people.do_not_submit.length})</summary>
        <People jobId={job.id} people={job.people.do_not_submit} />
      </details>
      <details className="band">
        <summary>Archived: outside coverage ({job.archived.length})</summary>
        <p className="hint">
          They live or work outside the countries this desk and this job accept, so nothing more is spent on them. Open one to bring them back.
        </p>
        {job.archived.length === 0 ? <p className="empty">Nobody.</p> : (
          <ul className="people">
            {job.archived.map((a) => (
              <li key={a.candidate_id}>
                <Link href={`/people/${a.candidate_id}`}>{a.name ?? "name not read"}</Link>
                <span className="sub">{a.reason}</span>
                <span />
              </li>
            ))}
          </ul>
        )}
      </details>

      <section className="panel">
        <h3>Countries this job accepts</h3>
        <p className="sub">
          The desk covers the EU / EEA, the UK, Switzerland, the US and Canada.
          {job.coverage.from_ad.length > 0 && <> The ad also accepts: {job.coverage.from_ad.map((c) => job.coverage.names[c] ?? c).join(", ")}.</>}
        </p>
        <CountriesForm action={setJobCountries.bind(null, job.id)} opened={job.coverage.opened.map((c) => job.coverage.names[c] ?? c).join(", ")} />
        <p className="hint">Decided by where people live and work now, never by nationality or where they are from.</p>
      </section>

      {mobility.length > 0 && (
        <>
          <h2>Mobility (three separate facts)</h2>
          <ul className="reqs">
            {mobility.map((r) => (
              <li key={r.id}>
                <strong>{FACET_LABEL[r.payload.mobility.facet]}:</strong> {facetValue(r.payload.mobility)}
                <details><summary>source</summary><Snippet ev={r.evidence[0]} /></details>
              </li>
            ))}
          </ul>
          <p className="sub">Where someone lives never puts them in Do not submit by itself; it becomes a question to ask.</p>
        </>
      )}

      <h2>Requirements</h2>
      {groups.map(([title, items]) => (
        <section key={title}>
          <h3 className="group">{title}</h3>
          <ul className="reqs">
            {items.map((r) => (
              <li key={r.id}>
                <span className="tag">{r.payload.strength}</span>
                {r.payload.distinctive && <span className="tag key" title="Zero evidence of this puts a person in Do not submit">decides the band</span>}
                {r.payload.min_years != null && <span className="tag">{r.payload.min_years}+ years</span>}
                {r.payload.education_level && <span className="tag">{r.payload.education_level}</span>}
                {r.payload.text_raw}
                <details><summary>source</summary><Snippet ev={r.evidence[0]} /></details>
              </li>
            ))}
          </ul>
        </section>
      ))}
      {dates.length > 0 && (
        <>
          <h2>Process dates</h2>
          <ul className="reqs">
            {dates.map((d) => (
              <li key={d.id}>
                {d.payload.normalized_token} · {d.payload.text_raw}
                {d.flags.job_process_stale && <span className="pill">passed</span>}
              </li>
            ))}
          </ul>
        </>
      )}
      {job.source_document_id && <p className="sub"><a href={`/files/${job.source_document_id}`} target="_blank" rel="noreferrer">Open the original ad</a></p>}
    </>
  );
}
