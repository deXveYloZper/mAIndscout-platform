import { api } from "@/lib/api";

export const metadata = { title: "Costs" };

type Costs = {
  month: string;
  spent_usd: number;
  budget_usd: number;
  shared_research_usd: number;
  by_purpose: { purpose: string; calls: number; usd: number; input_tokens: number; output_tokens: number; sources: number }[];
  by_day: { day: string; usd: number }[];
};

const PURPOSE: Record<string, string> = { read_cv: "Reading CVs", read_jd: "Reading job ads", research_company: "Company research" };

export default async function CostsPage() {
  const c = await api<Costs>("/v1/costs");
  const left = Math.max(c.budget_usd - c.spent_usd, 0);
  return (
    <>
      <h1>Costs</h1>
      <p className="sub">Every model call and web search is recorded. Paid work pauses when the monthly budget is reached.</p>
      <section className="panel">
        <p><strong>{c.month}:</strong> ${c.spent_usd.toFixed(2)} of ${c.budget_usd.toFixed(2)} budget · ${left.toFixed(2)} left</p>
        <div className="meter" role="img" aria-label={`$${c.spent_usd.toFixed(2)} of $${c.budget_usd.toFixed(2)} spent`}>
          <span style={{ width: `${Math.min((c.spent_usd / Math.max(c.budget_usd, 0.01)) * 100, 100)}%` }} />
        </div>
        <p className="hint">Shared company research this month (reused by every desk): ${c.shared_research_usd.toFixed(2)}. Budget is set with MONTHLY_BUDGET_USD in core/.env.</p>
      </section>
      <h2>By purpose</h2>
      {c.by_purpose.length === 0 ? <p className="empty">Nothing spent this month.</p> : (
        <div className="tablewrap">
          <table>
            <thead><tr><th>What</th><th className="num">Calls</th><th className="num">Tokens in</th><th className="num hide-narrow">Tokens out</th><th className="num">Cost</th></tr></thead>
            <tbody>
              {c.by_purpose.map((p) => (
                <tr key={p.purpose}>
                  <td>{PURPOSE[p.purpose] ?? p.purpose}</td>
                  <td className="num">{p.calls}</td>
                  <td className="num">{p.input_tokens.toLocaleString()}</td>
                  <td className="num hide-narrow">{p.output_tokens.toLocaleString()}</td>
                  <td className="num">${p.usd.toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {c.by_day.length > 0 && (
        <>
          <h2>By day</h2>
          <ul className="campaigns">{c.by_day.map((d) => <li key={d.day}>{d.day} · ${d.usd.toFixed(3)}</li>)}</ul>
        </>
      )}
    </>
  );
}
