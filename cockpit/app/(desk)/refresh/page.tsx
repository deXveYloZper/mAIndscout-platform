import Link from "next/link";
import { api } from "@/lib/api";

export const metadata = { title: "Refresh" };

type Fresh = { status: string; since: string | null; words: string };
type Lists = { person_months: number; company_months: number;
  people: { candidate_id: string; name: string | null; why: string[]; freshness: Fresh }[];
  clients: { company_id: string; name: string; why: string[]; freshness: Fresh }[] };

export default async function Refresh() {
  const lists = await api<Lists>("/v1/freshness");
  return (
    <>
      <h1>Refresh</h1>
      <p className="sub">
        People nobody has contacted or verified for {lists.person_months} months, and clients without contact or fresh facts for {lists.company_months} months.
        Most valuable first: priority on a live job, a strong match on a live job, a talent pool, a strong career; then whoever has been silent longest.
      </p>
      <h2>Re-contact these people ({lists.people.length})</h2>
      {lists.people.length === 0 ? <p className="empty">Nobody is stale.</p> : (
        <ul className="results-list">
          {lists.people.map((p) => (
            <li key={p.candidate_id}>
              <div><Link href={`/people/${p.candidate_id}`}>{p.name ?? "name not read"}</Link> <span className="sub">· {p.freshness.words}</span></div>
              {p.why.length > 0 && <div className="why-line">Why now: {p.why.join("; ")}</div>}
            </li>
          ))}
        </ul>
      )}
      <h2>Clients to reconnect with ({lists.clients.length})</h2>
      {lists.clients.length === 0 ? <p className="empty">No stale clients.</p> : (
        <ul className="results-list">
          {lists.clients.map((c) => (
            <li key={c.company_id}>
              <div><Link href={`/companies/${c.company_id}`}>{c.name}</Link> <span className="sub">· {c.freshness.words}</span></div>
              {c.why.length > 0 && <div className="why-line">{c.why.join("; ")}</div>}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
