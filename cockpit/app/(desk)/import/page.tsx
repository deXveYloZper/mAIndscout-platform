import Link from "next/link";
import { uploadImport } from "@/app/actions";
import { api } from "@/lib/api";

export const metadata = { title: "Import" };

type Batches = { allowance: Record<string, number>; used: Record<string, number>;
  batches: { id: string; kind: string; filename: string | null; at: string | null }[] };

export default async function Import() {
  const b = await api<Batches>("/v1/imports");
  return (
    <>
      <h1>Import and export</h1>
      <p className="sub">
        Bring in the candidates and clients you actually know, from a CSV (every ATS can export one). Free per account:
        {" "}<strong>{b.allowance.candidates} candidates</strong> ({b.used.candidates} used) and <strong>{b.allowance.clients} clients</strong> ({b.used.clients} used).
        You tick each row you vouch for: it comes in as an approved fact with you as the source. Anything beyond the free
        allowance is paid analysis (our compute cost + 90%), never taken in unverified.
      </p>
      <section className="panel">
        <h3>Upload a CSV</h3>
        <form action={uploadImport} className="row">
          <select name="kind" aria-label="What the file holds" defaultValue="candidates">
            <option value="candidates">candidates</option>
            <option value="clients">clients (companies and contacts)</option>
          </select>
          <input type="file" name="file" accept=".csv,text/csv" aria-label="CSV file" required />
          <button className="btn primary">Preview</button>
        </form>
        <p className="hint">Columns are recognised by common names: name (or first and last name), email, phone, LinkedIn, location, current company, title, tags, notes; for clients: company, website, contact name, title, email, phone. A &quot;last contacted&quot; column is kept only as a note: we do not trust another system&apos;s freshness.</p>
      </section>
      <section className="panel">
        <h3>Export</h3>
        <p><a className="btn small" href="/export/people">Download everyone as CSV</a> <span className="sub">Your desk&apos;s data, always free.</span></p>
      </section>
      {b.batches.length > 0 && (
        <>
          <h2>Recent imports</h2>
          <ul className="reqs">
            {b.batches.map((x) => (
              <li key={x.id}><Link href={`/import/${x.id}`}>{x.filename ?? "file"}</Link> <span className="sub">· {x.kind} · {x.at?.slice(0, 10)}</span></li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}
