import Link from "next/link";
import { api } from "@/lib/api";

export const metadata = { title: "Costs" };

type Costs = {
  month: string;
  spent_usd: number;
  budget_usd: number;
  shared_research_usd: number;
  research_budget_usd: number;
  sourcing_usd: number;
  sourcing_budget_usd: number;
  by_purpose: { purpose: string; calls: number; usd: number; input_tokens: number; output_tokens: number; sources: number }[];
  by_day: { day: string; usd: number }[];
};

const PURPOSE: Record<string, string> = {
  read_cv: "Reading CVs", read_jd: "Reading job ads", research_company: "Company research", research_institution: "University research",
  classify_steps: "Reading career steps", hiring_profile: "Hiring profiles from ads", hiring_intake: "Hiring manager notes",
  search_query: "Searches in your own words", draft_message: "Drafting messages",
  sourcing_exa_people: "Sourcing: web people searches", sourcing_company_search: "Sourcing: company searches",
  sourcing_exa_news: "Sourcing: news (talent-release radar)",
  sourcing_company_profile: "Sourcing: company profiles (Exa)", sourcing_talent_dna: "Sourcing: talent DNA (Exa)",
  company_domains: "Reading companies' markets", read_transcript: "Reading call transcripts",
  research_company_exa: "Company profiles from CVs (Exa)",
  role_brief: "Role briefs", process_dates: "Hiring process dates from your notes", company_lines: "Companies' lines of business",
  work_lines: "The roles' work lines", role_titles: "The roles' own titles", work_reading: "Reading people's work against the role",
  sourcing_competitors: "Sourcing: competitor research (web)", sourcing_talent_pools: "Sourcing: talent map (web)",
  sourcing_evidence_check: "Sourcing: deeper public checks", sourcing_company_practices: "Sourcing: what companies use (their job ads)",
  core_work_lines: "Core-work reader measurement: work lines", core_work_check: "Core-work reader measurement: readings",
};

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
        <p className="hint">Budget is set with MONTHLY_BUDGET_USD in core/.env.</p>
      </section>
      <section className="panel">
        <p><strong>Shared company research</strong> (reused by every desk): ${c.shared_research_usd.toFixed(2)} of ${c.research_budget_usd.toFixed(2)} this month</p>
        <div className="meter" role="img" aria-label={`$${c.shared_research_usd.toFixed(2)} of $${c.research_budget_usd.toFixed(2)} spent`}>
          <span style={{ width: `${Math.min((c.shared_research_usd / Math.max(c.research_budget_usd, 0.01)) * 100, 100)}%` }} />
        </div>
        {c.shared_research_usd >= c.research_budget_usd && (
          <p className="warn" role="alert">Used up: company research and company profiles wait until next month. Raise RESEARCH_MONTHLY_BUDGET_USD in
            core/.env to continue now.</p>
        )}
        <p className="hint">Companies on CVs get an Exa profile (about a cent each); Grok research (about $0.09) runs for hiring companies,
          companies named on a role, and Research now.</p>
      </section>
      <section className="panel">
        <p className="hint">Sourcing has its own budget: ${c.sourcing_usd.toFixed(2)} of ${c.sourcing_budget_usd.toFixed(2)} this month
          (<Link href="/sourcing">results and spend</Link>). It is not part of the budgets above.</p>
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
