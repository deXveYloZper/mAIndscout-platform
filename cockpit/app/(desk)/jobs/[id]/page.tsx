import Link from "next/link";
import { FileText, Inbox, MessageSquareText } from "lucide-react";
import { deleteJob, overrideBand, setJobCountries, setJobState } from "@/app/actions";
import { CountriesForm } from "@/components/CountriesForm";
import { HiringProfile } from "@/components/HiringProfile";
import { Snippet } from "@/components/Claim";
import { MultiUpload } from "@/components/MultiUpload";
import { RoleControls } from "@/components/RoleControls";
import { SourcingTab } from "@/components/Sourcing";
import { api, apiOr404, type Band, type InboxItem, type JobPage, type PersonOnJob, type SourcingPage, type SourcingStats } from "@/lib/api";
import { BAND_LABEL, countryName, PIPELINE, reasonWords, STATE_LABEL, TIER_WORDS } from "@/lib/format";
import { ActForm } from "@/components/ActForm";

export const metadata = { title: "Job" };

const FACET_LABEL: Record<string, string> = {
  residence: "Must live in or work from",
  visa_sponsorship: "Visa sponsorship",
  relocation_assistance: "Relocation assistance",
};
const BANDS: (Band | "archived")[] = ["priority", "review_later", "do_not_submit", "archived"];
const TABS: [string, string][] = [["people", "People"], ["profile", "Hiring profile"], ["find", "Sourcing"]];

function facetValue(m: { facet: string; countries?: string[] | null; offered?: boolean | null }): string {
  return m.offered === true ? "offered" : m.offered === false ? "not offered" : "not stated";
}

/** Evidence, questions, missing and conflicts as one bar: how well a person is known against this job, at a glance. */
function GapBar({ g }: { g: NonNullable<PersonOnJob["gaps"]> }) {
  const likely = g.likely ?? 0;
  const total = g.evidence + likely + g.question + g.missing + g.conflict;
  if (!total) return null;
  const pct = (n: number) => `${(n / total) * 100}%`;
  return (
    <span className="gapbar" title={`${g.evidence} evidence${likely ? ` · ${likely} likely from their employer` : ""} · ${g.question} to ask · ${g.missing} missing${g.conflict ? ` · ${g.conflict} conflict` : ""}`}>
      <span className="track" aria-hidden="true">
        <span className="ev" style={{ width: pct(g.evidence) }} />
        <span className="q" style={{ width: pct(g.question + likely) }} />
        <span className="cf" style={{ width: pct(g.conflict) }} />
      </span>
      <span className="mini">{g.evidence} evidence{likely ? ` · ${likely} likely` : ""} · {g.question} to ask · {g.missing} missing{g.conflict ? ` · ${g.conflict} conflict` : ""}</span>
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
              {p.stopped && <span className="blocktag" title="They asked not to be contacted: never drafted to or put forward">asked not to be contacted</span>}
              {p.coverage && !p.coverage.met && p.coverage.applicable > 0 && <span className="thintag" title={p.coverage.words}>thin</span>}
              {p.open_decisions > 0 && <span className="pill">{p.open_decisions} to review</span>}
            </div>
            <p className="reason">{reasonWords(p.reason)}</p>
            {p.gaps && <GapBar g={p.gaps} />}
          </div>
          <div className="pc-side">
            <Link className="btn small" href={`/jobs/${jobId}/people/${p.candidate_id}/brief${p.band === "priority" ? "" : "?force=1"}`}>
              <MessageSquareText aria-hidden="true" />Brief
            </Link>
            <details className="move">
              <summary className="btn small ghost">Move</summary>
              <ActForm action={overrideBand.bind(null, jobId, p.candidate_id)} className="movebox">
                <select name="band" defaultValue={p.band} aria-label="Band">
                  {(Object.keys(BAND_LABEL) as Band[]).map((b) => <option key={b} value={b}>{BAND_LABEL[b]}</option>)}
                </select>
                <input name="reason" placeholder="why (shown in the history)" aria-label="Reason for changing the band" />
                <button className="btn small primary">Set band</button>
              </ActForm>
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
  const [job, waiting] = await Promise.all([
    apiOr404<JobPage>(`/v1/jobs/${id}`),
    api<InboxItem[]>(`/v1/inbox?job_id=${id}&band=priority`),
  ]);
  const band = (BANDS as string[]).includes(sp.band ?? "") ? (sp.band as Band | "archived") : "priority";
  const tab = TABS.some(([k]) => k === sp.tab) ? sp.tab! : "people";
  // The sourcing plan is made (paused) the first time the tab is opened: no request makes one otherwise.
  const [engine, results] = tab === "find" && job.state === "open"
    ? await Promise.all([api<SourcingPage>(`/v1/jobs/${id}/sourcing`), api<SourcingStats>(`/v1/sourcing/stats?job_id=${id}&group=tier`)])
    : [null, null];
  const places = job.requirements.filter((r) => r.payload.category === "location" && r.payload.strength === "unknown" && !r.payload.mobility);
  const mobility = job.requirements.filter((r) => r.payload.mobility && r.payload.mobility.facet !== "residence");
  const residence = job.requirements.find((r) => r.payload.mobility?.facet === "residence");
  const lives: string[] = residence?.payload.mobility.countries ?? [];
  const must = job.requirements.filter((r) => r.payload.category !== "process" && !places.includes(r) && !r.payload.mobility);
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
          <h1>{job.title}{job.state !== "open" && <span className="statetag we_passed"> {job.state.replace("_", " ")}</span>}</h1>
          {places.length > 0 && <p className="sub where">{places.map((p) => p.payload.text_raw).join(" · ")}</p>}
        </div>
        <div className="actions">
          <Link href={`/inbox?job=${job.id}`} className="btn"><Inbox aria-hidden="true" />{waiting.length ? `${waiting.length} question${waiting.length === 1 ? "" : "s"}` : "No questions"}</Link>
          {job.source_document_id && (
            <a href={`/files/${job.source_document_id}`} target="_blank" rel="noreferrer" className="btn ghost"><FileText aria-hidden="true" />The ad</a>
          )}
          <RoleControls state={job.state} setState={setJobState.bind(null, job.id)} remove={deleteJob.bind(null, job.id)} foundOnly={job.found_only_here} />
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
            {label}
            {k === "find" && job.suggestions_waiting > 0 ? <span className="pill accent" title="Suggestions to review">{job.suggestions_waiting}</span> : null}
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
            <>
              {job.suggestions_waiting > 0 && (
                <p className="hint">{job.suggestions_waiting} {job.suggestions_waiting === 1 ? "person" : "people"} found by sourcing wait on
                  the <Link href={href({ tab: "find" })}>Sourcing tab</Link>: they join these lists when you choose them.</p>
              )}
              <People jobId={job.id} people={job.people[band]} />
            </>
          )}
        </>
      )}

      {tab === "profile" && (
        <>
          <HiringProfile job={job} requirements={must} />
          <section className="panel">
            <h3>Where people must live</h3>
            <p className="sub">
              {lives.length ? lives.map(countryName).join(", ") : "Not stated: sourcing uses the ad's places, or where the client's team works."}
              {residence?.payload.cities?.length ? ` · ${residence.payload.cities.join(", ")}` : ""}
              {residence?.payload.relocation ? " · moving there is welcome" : ""}
              {residence ? <span className="sub"> · {residence.payload.source === "intake" ? "from the intake notes" : residence.payload.source === "recruiter" ? "set by a person" : "from the ad"}</span> : null}
            </p>
            <CountriesForm action={setJobCountries.bind(null, job.id)} current={lives.map(countryName).join(", ")} />
            <p className="hint">The one place for the role&apos;s countries: sourcing searches and suggests only here, and people living here are
              never archived as outside the desk&apos;s coverage (the desk covers the EU / EEA, the UK, Switzerland, the US and Canada).
              Where someone lives never puts them in Do not submit by itself; it becomes a question to ask. Decided by where people
              live and work now, never by nationality.</p>
          </section>
          {mobility.length > 0 && (
            <section className="panel">
              <h3>Visa and relocation</h3>
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

      {tab === "find" && engine && results && <SourcingTab s={engine} stats={results} />}
      {tab === "find" && job.state !== "open" && <p className="empty">Only an open role is sourced.</p>}


    </>
  );
}
