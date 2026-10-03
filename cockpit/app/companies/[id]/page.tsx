import Link from "next/link";
import { apiOr404 } from "@/lib/api";
import { period } from "@/lib/format";

export const metadata = { title: "Company" };

type CompanyPage = {
  id: string;
  name: string;
  aliases: string[];
  people_count: number;
  people: { candidate_id: string; name: string | null; current: boolean;
    roles: { title: string | null; valid_from: string | null; valid_to: string | null; current: boolean }[] }[];
  jobs: { id: string; title: string }[];
};

export default async function Company({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const c = await apiOr404<CompanyPage>(`/v1/companies/${id}`);
  return (
    <>
      <h1>{c.name}</h1>
      <p className="sub">
        We know {c.people_count} {c.people_count === 1 ? "person" : "people"} who worked here.
        {c.aliases.length > 1 && <> Also written as: {c.aliases.join(", ")}.</>}
      </p>
      <p className="hint">Company facts (domain, stage, funding, size) arrive with company research in the next phase.</p>

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
