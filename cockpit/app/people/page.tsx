import Link from "next/link";
import { MultiUpload } from "@/components/MultiUpload";
import { api, type PersonSummary } from "@/lib/api";
import { BAND_LABEL } from "@/lib/format";

export const metadata = { title: "People" };

export default async function People({ searchParams }: { searchParams: Promise<{ show?: string }> }) {
  const { show } = await searchParams;
  const pool = show === "pool";
  const people = await api<PersonSummary[]>(`/v1/candidates${pool ? "?unassigned=true" : ""}`);
  return (
    <>
      <h1>People</h1>
      <p className="sub">Everyone the desk has read. People on no job are the pool: open one to put them on a job.</p>
      <nav className="tabs">
        <Link href="/people" aria-current={!pool ? "page" : undefined}>Everyone</Link>
        <Link href="/people?show=pool" aria-current={pool ? "page" : undefined}>Not on a job</Link>
      </nav>

      <section className="panel">
        <h3>Add CVs without a job</h3>
        <MultiUpload jobId={null} />
      </section>

      {people.length === 0 ? (
        <p className="empty">{pool ? "Nobody is waiting without a job." : "Nobody yet."}</p>
      ) : (
        <div className="tablewrap">
          <table>
            <thead><tr><th>Person</th><th>Jobs and bands</th><th className="hide-narrow">Added</th></tr></thead>
            <tbody>
              {people.map((p) => (
                <tr key={p.id}>
                  <td>
                    <Link href={`/people/${p.id}`}>{p.name ?? "name not read"}</Link>
                    {p.archived && <span className="bandtag archived" title={p.archived}> archived</span>}
                  </td>
                  <td>
                    {p.jobs.length === 0 ? <span className="sub">in the pool</span> : (
                      <span className="joblist">
                        {p.jobs.map((j) => (
                          <span key={j.job_id}>
                            <Link href={`/jobs/${j.job_id}`}>{j.title}</Link> <span className={`bandtag nowrap ${j.band}`}>{BAND_LABEL[j.band]}</span>
                          </span>
                        ))}
                      </span>
                    )}
                  </td>
                  <td className="sub nowrap hide-narrow">{p.created_at.slice(0, 10)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
