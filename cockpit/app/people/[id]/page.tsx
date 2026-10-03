import Link from "next/link";
import { addFact, bringBack, eraseCandidate, putOnJob } from "@/app/actions";
import { CareerProfile } from "@/components/CareerProfile";
import { ClaimRow, Status } from "@/components/Claim";
import { EraseForm } from "@/components/EraseForm";
import { FactForm } from "@/components/FactForm";
import { api, apiOr404, type JobSummary, type PersonPage } from "@/lib/api";
import { BAND_LABEL, reasonWords } from "@/lib/format";

export const metadata = { title: "Person" };

const SECTIONS: [string, string][] = [
  ["IdentityClaim", "Name"],
  ["ContactClaim", "Contacts"],
  ["CareerStepClaim", "Career"],
  ["EducationClaim", "Education"],
  ["LocationClaim", "Location"],
];

export default async function Person({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [person, jobs] = await Promise.all([apiOr404<PersonPage>(`/v1/candidates/${id}`), api<JobSummary[]>("/v1/jobs")]);
  const otherJobs = jobs.filter((j) => !person.jobs.some((p) => p.job_id === j.id));
  const path = `/people/${id}`;
  const skills = person.claims.SkillClaim ?? [];

  return (
    <>
      <h1>{person.name ?? "Name not read"}</h1>
      <p className="sub">
        Facts are proposed by the machine and official only once approved.
        {person.open_decisions.length > 0 && <> · <Link href="/inbox?band=all">{person.open_decisions.length} open in the inbox</Link></>}
      </p>
      {person.archived && (
        <div className="warn archived-note">
          Archived: {person.archived.reason ?? "outside the desk's coverage"}. No company research or profiling is spent on archived people.
          <form action={bringBack.bind(null, person.id, path)}><button className="btn small">Bring back</button></form>
        </div>
      )}
      {person.coverage_override && !person.archived && <p className="hint">Brought back by a person: the coverage rule leaves them be.</p>}

      {otherJobs.length > 0 && (
        <form action={putOnJob.bind(null, person.id)} className="row" style={{ marginTop: 12 }}>
          <select name="job" aria-label="Job to put this person on" defaultValue="">
            <option value="" disabled>Put on a job…</option>
            {otherJobs.map((j) => <option key={j.id} value={j.id}>{j.title}</option>)}
          </select>
          <button className="btn small">Put on job</button>
        </form>
      )}
      {person.jobs.length === 0 && <p className="sub">Not on any job yet (in the pool).</p>}
      {person.jobs.length > 0 && (
        <>
          <h2>Jobs</h2>
          <ul className="people">
            {person.jobs.map((j) => (
              <li key={j.job_id}>
                <Link href={`/jobs/${j.job_id}/people/${person.id}`}>{j.title}</Link>
                <span>{BAND_LABEL[j.band]}</span>
                <span className="reason">{reasonWords(j.reason)}</span>
              </li>
            ))}
          </ul>
        </>
      )}

      {!person.archived && (
        <CareerProfile candidateId={person.id} path={path} profile={person.profile} labels={person.classifications}
          careers={(person.claims.CareerStepClaim ?? []).filter((c) => c.status === "proposed" || c.status === "approved")} />
      )}

      {SECTIONS.map(([type, title]) =>
        person.claims[type]?.length ? (
          <section key={type}>
            <h2>{title}</h2>
            <ul>{person.claims[type].map((c) => <ClaimRow key={c.id} claim={c} path={path} />)}</ul>
          </section>
        ) : null,
      )}

      {skills.length > 0 && (
        <>
          <h2>Skills ({skills.length})</h2>
          <ul className="chips">
            {skills.map((s) => (
              <li key={s.id} title={s.evidence[0]?.snippet ?? ""}>
                {s.payload.raw_label} {s.status !== "proposed" && <Status status={s.status} />}
              </li>
            ))}
          </ul>
        </>
      )}

      <h2>Documents</h2>
      <ul>
        {person.documents.map((d) => (
          <li key={d.id}>
            <a href={`/files/${d.id}`} target="_blank" rel="noreferrer">{d.filename ?? d.id}</a>
            <span className="sub"> · as of {d.as_of ?? "unknown"}{d.needs_vision ? " · has images or a lossy layout: the text may be incomplete" : ""}</span>
          </li>
        ))}
      </ul>

      <section className="panel">
        <h3>Add or correct a fact</h3>
        <p className="sub">What you type is saved as approved, with you as the source. A typed email, phone or LinkedIn can be used to recognise this person in later CVs.</p>
        <FactForm action={addFact.bind(null, person.id, path, null, null)} defaultKind={person.name ? "email" : "name"} />
      </section>

      <EraseForm action={eraseCandidate.bind(null, person.id)} />
    </>
  );
}
