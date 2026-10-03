import Link from "next/link";
import { addIntake, addRequirement, approveClaim, rejectClaim, setStrength } from "@/app/actions";
import { AddRequirement } from "@/components/AddRequirement";
import { Snippet } from "@/components/Claim";
import { IntakeForm } from "@/components/IntakeForm";
import type { ClaimView, JobPage } from "@/lib/api";
import { EMPLOYER_KIND_LABEL, FAMILY_LABEL, KIND_LABEL, STRENGTH_GROUPS, STRENGTHS } from "@/lib/format";

const SOURCE: Record<string, string> = { ad: "from the ad", intake: "from the intake notes", recruiter: "added by a person" };

function detail(r: ClaimView, targets: Record<string, number>) {
  const p = r.payload;
  const bits: React.ReactNode[] = [];
  if (p.category === "role") {
    bits.push(<span key="r">{FAMILY_LABEL[p.role_family] ?? p.role_family}{p.level ? `, ${p.level}` : ""}{p.min_years != null ? `, ${p.min_years}+ years` : ""}</span>);
  }
  if (p.employer_kinds?.length) bits.push(<span key="e">{p.employer_kinds.map((k: string) => EMPLOYER_KIND_LABEL[k] ?? k).join(", ")}</span>);
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
  if (p.note) bits.push(<span key="n" className="note">{p.note}</span>);
  return bits.length ? <span className="reqdetail"> · {bits.reduce<React.ReactNode[]>((a, b, i) => (i ? [...a, " · ", b] : [b]), [])}</span> : null;
}

/** What the job really asks for: the ad, the hiring manager's word, and the recruiter's own edits, by strength. */
export function HiringProfile({ job, requirements }: { job: JobPage; requirements: ClaimView[] }) {
  const path = `/jobs/${job.id}`;
  const company = job.hiring.company;
  return (
    <section className="hiring">
      <h2>Hiring profile</h2>
      {company && (
        <p className="sub company-line">
          <Link href={`/companies/${company.id}`}>{company.name}</Link>
          {[company.kind, company.stage, company.team, company.founded && `founded ${company.founded}`, company.hq]
            .filter(Boolean).map((x, i) => <span key={i}> · {x}</span>)}
          {company.domains?.length ? <span> · {company.domains.join(", ")}</span> : null}
          {!company.kind && !company.team && <span> · not researched yet</span>}
        </p>
      )}
      {STRENGTH_GROUPS.map(([title, strengths]) => {
        const items = requirements.filter((r) => strengths.includes(r.payload.strength));
        if (!items.length) return null;
        return (
          <section key={title}>
            <h3 className="group">{title}</h3>
            <ul className="reqs">
              {items.map((r) => (
                <li key={r.id}>
                  <span className="tag">{KIND_LABEL[r.payload.category] ?? r.payload.category}</span>
                  {r.payload.distinctive && <span className="tag key" title="Zero evidence of this puts a person in Do not submit">decides the band</span>}
                  {r.payload.min_years != null && r.payload.category !== "role" && <span className="tag">{r.payload.min_years}+ years</span>}
                  {r.payload.education_level && <span className="tag">{r.payload.education_level}</span>}
                  {r.payload.text_raw}
                  {detail(r, job.hiring.targets)}
                  <span className="sub"> · {SOURCE[r.payload.source ?? "ad"] ?? "from the ad"}{r.status === "approved" ? ", approved" : ""}</span>
                  <div className="row reqacts">
                    <form action={setStrength.bind(null, r.id, path)} className="row">
                      <select name="strength" defaultValue={r.payload.strength} aria-label="How much it matters">
                        {STRENGTHS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                        {!STRENGTHS.some(([v]) => v === r.payload.strength) && <option value={r.payload.strength}>{r.payload.strength}</option>}
                      </select>
                      <button className="btn small">Set</button>
                    </form>
                    {r.status === "proposed" && (
                      <>
                        <form action={approveClaim.bind(null, r.id, path)}><button className="btn small">Approve</button></form>
                        <form action={rejectClaim.bind(null, r.id, path, "wrong")}><button className="btn small ghost">Reject</button></form>
                      </>
                    )}
                    <details><summary>source</summary><Snippet ev={r.evidence[0]} /></details>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        );
      })}

      <section className="panel">
        <h3>Intake notes</h3>
        <p className="hint">Paste what the hiring manager said. Each requirement read from it keeps its quote; what the hiring manager says replaces what the ad says. Personality, culture or &quot;fit&quot; is never turned into a requirement.</p>
        <IntakeForm action={addIntake.bind(null, job.id)} />
        {job.hiring.intakes.map((i) => (
          <details key={i.id} className="band">
            <summary>Notes from {i.at?.slice(0, 10)} ({i.by})</summary>
            <p className="notes">{i.text}</p>
          </details>
        ))}
      </section>

      <section className="panel">
        <h3>Add a requirement</h3>
        <AddRequirement action={addRequirement.bind(null, job.id)} />
      </section>
    </section>
  );
}
