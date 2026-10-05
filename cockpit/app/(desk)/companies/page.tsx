import Link from "next/link";
import { api } from "@/lib/api";

export const metadata = { title: "Companies" };

type CompanyRow = { id: string; name: string; people_count: number };

export default async function Companies({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const { q } = await searchParams;
  const rows = await api<CompanyRow[]>(`/v1/companies${q ? `?q=${encodeURIComponent(q)}` : ""}`);
  return (
    <>
      <h1>Companies</h1>
      <p className="sub">Every company the desk has met through a CV or a job. Open one to see who we know there.</p>
      <form className="row" action="/companies" method="get">
        <input name="q" defaultValue={q ?? ""} placeholder="company name" aria-label="Search companies" size={32} />
        <button className="btn small">Search</button>
      </form>
      {rows.length === 0 ? <p className="empty">{q ? "No company with that name on the desk." : "No companies yet."}</p> : (
        <div className="tablewrap">
          <table>
            <thead><tr><th>Company</th><th className="num">People we know</th></tr></thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.id}>
                  <td><Link href={`/companies/${c.id}`}>{c.name}</Link></td>
                  <td className="num">{c.people_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
