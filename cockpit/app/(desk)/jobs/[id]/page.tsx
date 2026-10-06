import Link from "next/link";
import { FileText, Inbox, MessageSquareText } from "lucide-react";
import { overrideBand, setJobCountries, startCampaign } from "@/app/actions";
import { CountriesForm } from "@/components/CountriesForm";
import { FindMore } from "@/components/FindMore";
import { HiringProfile } from "@/components/HiringProfile";
import { Snippet } from "@/components/Claim";
import { MultiUpload } from "@/components/MultiUpload";
import { api, apiOr404, type Band, type InboxItem, type JobPage, type PersonOnJob } from "@/lib/api";
import { BAND_LABEL, countryName, PIPELINE, reasonWords, STATE_LABEL, TIER_WORDS } from "@/lib/format";

export const metadata = { title: "Job" };

type Campaign = { id: string; source: string; query: { tokens?: string[]; words?: string[] }; cap: number; spent: number; added: number;
  priority_added: number; status: string; stop_reason: string | null; created_at: string };
type CampaignList = { priority: number; default_target: number; by_profile: string[] | null; campaigns: Campaign[] };

const STOP_WORDS: Record<string, string> = { cap: "stopped at cap", target_reached: "target reached", human: "stopped by hand" };
const FACET_LABEL: Record<string, string> = {
  residence: "Must live in or work from",
  visa_sponsorship: "Visa sponsorship",
  relocation_assistance: "Relocation assistance",
};
const BANDS: (Band | "archived")[] = ["priority", "review_later", "do_not_submit", "archived"];
const TABS: [string, string][] = [["people", "People"], ["profile", "Hiring profile"], ["find", "Find more"], ["countries", "Countries"]];

function facetValue(m: { facet: string; countries?: string[] | null; offered?: boolean | null }): string {
  if (m.facet === "residence") return (m.countries ?? []).map(countryName).join(", ") || "not stated";
  return m.offered === true ? "offered" : m.offered === false ? "not offered" : "not stated";
}

/** Evidence, questions, missing and conflicts as one bar: how well a person is known against this job, at a glance. */
function GapBar({ g }: { g: NonNullable<PersonOnJob["gaps"]> }) {
  const total = g.evidence + g.question + g.missing + g.conflict;
  if (!total) return null;
  const pct = (n: number) => `${(n / total) * 100}%`;
  return (
    <span className="gapbar" title={`${g.evidence} evidence · ${g.question} to ask · ${g.missing} missing${g.conflict ? ` · ${g.conflict} conflict` : ""}`}>
      <span className="track" aria-hidden="true">
        <span className="ev" style={{ width: pct(g.evidence) }} />
        <span className="q" style={{ width: pct(g.question) }} />
        <span className="cf" style={{ width: pct(g.conflict) }} />
      </span>
      <span className="mini">{g.evidence} evidence · {g.question} to ask · {g.missing} missing{g.conflict ? ` · ${g.conflict} conflict` : ""}</span>
    </span>
  );
}

function People({ jobId, people }: { jobId: string; people: PersonOnJob[] }) {
  if (!people.length) return <p className="empty">Nobody in this band.</p>;
  return (
    <ul className="people personcards stagger">
      {people.map((p) => (
        <li key={p.candidate_id} className={`personcard${p.state === "we_passed" ? " passed" : ""}`}>
          <div className="pc-main">
            <div className="pc-head">
              <Link href={`/jobs/${jobId}/people/${p.candidate_id}`} className="pc-name">{p.name ?? "name not read"}</Link>
              {p.state && p.state !== "new" && <span className={`statetag ${p.state}`}>{STATE_LABEL[p.state]}</span>}
              {p.match_tier && p.match_tier !== "unclear" && <span className={`tiertag ${p.match_tier}`}>{TIER_WORDS[p.match_tier]}</span>}
              {p.blocked && <span className="blocktag" title="The client said no to this person">blocked by client</span>}
              {p.coverage && !p.coverage.met && p.coverage.applicable > 0 && <span className="thintag" title={p.coverage.words}>thin</span>}
              {p.open_decisions > 0 && <span className="pill">{p.open_decisions} to review</span>}
            </div>
            <p className="reason">{reasonWords(p.reason)}</p>
            {p.gaps && <GapBar g={p.gaps} />}
          </div>
          <div className="pc-side">
            {p.band === "priority" && (
              <Link className="btn small" href={`/jobs/${jobId}/people/${p.candidate_id}/brief`}><MessageSquareText aria-hidden="true" />Brief</Link>
            )}
            <details className="move">
              <summary className="btn small ghost">Move</summary>
              <form action={overrideBand.bind(null, jobId, p.candidate_id)} className="movebox">
                <select name="band" defaultValue={p.band} aria-label="Band">
                  {(Object.keys(BAND_LABEL) as Band[]).map((b) => <option key={b} value={b}>{BAND_LABEL[b]}</option>)}
                </select>
                <input name="reason" placeholder="why (shown in the history)" aria-label="Reason for changing the band" />
                <button className="btn small primary">Set band</button>
              </form>
            </details>
          </div>
        </li>
      ))}
    </ul>
  );
}

export default async function Job({ params, searchParams }: {
  params: Promise<{ id: string }>; searchParams: Promise<{ band?: string; tab?: string }>;
}) {
  const [{ id }, sp] = await Promise.all([params, searchParams]);
  const [job, waiting, sourcing] = await Promise.all([
    apiOr404<JobPage>(`/v1/jobs/${id}`),
    api<InboxItem[]>(`/v1/inbox?job_id=${id}&band=priority`),
    api<CampaignList>(`/v1/jobs/${id}/campaigns`),
  ]);
  const band = (BANDS as string[]).includes(sp.band ?? "") ? (sp.band as Band | "archived") : "priority";
  const tab = TABS.some(([k]) => k === sp.tab) ? sp.tab! : "people";
  const thin = sourcing.priority < sourcing.default_target;
  const tokens = job.requirements
    .filter((r) => r.payload.category === "skill" && r.payload.distinctive && r.payload.normalized_token)
    .map((r) => r.payload.normalized_token)
    .join(", ");
  const places = job.requirements.filter((r) => r.payload.category === "location" && r.payload.strength === "unknown" && !r.payload.mobility);
  const mobility = job.requirements.filter((r) => r.payload.mobility);
  const must = job.requirements.filter((r) => r.payload.category !== "process" && !places.includes(r) && !mobility.includes(r));
  const dates = job.requirements.filter((r) => r.payload.category === "process");
  const count = (b: Band | "archived") => (b === "archived" ? job.archived.length : job.people[b].length);
  const href = (q: Record<string, string>) => `/jobs/${job.id}?${new URLSearchParams({ tab, band, ...q })}`;

  return (
    <>
      <div className="pagehead">
        <div>
          <p className="eyebrow">
            {job.hiring.company ? <Link href={`/companies/${job.hiring.company.id}`}>{job.hiring.company.name}</Link> : job.hiring_company ?? "Hiring company not stated"}
          </p>
          <h1>{job.title}</h1>
          {places.length > 0 && <p className="sub where">{places.map((p) => p.payload.text_raw).join(" · ")}</p>}
        </div>
        <div className="actions">
          <Link href={`/inbox?job=${job.id}`} className="btn"><Inbox aria-hidden="true" />{waiting.length ? `${waiting.length} to review` : "Inbox clear"}</Link>
          {job.source_document_id && (
            <a href={`/files/${job.source_document_id}`} target="_blank" rel="noreferrer" className="btn ghost"><FileText aria-hidden="true" />The ad</a>
          )}
        </div>
      </div>

      {job.rematching && <p className="warn" role="status">Re-matching everyone on this job after the change to its requirements. Bands update in a moment: reload to see them.</p>}
      {job.process_stale && <p className="warn">This posting&apos;s own process dates have passed. Confirm it is still open before submitting anyone.</p>}

      <div className="stats bandtiles">
        {BANDS.map((b) => (
          <Link key={b} href={href({ tab: "people", band: b })} className={`stat band-${b}`} aria-current={tab === "people" && band === b ? "true" : undefined}>
            <span className="label">{b === "archived" ? "Archived" : BAND_LABEL[b]}</span>
            <span className="value">{count(b)}</span>
          </Link>
        ))}
      </div>
      {Object.entries(job.stages).some(([k, n]) => k !== "new" && n) && (
        <p className="stages" aria-label="Pipeline">
          {PIPELINE.filter(([k]) => k !== "new" && job.stages[k]).map(([k, l]) => <span key={k} className={`statetag ${k}`}>{l} {job.stages[k]}</span>)}
        </p>
      )}

      <nav className="tabs" aria-label="Job sections">
        {TABS.map(([k, label]) => (
          <Link key={k} href={href({ tab: k })} aria-current={tab === k ? "page" : undefined}>
            {label}{k === "find" && thin ? <span className="pill">thin</span> : null}
          </Link>
        ))}
      </nav>

      {tab === "people" && (
        <>
          <details className="panel addcvs" open={job.people.priority.length + job.people.review_later.length + job.people.do_not_submit.length === 0}>
            <summary><strong>Drop CVs onto this job</strong></summary>
            <MultiUpload jobId={job.id} />
          </details>
          {band === "archived" ? (
            <>
              <p className="hint">They live or work outside the countries this desk and this job accept, so nothing more is spent on them. Open one to bring them back.</p>
              {job.archived.length === 0 ? <p className="empty">Nobody.</p> : (
                <ul className="people personcards">
                  {job.archived.map((a) => (
                    <li key={a.candidate_id} className="personcard">
                      <div className="pc-main">
                        <Link href={`/people/${a.candidate_id}`} className="pc-name">{a.name ?? "name not read"}</Link>
                        <p className="reason">{a.reason}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </>
          ) : (
            <People jobId={job.id} people={job.people[band]} />
          )}
        </>
      )}

      {tab === "profile" && (
        <>
          <HiringProfile job={job} requirements={must} />
          {mobility.length > 0 && (
            <section className="panel">
              <h3>Mobility (three separate facts)</h3>
              <ul className="reqs">
                {mobility.map((r) => (
                  <li key={r.id}>
                    <strong>{FACET_LABEL[r.payload.mobility.facet]}:</strong> {facetValue(r.payload.mobility)}
                    <details><summary>source</summary><Snippet ev={r.evidence[0]} /></details>
                  </li>
                ))}
              </ul>
              <p className="hint">Where someone lives never puts them in Do not submit by itself; it becomes a question to ask.</p>
            </section>
          )}
          {dates.length > 0 && (
            <section className="panel">
              <h3>Process dates</h3>
              <ul className="reqs">
                {dates.map((d) => (
                  <li key={d.id}>
                    {d.payload.normalized_token} · {d.payload.text_raw}
                    {d.flags.job_process_stale && <span className="pill">passed</span>}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}

      {tab === "find" && (
        <section className="panel">
          <h3>Find more people {thin ? `(priority is thin: ${sourcing.priority} of ${sourcing.default_target})` : ""}</h3>
          {thin ? <FindMore action={startCampaign.bind(null, job.id)} tokens={tokens} byProfile={sourcing.by_profile} />
            : <p className="sub">Priority has {sourcing.priority}; sourcing is for a thin queue.</p>}
          <p className="hint">Searches the desk&apos;s own people only. Everyone found is banded by the same rules as an uploaded CV; being found never changes a band.</p>
          {sourcing.campaigns.length > 0 && (
            <ul className="campaigns">
              {sourcing.campaigns.map((c) => (
                <li key={c.id}>
                  <span className="sub">{c.created_at.slice(0, 16).replace("T", " ")}</span> · {c.source === "profile" ? "by profile" : "desk"} · {(c.query.words ?? c.query.tokens ?? []).join(", ")} ·
                  looked at {c.spent}/{c.cap} · added {c.added} ({c.priority_added} priority) · {c.status === "exhausted" ? "no more matches" : STOP_WORDS[c.stop_reason ?? ""] ?? c.status}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {tab === "countries" && (
        <section className="panel">
          <h3>Countries this job accepts</h3>
          <p className="sub">
            The desk covers the EU / EEA, the UK, Switzerland, the US and Canada.
            {job.coverage.from_ad.length > 0 && <> The ad also accepts: {job.coverage.from_ad.map((c) => job.coverage.names[c] ?? c).join(", ")}.</>}
          </p>
          <CountriesForm action={setJobCountries.bind(null, job.id)} opened={job.coverage.opened.map((c) => job.coverage.names[c] ?? c).join(", ")} />
          <p className="hint">Decided by where people live and work now, never by nationality or where they are from.</p>
        </section>
      )}
    </>
  );
}
