import Link from "next/link";
import { ClaimRow, Status } from "@/components/Claim";
import { api, type PersonPage } from "@/lib/api";
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
  const person = await api<PersonPage>(`/v1/candidates/${id}`);
  const path = `/people/${id}`;
  const skills = person.claims.SkillClaim ?? [];

  return (
    <>
      <h1>{person.name ?? "Name not read"}</h1>
      <p className="sub">
        Facts are proposed by the machine and official only once approved.
        {person.open_decisions.length > 0 && <> · <Link href="/inbox?band=all">{person.open_decisions.length} open in the inbox</Link></>}
      </p>

      {person.jobs.length > 0 && (
        <>
          <h2>Jobs</h2>
          <ul className="people">
            {person.jobs.map((j) => (
              <li key={j.job_id}>
                <Link href={`/jobs/${j.job_id}`}>{j.title}</Link>
                <span>{BAND_LABEL[j.band]}</span>
                <span className="reason">{reasonWords(j.reason)}</span>
              </li>
            ))}
          </ul>
        </>
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
    </>
  );
}
