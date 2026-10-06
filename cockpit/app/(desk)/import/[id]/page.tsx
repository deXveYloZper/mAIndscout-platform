import Link from "next/link";
import { acceptImportQuote, importRows } from "@/app/actions";
import { apiOr404 } from "@/lib/api";

export const metadata = { title: "Import preview" };

type Row = { id: string; row: number; data: Record<string, string>; status: string; reason: string | null;
  candidate_id: string | null; company_id: string | null };
type Batch = { id: string; kind: string; filename: string | null; columns: Record<string, string>; allowance: number;
  free_left: number; counts: Record<string, number>; quote_accepted: string | null;
  quote: { rows_over_allowance: number; unit_cost_usd: number; markup: number; quote_usd: number }; rows: Row[] };

const STATUS: Record<string, string> = { ready: "ready", duplicate: "already here", invalid: "cannot use", imported: "imported",
  held: "held for paid analysis", skipped: "skipped" };

function summary(kind: string, d: Record<string, string>): string {
  if (kind === "clients") return [d.company, d.contact_name && `contact ${d.contact_name}${d.contact_role ? ` (${d.contact_role})` : ""}`].filter(Boolean).join(" · ");
  const name = d.name || [d.first_name, d.last_name].filter(Boolean).join(" ");
  return [name, d.title && d.company ? `${d.title} at ${d.company}` : d.company, d.location, d.email].filter(Boolean).join(" · ");
}

export default async function ImportPreview({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const b = await apiOr404<Batch>(`/v1/imports/${id}`);
  const path = `/import/${id}`;
  const ready = b.rows.filter((r) => r.status === "ready");
  return (
    <>
      <p className="sub"><Link href="/import">Import</Link></p>
      <h1>{b.filename ?? "Import"}: {b.kind}</h1>
      <p className="sub">
        {Object.entries(b.counts).map(([k, n]) => `${n} ${STATUS[k] ?? k}`).join(" · ")}. Free left on this account: <strong>{b.free_left}</strong> of {b.allowance}.
      </p>
      <p className="hint">Columns used: {Object.entries(b.columns).map(([ours, theirs]) => `${theirs} → ${ours.replace("_", " ")}`).join(", ")}.</p>

      {ready.length > 0 && (
        <form action={importRows.bind(null, id, path)}>
          <p className="row">
            <button className="btn primary">Import ticked rows</button>
            <span className="sub">Tick only people and clients you know: each comes in as an approved fact with you as the source (up to {b.free_left} free).</span>
          </p>
          <ul className="import-rows">
            {ready.map((r, i) => (
              <li key={r.id}>
                <label>
                  <input type="checkbox" name="row" value={r.id} defaultChecked={i < b.free_left} aria-label={`Import row ${r.row}`} />
                  {" "}<span className="sub">#{r.row}</span> {summary(b.kind, r.data)}
                </label>
              </li>
            ))}
          </ul>
        </form>
      )}

      {b.quote.rows_over_allowance > 0 && !b.quote_accepted && (
        <section className="panel">
          <h3>Beyond the free allowance</h3>
          <p>
            {b.quote.rows_over_allowance} more rows than the free allowance. Paid analysis: <strong>${b.quote.quote_usd.toFixed(2)}</strong>
            {" "}<span className="sub">(our measured compute ${b.quote.unit_cost_usd.toFixed(4)} per record × {b.quote.markup}). They are verified before they become facts.</span>
          </p>
          <form action={acceptImportQuote.bind(null, id, path)}><button className="btn small">Accept the quote</button></form>
        </section>
      )}
      {b.quote_accepted && <p className="warn">Paid analysis ordered {b.quote_accepted.slice(0, 10)}: the held rows are verified before they become facts.</p>}

      {b.rows.some((r) => r.status !== "ready") && (
        <details className="band" open>
          <summary>Other rows ({b.rows.length - ready.length})</summary>
          <ul className="import-rows">
            {b.rows.filter((r) => r.status !== "ready").map((r) => (
              <li key={r.id} className={r.status}>
                <span className="sub">#{r.row}</span> {summary(b.kind, r.data) || "(empty)"} · <strong>{STATUS[r.status] ?? r.status}</strong>
                {r.reason && <span className="sub">: {r.reason}</span>}
                {r.candidate_id && <> · <Link href={`/people/${r.candidate_id}`}>open</Link></>}
                {r.company_id && <> · <Link href={`/companies/${r.company_id}`}>open</Link></>}
              </li>
            ))}
          </ul>
        </details>
      )}
    </>
  );
}
