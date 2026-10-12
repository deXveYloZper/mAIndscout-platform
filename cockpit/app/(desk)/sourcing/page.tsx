import Link from "next/link";
import { X } from "lucide-react";
import { addOffLimits, removeOffLimits, setDeskSourcingBudget } from "@/app/actions";
import { AddOffLimits, DeskBudget } from "@/components/SourcingForms";
import { api, currentUser, type JobSummary, type SourcingStats } from "@/lib/api";

export const metadata = { title: "Sourcing" };

/* Results and spend (docs/next/PLAN.md S5): what each search strategy cost and what it brought, so the owner can
   change what doesn't work. Plus the desk's sourcing budget and its off-limits companies. */

const GROUPS: [string, string][] = [["channel", "Channel"], ["tier", "Company group"], ["target", "Target company"],
  ["query", "Search"], ["week", "Week"], ["job", "Role"]];
const SINCE: [string, string][] = [["30", "30 days"], ["90", "90 days"], ["all", "All time"]];
const COLS: [keyof SourcingStats["totals"], string][] = [["found", "Found"], ["relevant", "Relevant"], ["contacted", "Contacted"],
  ["replied", "Replied"], ["interested", "Interested"], ["cv", "CV"], ["submitted", "Submitted"], ["interviewed", "Interviewed"],
  ["placed", "Placed"]];

const usd = (n: number | null) => (n === null ? "–" : `$${n < 1 ? n.toFixed(3) : n.toFixed(2)}`);

type OffLimitsList = { companies: { company_id: string; name: string | null; why: string; id: string | null; until: string | null }[] };
type Settings = { sourcing_budget_usd: number; spent_usd: number; web_ready: boolean };

export default async function Sourcing({ searchParams }: { searchParams: Promise<{ group?: string; since?: string; job?: string }> }) {
  const sp = await searchParams;
  const group = GROUPS.some(([k]) => k === sp.group) ? sp.group! : "channel";
  const since = SINCE.some(([k]) => k === sp.since) ? sp.since! : "90";
  const from = since === "all" ? null : new Date(Date.now() - Number(since) * 86400000).toISOString().slice(0, 10);
  const q = new URLSearchParams({ group, ...(from ? { since: from } : {}), ...(sp.job ? { job_id: sp.job } : {}) });
  const [stats, settings, off, jobs, me] = await Promise.all([
    api<SourcingStats>(`/v1/sourcing/stats?${q}`), api<Settings>("/v1/sourcing/settings"), api<OffLimitsList>("/v1/off-limits"),
    api<JobSummary[]>("/v1/jobs"), currentUser()]);
  const job = sp.job ? jobs.find((j) => j.id === sp.job) : null;
  const href = (k: Record<string, string>) => `/sourcing?${new URLSearchParams({ group, since, ...(sp.job ? { job: sp.job } : {}), ...k })}`;
  const t = stats.totals;

  return (
    <>
      <div className="pagehead">
        <div>
          <p className="eyebrow">{job ? <Link href={`/jobs/${job.id}?tab=find`}>{job.title}</Link> : "Every role"}</p>
          <h1>Sourcing results and spend</h1>
          <p className="sub">What each search strategy cost, and how far the people it found got.</p>
        </div>
      </div>

      <div className="stats">
        <div className="stat accent"><span className="label">Spent</span><span className="value">{usd(t.spend_usd)}</span>
          <span className="note">this month {usd(settings.spent_usd)} of {usd(settings.sourcing_budget_usd)}</span></div>
        <div className="stat"><span className="label">Found</span><span className="value">{t.found}</span><span className="note">{t.new_to_desk} new to the desk</span></div>
        <div className="stat"><span className="label">Relevant</span><span className="value">{t.relevant}</span><span className="note">{usd(t.cost_per_relevant)} each</span></div>
        <div className="stat"><span className="label">Interviews</span><span className="value">{t.interviewed}</span><span className="note">{usd(t.cost_per_interview)} each</span></div>
        <div className="stat"><span className="label">Placed</span><span className="value">{t.placed}</span><span className="note">{usd(t.cost_per_placement)} each</span></div>
      </div>

      {stats.flags.length > 0 && (
        <ul className="flags">{stats.flags.map((f, i) => <li key={i} className={`flag ${f.level}`}>{f.text}</li>)}</ul>
      )}

      <section className="panel">
        <div className="row spread">
          <nav className="groupnav" aria-label="Group by">
            {GROUPS.map(([k, l]) => <Link key={k} href={href({ group: k })} aria-current={group === k ? "page" : undefined}>{l}</Link>)}
          </nav>
          <nav className="groupnav" aria-label="Period">
            {SINCE.map(([k, l]) => <Link key={k} href={href({ since: k })} aria-current={since === k ? "page" : undefined}>{l}</Link>)}
          </nav>
        </div>
        {stats.groups.length === 0 ? <p className="empty">Nothing found by sourcing in this period yet.</p> : (
          <div className="tablewrap">
            <table className="results">
              <thead>
                <tr><th>{GROUPS.find(([k]) => k === group)?.[1]}</th><th className="num">Spent</th>
                  {COLS.map(([, l]) => <th key={l} className="num">{l}</th>)}<th className="num">Per relevant</th><th className="num">Per interview</th></tr>
              </thead>
              <tbody>
                {stats.groups.map((g) => (
                  <tr key={g.key}>
                    <td>{group === "job" ? <Link href={`/jobs/${g.key}?tab=find`}>{g.label}</Link> : g.label}</td>
                    <td className="num">{usd(g.spend_usd)}</td>
                    {COLS.map(([k]) => <td key={k} className="num">{g[k] as number}</td>)}
                    <td className="num">{usd(g.cost_per_relevant)}</td><td className="num">{usd(g.cost_per_interview)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="hint">Each person counts once per role, for the search that found them first. &ldquo;How far they got&rdquo; is the furthest
          stage they reached, so someone we later passed on still counts as contacted. Company searches for the market map are
          in the total spend, not in a row.</p>
      </section>

      <section className="panel">
        <h3>Budget</h3>
        {me?.role === "owner" ? <DeskBudget action={setDeskSourcingBudget} budget={settings.sourcing_budget_usd} />
          : <p className="sub">The desk&apos;s monthly sourcing budget is {usd(settings.sourcing_budget_usd)} (an owner can change it).</p>}
        <p className="hint">Each role also has its own monthly budget (on its Sourcing tab). Sourcing has its own budget, so a busy search month
          never stops the desk reading CVs.{!settings.web_ready && " Web search is not set up: add EXA_API_KEY to core/.env."}</p>
      </section>

      <section className="panel">
        <h3>Off-limits companies</h3>
        <p className="sub">Never sourced from. Active clients and clients we placed someone at in the last 12 months are added by themselves.</p>
        {off.companies.length === 0 ? <p className="empty">None yet.</p> : (
          <ul className="targets">
            {off.companies.map((c) => (
              <li key={c.company_id}>
                <div><Link href={`/companies/${c.company_id}`}><strong>{c.name ?? "a company"}</strong></Link>
                  <p className="hint">{c.why}{c.until ? ` · until ${c.until}` : ""}</p></div>
                {c.id && (
                  <form action={removeOffLimits.bind(null, c.id)}>
                    <button className="btn small ghost" aria-label={`Remove ${c.name} from the list`}><X aria-hidden="true" /></button>
                  </form>
                )}
              </li>
            ))}
          </ul>
        )}
        <AddOffLimits action={addOffLimits} />
      </section>
    </>
  );
}
