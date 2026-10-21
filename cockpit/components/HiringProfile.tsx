import Link from "next/link";
import { answerBriefQuestion, confirmRequirements, editRequirement, readRoleBrief, rejectClaim, setHiringCompany,
  setJobCountries, tellDesk } from "@/app/actions";
import { AnswerForm, Change, EditForm, Fold, TellForm } from "@/components/BriefForms";
import { Snippet } from "@/components/Claim";
import { CountriesForm } from "@/components/CountriesForm";
import { HiringCompanyForm } from "@/components/HiringCompanyForm";
import { OneClick } from "@/components/SourcingForms";
import type { BriefLine, ClaimView, JobPage, RequirementGroup } from "@/lib/api";
import { countryName, EMPLOYER_KIND_LABEL, FAMILY_LABEL } from "@/lib/format";
import { ActForm } from "@/components/ActForm";

/* The hiring profile in three groups (step E of understanding the hire, owner 2026-10-20): what the desk searches and
   rates by, confirmed once; what is for the call, nothing to confirm; and context. The role brief and its questions
   on top. Every requirement's quote and controls are one click away ("change"). */

const SOURCE: Record<string, string> = { ad: "the ad", intake: "your notes", recruiter: "typed" };
const BASIS: Record<string, string> = { ad: "the ad", notes: "your notes", research: "research", reading: "our reading" };
const FACET: Record<string, string> = { situation: "Situation", core_work: "Core work", team: "Team", hands_on: "Hands-on",
  market: "Market", reports_to: "Reports to", level: "Level" };
const STRENGTH: Record<string, [string, string]> = { must: ["Must", "must"], deal_breaker: ["Must", "must"],
  strong_plus: ["Strong plus", "plus"], nice: ["Nice", "nice"], anti: ["Not wanted", "anti"], unknown: ["Listed", "nice"] };
const ORDER = ["must", "deal_breaker", "strong_plus", "nice", "unknown", "anti"];
const MOBILITY: Record<string, string> = { visa_sponsorship: "Visa sponsorship", relocation_assistance: "Relocation assistance" };

function detail(r: ClaimView, targets: Record<string, number>) {
  const p = r.payload;
  const bits: React.ReactNode[] = [];
  if (p.category === "role" && p.strength === "anti") {
    bits.push(<span key="r">{p.level ? `${p.level} and above` : "too senior"}</span>);  // a limit on seniority
  } else if (p.category === "role") {
    bits.push(<span key="r">{FAMILY_LABEL[p.role_family] ?? p.role_family}{p.level ? `, ${p.level}` : ""}{p.min_years != null ? `, ${p.min_years}+ years` : ""}</span>);
  } else if (p.min_years != null) {
    bits.push(<span key="y">{p.min_years}+ years</span>);
  }
  if (p.education_level) bits.push(<span key="l">{p.education_level}</span>);
  if (p.employer_kinds?.length) bits.push(<span key="e">{p.employer_kinds.map((k: string) => EMPLOYER_KIND_LABEL[k] ?? k).join(", ")}</span>);
  if ((p.min_staff || p.max_staff) && !/\d/.test(p.text_raw ?? "")) {  // "up to 200 people" already says it
    const n = (x: number) => x.toLocaleString("en-GB");
    bits.push(<span key="s">{p.min_staff && p.max_staff ? `${n(p.min_staff)}-${n(p.max_staff)} people`
      : p.max_staff ? `up to ${n(p.max_staff)} people` : `over ${n(p.min_staff - 1)} people`}</span>);
  }
  if (p.domains?.length) bits.push(<span key="d">{p.domains.join(", ")}</span>);
  if (p.employment) bits.push(<span key="m">{p.employment}</span>);
  if (p.companies?.length) {
    bits.push(
      <span key="c">
        {p.companies.map((c: { name: string; company_id: string | null }, i: number) => (
          <span key={i}>
            {i > 0 && ", "}
            {c.company_id ? <Link href={`/companies/${c.company_id}`}>{c.name}</Link> : c.name}
            {c.company_id && <> (we know {targets[c.company_id] ?? 0})</>}
          </span>
        ))}
      </span>,
    );
  }
  if (p.category === "target_company" && p.strength === "anti") {
    bits.push(<span key="w">their people now, and anyone who left in the last {p.recent_months ?? 6} months</span>);
  }
  if (p.note) bits.push(<span key="n" className="note">{p.note}</span>);
  return bits.length ? <span className="reqdetail"> · {bits.reduce<React.ReactNode[]>((a, b, i) => (i ? [...a, " · ", b] : [b]), [])}</span> : null;
}

const WORDS_SKIP = new Set(["experience", "with", "and", "the", "another", "strongly", "preferred", "for", "from", "that"]);
const words = (t: string | undefined) => new Set((t ?? "").toLowerCase().match(/[a-z]{3,}/g)?.filter((w) => !WORDS_SKIP.has(w)) ?? []);

/** The same ask already listed to search by (the ad's long luxury sentence and the luxury strong plus): shown once. */
function duplicate(r: ClaimView, others: ClaimView[]): boolean {
  const w = words(r.payload.text_raw);
  if (!w.size) return false;
  return others.some((o) => {
    const v = words(o.payload.text_raw);
    const shared = [...w].filter((x) => v.has(x)).length;
    return v.size > 0 && shared >= 0.8 * Math.min(w.size, v.size);
  });
}

function LineChange({ r, path, editable = true, removable = editable }: { r: ClaimView; path: string; editable?: boolean;
  removable?: boolean }) {
  return (
    <Change>
      {editable && <EditForm action={editRequirement.bind(null, r.id, path)} text={r.payload.text_raw ?? ""} strength={r.payload.strength} />}
      {removable && (
        <ActForm action={rejectClaim.bind(null, r.id, path, "wrong")}>
          <button className="btn small ghost" title="The desk misread it, or it no longer applies: it stops counting">Remove this line</button>
        </ActForm>
      )}
      {r.payload.category === "process" && <p className="hint">A new date: tell the desk (&ldquo;the next hackathon is on 21 November&rdquo;), and it replaces this one.</p>}
      <p className="sub">Where it comes from:</p>
      <Snippet ev={r.evidence[0]} />
    </Change>
  );
}

function Line({ r, job, quiet }: { r: ClaimView; job: JobPage; quiet?: boolean }) {
  const p = r.payload;
  const [label, cls] = STRENGTH[p.strength] ?? ["Listed", "nice"];
  const m = p.mobility;
  return (
    <li className={`reqline${quiet ? " quiet" : ""}`}>
      {!quiet && <span className={`st st-${cls}`}>{label}</span>}
      <span className="rtext">
        {m ? <><strong>{MOBILITY[m.facet] ?? m.facet}:</strong> {m.offered === true ? "offered" : m.offered === false ? "not offered" : "not stated"}</> : p.text_raw}
        {!quiet && p.distinctive && <span className="tag key" title="Zero evidence of this puts a person in Do not submit">decides the band</span>}
        {!quiet && detail(r, job.hiring.targets)}
      </span>
      <span className="rsrc">{SOURCE[p.source ?? "ad"] ?? "the ad"}
        {!quiet && r.status === "proposed" && <span className="waiting" title="Read by the desk, waiting for your confirmation">new</span>}</span>
      <LineChange r={r} path={`/jobs/${job.id}`} editable={!m} />
    </li>
  );
}

/** "Where people must live" as a line to search by: the role's countries, edited here, the one place they are kept. */
function Residence({ job, r }: { job: JobPage; r: ClaimView | undefined }) {
  const lives: string[] = r?.payload.mobility?.countries ?? [];
  return (
    <li className="reqline">
      <span className="st st-must">{r ? "Must" : "Listed"}</span>
      <span className="rtext">
        Where people must live: {lives.length ? lives.map(countryName).join(", ") : "not stated"}
        {r?.payload.cities?.length ? ` (${r.payload.cities.join(", ")})` : ""}
        {r?.payload.relocation ? " · moving there is welcome" : ""}
        <span className="reqdetail"> · {lives.length ? "sourcing searches and suggests only there" : "sourcing uses the ad's places, or where the client's team works"}</span>
      </span>
      <span className="rsrc">{r ? SOURCE[r.payload.source ?? "ad"] ?? "the ad" : ""}
        {r?.status === "proposed" && <span className="waiting" title="Read by the desk, waiting for your confirmation">new</span>}</span>
      <Change label="Change where people must live">
          <CountriesForm action={setJobCountries.bind(null, job.id)} current={lives.map(countryName).join(", ")} />
          <p className="hint">The one place for the role&apos;s countries: sourcing searches and suggests only here, and people living here
            are never archived as outside the desk&apos;s coverage (the desk covers the EU / EEA, the UK, Switzerland, the US and Canada).
            Where someone lives never puts them in Do not submit by itself; it becomes a question to ask. Decided by where people live
            and work now, never by nationality.</p>
          {r && <Snippet ev={r.evidence[0]} />}
      </Change>
    </li>
  );
}

/** When the brief was read and what it gave, so pressing "Read the brief" visibly did something (owner, 2026-10-21). */
function readLine(lines: BriefLine[], readAt?: string | null): string {
  const latest = readAt ?? lines.map((b) => b.at ?? "").sort().pop();
  const asked = lines.filter((b) => b.question).length;
  const when = latest ? new Date(latest).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "";
  return `Read ${when} · ${lines.length} line${lines.length === 1 ? "" : "s"} · ${asked ? `${asked} question${asked === 1 ? "" : "s"} for you` : "no questions"}`;
}

function Brief({ job, lines }: { job: JobPage; lines: BriefLine[] }) {
  if (!lines.length) {
    return (
      <section className="panel rolebrief">
        <h3>What this hire will really do</h3>
        <p className="sub">Not read yet. The desk reads it from the ad, your notes and public research on the company, each line saying
          where it comes from, with a question or two when it has to guess (about a cent).</p>
        <OneClick action={readRoleBrief.bind(null, job.id)} label="Read the brief" busy="Reading…" primary />
      </section>
    );
  }
  return (
    <section className="panel rolebrief">
      <div className="row spread">
        <h3>What this hire will really do</h3>
        <OneClick action={readRoleBrief.bind(null, job.id)} label="Read again" busy="Reading…" />
      </div>
      <p className="sub briefread" role="status">{readLine(lines, job.role_brief_read_at)}</p>
      <dl className="brieflines">
        {lines.map((b) => (
          <div key={b.id} className="bline">
            <dt>{FACET[b.facet] ?? b.facet}</dt>
            <dd>
              {b.words}{" "}
              <span className={`srcchip ${b.status === "approved" ? "you" : b.basis}`}>{b.status === "approved" ? "you" : BASIS[b.basis] ?? b.basis}</span>
              {b.quote && <span className="quote">&ldquo;{b.quote}&rdquo;</span>}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

/** The desk's questions, each with an answer box, and a box for anything else in the recruiter's own words. */
function TellMore({ job, lines }: { job: JobPage; lines: BriefLine[] }) {
  const asked = lines.filter((b) => b.question);
  return (
    <section className="panel questions">
      <h3>{asked.length ? (asked.length === 1 ? "A question for you" : `${asked.length} questions for you`) : "Tell the desk more"}</h3>
      {asked.map((q) => (
        <div key={q.id} className="question">
          <p className="qtext">{q.question}</p>
          {q.why && <p className="qwhy">Why it matters: {q.why}</p>}
          <AnswerForm action={answerBriefQuestion.bind(null, job.id, q.facet)} id={`answer-${q.facet}`} />
        </div>
      ))}
      {lines.length > 0 && !asked.length && <p className="hint noquestions">No questions for you: the ad and your notes say what the search needs.</p>}
      <TellForm action={tellDesk.bind(null, job.id)} asked={asked.length > 0} />
    </section>
  );
}

/** What the job really asks for, in three groups, with the role brief on top. */
export function HiringProfile({ job }: { job: JobPage }) {
  const company = job.hiring.company;
  const lines = job.role_brief ?? [];
  const group = (r: ClaimView): RequirementGroup => job.requirement_groups?.[r.id]?.[0] ?? "search";
  const residence = job.requirements.find((r) => r.payload.mobility?.facet === "residence");
  const rest = job.requirements.filter((r) => r !== residence);
  const search = rest.filter((r) => group(r) === "search")
    .sort((a, b) => ORDER.indexOf(a.payload.strength) - ORDER.indexOf(b.payload.strength));
  const call = rest.filter((r) => group(r) === "conversation" && !duplicate(r, search));
  const places = rest.filter((r) => r.payload.category === "location" && group(r) === "context");
  const dates = rest.filter((r) => r.payload.category === "process")
    .sort((a, b) => String(a.payload.normalized_token).localeCompare(String(b.payload.normalized_token)));
  const waiting = [...(residence?.status === "proposed" ? [residence] : []), ...search.filter((r) => r.status === "proposed")];
  const total = search.length + (residence ? 1 : 0);
  return (
    <section className="hiring">
      <h2>Hiring profile</h2>
      {company ? (
        <div className="row spread">
          <p className="sub company-line">
            <Link href={`/companies/${company.id}`}>{company.name}</Link>
            {[company.kind, company.stage, company.team, company.founded && `founded ${company.founded}`, company.hq]
              .filter(Boolean).map((x, i) => <span key={i}> · {x}</span>)}
            {company.domains?.length ? <span> · {company.domains.join(", ")}</span> : null}
            {!company.kind && !company.team && <span> · not researched yet</span>}
          </p>
          <details><summary className="sub">Change</summary><HiringCompanyForm action={setHiringCompany.bind(null, job.id)} current={company.name} /></details>
        </div>
      ) : (
        <div className="panel">
          <p className="warn">No hiring company: the ad does not name one. Say who is hiring (or put it in the notes), so the
            strategy can learn where their people came from and which companies are like them.</p>
          <HiringCompanyForm action={setHiringCompany.bind(null, job.id)} />
        </div>
      )}

      <Brief job={job} lines={lines} />
      <TellMore job={job} lines={lines} />

      <section className="panel searchby">
        <h3>What we search and rate by</h3>
        <p className="sub">These decide who is found and how they are rated. Change any line; otherwise confirm them together.</p>
        <ul className="reqs grouped">
          <Residence job={job} r={residence} />
          {search.map((r) => <Line key={r.id} r={r} job={job} />)}
        </ul>
        <div className="confirmbar">
          {waiting.length > 0 ? (
            <>
              <span className="sub">{waiting.length} of these {total} {waiting.length === 1 ? "was" : "were"} read by the desk and {waiting.length === 1 ? "waits" : "wait"} for you</span>
              <OneClick action={confirmRequirements.bind(null, job.id, waiting.map((r) => r.id))} label={`Confirm all ${waiting.length}`} busy="Confirming…" primary />
            </>
          ) : <span className="sub">All confirmed. A change re-rates everyone on the role.</span>}
        </div>
      </section>

      {call.length > 0 && (
        <section className="panel forcall">
          <h3>For the call <span className="sub">· nothing to confirm</span></h3>
          <p className="sub">No profile shows these. Each becomes a question on the call brief of anyone you contact; the answer becomes evidence.</p>
          <ul className="reqs grouped">{call.map((r) => <Line key={r.id} r={r} job={job} quiet />)}</ul>
        </section>
      )}

      {(places.length > 0 || dates.length > 0 || job.hiring.intakes.length > 0) && <section className="panel context">
        <h3>Context</h3>
        <ul className="reqs grouped">
          {places.map((r) => (  // the ad's place can be wrong (owner, 2026-10-21): each one can be changed or removed
            <li key={r.id} className="reqline quiet">
              <span className="rtext">Where the job is: {r.payload.text_raw}</span>
              <span className="rsrc">{SOURCE[r.payload.source ?? "ad"] ?? "the ad"}</span>
              <LineChange r={r} path={`/jobs/${job.id}`} />
            </li>
          ))}
          {dates.map((d) => (
            <li key={d.id} className="reqline quiet">
              <span className="rtext">{d.payload.normalized_token} · {d.payload.text_raw}{d.flags.job_process_stale && <span className="pill">passed</span>}</span>
              <span className="rsrc">{SOURCE[d.payload.source ?? "ad"] ?? "the ad"}</span>
              <LineChange r={d} path={`/jobs/${job.id}`} editable={false} removable />
            </li>
          ))}
        </ul>
        {job.hiring.intakes.length > 0 && (
          <Fold className="fold" summary={<>Your notes and what you told the desk ({job.hiring.intakes.length})</>}>
            {job.hiring.intakes.map((i) => (
              <details key={i.id} className="band">
                <summary>{i.at?.slice(0, 10)} ({i.by})</summary>
                <p className="notes">{i.text}</p>
              </details>
            ))}
          </Fold>
        )}
      </section>}
    </section>
  );
}
