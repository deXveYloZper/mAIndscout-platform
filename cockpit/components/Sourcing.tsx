import Link from "next/link";
import { ExternalLink, Pin, PinOff, Radar, Undo2, X } from "lucide-react";
import { addSourcingTarget, changeSourcingTarget, draftLinkedIn, findPeerCompanies, runSourcingNow, setSourcingMode, setSourcingPlan } from "@/app/actions";
import { AddTarget, OneClick, PlanSettings, PlanWords } from "@/components/SourcingForms";
import type { SourcingMode, SourcingPage, SourcingStats, Suggestion } from "@/lib/api";
import { MODE_LABEL, reasonWords, TIER_WORDS } from "@/lib/format";

/* The role's sourcing (docs/next/PLAN.md, phase 1): how often it searches, the market map, suggestions to contact,
   runs, and what each strategy cost and brought. */

export const TARGET_TIER: Record<string, string> = {
  named: "named by the hiring manager", known: "our people worked there", peer: "peer company",
  adjacent: "adjacent industry", release: "releasing talent", manual: "added by you",
};
const STOP: Record<string, string> = {
  target: "target reached", budget: "the role's budget is used up", desk_budget: "the desk's budget is used up",
  run_limit: "8 web searches this run", no_queries: "no new searches to make (each is repeated after 30 days)",
  searched: "searched", pool_only: "own pool only: web search is not set up", error: "the web search failed",
};
export const REFUSED: Record<string, string> = {
  off_limits: "at an off-limits company", stop: "asked not to be contacted", client_block: "blocked by the client",
  not_for_them: "said this kind of role isn't for them", outside_countries: "outside the role's countries",
  not_a_profile: "not a person's profile", unreadable: "profile could not be read",
};
const CHANNEL: Record<string, string> = { pool: "our own pool", exa_people: "web people search" };

const usd = (n: number) => `$${n < 1 ? n.toFixed(3) : n.toFixed(2)}`;
const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "");
const link = (profile: string) => (profile.startsWith("http") ? profile : `https://${profile}`);

function SuggestionCard({ jobId, s }: { jobId: string; s: Suggestion }) {
  return (
    <li className="personcard">
      <div className="pc-main">
        <div className="pc-head">
          <Link href={`/jobs/${jobId}/people/${s.candidate_id}`} className="pc-name">{s.name ?? "name not read"}</Link>
          <span className={`tiertag ${s.band === "priority" ? "strong" : "possible"}`}>{s.band === "priority" ? "strong" : "possible"}</span>
          {s.match_tier && s.match_tier !== "unclear" && <span className={`tiertag ${s.match_tier}`}>{TIER_WORDS[s.match_tier]}</span>}
          {s.found_by.new_to_desk ? <span className="pill">new</span> : <span className="chip small">already on the desk</span>}
        </div>
        <p className="reason">{[s.current, s.location].filter(Boolean).join(" · ") || "role and place not on the profile"}</p>
        <p className="hint">{reasonWords(s.reason)} · found by {CHANNEL[s.found_by.channel] ?? s.found_by.channel}
          {s.found_by.target ? ` at ${s.found_by.target}` : ""}{s.found_by.query ? ` ("${s.found_by.query}")` : ""}</p>
      </div>
      <div className="pc-side">
        {s.profile && <a className="btn small ghost" href={link(s.profile)} target="_blank" rel="noreferrer"><ExternalLink aria-hidden="true" />Profile</a>}
        {s.profile && (
          <form action={draftLinkedIn.bind(null, jobId, s.candidate_id)}>
            <button className="btn small primary">Draft LinkedIn message</button>
          </form>
        )}
      </div>
    </li>
  );
}

function Funnel({ stats }: { stats: SourcingStats }) {
  const t = stats.totals;
  const steps: [string, number][] = [["found", t.found], ["relevant", t.relevant], ["contacted", t.contacted], ["replied", t.replied],
    ["interested", t.interested], ["CV", t.cv], ["submitted", t.submitted], ["interviewed", t.interviewed], ["placed", t.placed]];
  return (
    <>
      <p className="funnel" aria-label="Results and spend">
        <strong>{usd(t.spend_usd)}</strong> spent →{" "}
        {steps.map(([label, n], i) => <span key={label}>{i ? " → " : ""}<strong>{n}</strong> {label}</span>)}
      </p>
      <p className="hint">
        {t.cost_per_relevant !== null && <>{usd(t.cost_per_relevant)} per relevant person</>}
        {t.cost_per_interview !== null && <> · {usd(t.cost_per_interview)} per interview</>}
        {t.cost_per_placement !== null && <> · {usd(t.cost_per_placement)} per placement</>}
      </p>
      {stats.flags.length > 0 && (
        <ul className="flags">
          {stats.flags.map((f, i) => <li key={i} className={`flag ${f.level}`}>{f.text}</li>)}
        </ul>
      )}
    </>
  );
}

export function SourcingTab({ s, stats }: { s: SourcingPage; stats: SourcingStats }) {
  const jobId = s.job_id;
  const p = s.plan;
  const live = p.targets.filter((t) => !t.removed);
  const removed = p.targets.filter((t) => t.removed);
  const lastRun = s.runs[0];
  return (
    <>
      <section className="panel">
        <div className="row spread">
          <h3><Radar aria-hidden="true" className="h-icon" />Sourcing: {MODE_LABEL[p.mode]}</h3>
          <div className="row">
            {(["daily", "weekly", "continuous", "paused"] as SourcingMode[]).filter((m) => m !== p.mode).map((m) => (
              <form key={m} action={setSourcingMode.bind(null, jobId, m)}><button className="btn small ghost">{MODE_LABEL[m]}</button></form>
            ))}
          </div>
        </div>
        <p className="sub">
          {s.strong_waiting} of {p.target} strong suggestions waiting to be contacted ·
          this month {usd(s.budget.role_spent_usd)} of {usd(s.budget.role_budget_usd)} for this role
          (desk {usd(s.budget.desk_spent_usd)} of {usd(s.budget.desk_budget_usd)})
          {p.mode === "paused" ? " · paused: choose how often it searches" : ""}
        </p>
        {!s.web_ready && <p className="warn">Web search is not set up (no Exa key in core/.env): runs search the desk&apos;s own pool only.</p>}
        <div className="row">
          {s.running ? <span className="sub" role="status">Searching now…</span>
            : <OneClick action={runSourcingNow.bind(null, jobId)} label="Search now" busy="Starting…" primary />}
          {lastRun && <span className="hint">Last run {when(lastRun.started_at)}: {STOP[lastRun.stop_reason ?? ""] ?? lastRun.status}</span>}
        </div>
        <details>
          <summary className="sub">Frequency, target and budget</summary>
          <PlanSettings action={setSourcingPlan.bind(null, jobId)} mode={p.mode} target={p.target} budget={p.monthly_budget_usd} />
        </details>
        <p className="hint">Each run goes cheapest first: people already on the desk (free), then a web search (about $0.007 each, never the
          same search twice in 30 days). It stops at the target or the budget. Everyone found goes through the same checks as an uploaded
          CV; off-limits companies, people who asked to stop and people outside the role&apos;s countries are never suggested.</p>
      </section>

      <section className="panel">
        <h3>Suggestions to contact {s.suggestions_total > 0 && <span className="pill">{s.suggestions_total}</span>}</h3>
        {s.suggestions.length === 0 ? <p className="empty">No suggestions waiting. Choose how often to search, or search now.</p> : (
          <ul className="people personcards stagger">
            {s.suggestions.map((x) => <SuggestionCard key={x.candidate_id} jobId={jobId} s={x} />)}
          </ul>
        )}
        <p className="hint">Public data only: a guide to who to contact. Their CV, contact details and permission come from them.</p>
      </section>

      <section className="panel">
        <h3>Market map</h3>
        {s.hiring && (
          <p className="sub">{s.hiring.name}{s.hiring.stage ? ` · ${s.hiring.stage}` : ""}{s.hiring.domains?.length ? ` · ${s.hiring.domains.join(", ")}` : ""}
            {s.hiring.team ? ` · ${s.hiring.team}` : ""}{s.hiring.hq ? ` · ${s.hiring.hq}` : ""}</p>
        )}
        {live.length === 0 ? <p className="empty">No target companies yet: add some, or look for peers on the web.</p> : (
          <ul className="targets">
            {live.map((t) => (
              <li key={t.company_id} className={t.off_limits ? "off" : ""}>
                <div>
                  <Link href={`/companies/${t.company_id}`}><strong>{t.name}</strong></Link>
                  {t.pinned && <span className="pill">pinned</span>}
                  <span className="chip small">{TARGET_TIER[t.tier] ?? t.tier}</span>
                  {t.off_limits && <span className="blocktag" title="Never sourced from">off-limits: {t.off_limits}</span>}
                  {t.why.filter((w) => w !== TARGET_TIER[t.tier]).length > 0 && <p className="hint">{t.why.filter((w) => w !== TARGET_TIER[t.tier]).join(" · ")}</p>}
                </div>
                <div className="row">
                  <form action={changeSourcingTarget.bind(null, jobId, t.company_id, t.pinned ? "unpin" : "pin")}>
                    <button className="btn small ghost" aria-label={t.pinned ? `Unpin ${t.name}` : `Pin ${t.name}`}>{t.pinned ? <PinOff aria-hidden="true" /> : <Pin aria-hidden="true" />}</button>
                  </form>
                  <form action={changeSourcingTarget.bind(null, jobId, t.company_id, "remove")}>
                    <button className="btn small ghost" aria-label={`Remove ${t.name}`}><X aria-hidden="true" /></button>
                  </form>
                </div>
              </li>
            ))}
          </ul>
        )}
        <AddTarget action={addSourcingTarget.bind(null, jobId)} />
        <OneClick action={findPeerCompanies.bind(null, jobId)} label="Find peer companies on the web (about a cent)" busy="Searching…" />
        {removed.length > 0 && (
          <details>
            <summary className="sub">Removed ({removed.length})</summary>
            <ul className="targets">
              {removed.map((t) => (
                <li key={t.company_id}>
                  <span>{t.name}</span>
                  <form action={changeSourcingTarget.bind(null, jobId, t.company_id, "restore")}>
                    <button className="btn small ghost"><Undo2 aria-hidden="true" />Restore</button>
                  </form>
                </li>
              ))}
            </ul>
          </details>
        )}
        <details>
          <summary className="sub">Titles and countries ({p.role_variants.length} titles{p.countries.length ? `, ${p.countries.join(", ")}` : ", any country"})</summary>
          <PlanWords action={setSourcingPlan.bind(null, jobId)} variants={p.role_variants} countries={p.countries} />
        </details>
        <p className="hint">Plan version {p.version}, by {p.changed_by}. Every change is a new version, so results can be compared before and after.</p>
      </section>

      <section className="panel">
        <div className="row spread">
          <h3>Results and spend for this role</h3>
          <Link href={`/sourcing?job=${jobId}`} className="btn small ghost">By strategy</Link>
        </div>
        <Funnel stats={stats} />
      </section>

      {s.runs.length > 0 && (
        <section className="panel">
          <h3>Runs</h3>
          <ul className="runs">
            {s.runs.map((r) => (
              <li key={r.id}>
                <div className="row">
                  <strong>{when(r.started_at)}</strong>
                  <span className="sub">{r.trigger === "manual" ? "by hand" : "scheduled"} · {r.status === "running" ? "running" : STOP[r.stop_reason ?? ""] ?? r.status}</span>
                  <span className="sub">· found {r.found} ({r.new} new) · {r.strong} strong · {usd(r.cost_usd)}</span>
                </div>
                {r.refused > 0 && <p className="hint">Not suggested: {Object.entries(r.report.refused ?? {}).map(([k, n]) => `${n} ${REFUSED[k] ?? k}`).join(" · ")}</p>}
                {(r.report.web?.queries?.length ?? 0) > 0 && (
                  <details>
                    <summary className="sub">{r.report.web!.queries.length} web searches</summary>
                    <ul className="hint">
                      {r.report.web!.queries.map((q, i) => <li key={i}>&ldquo;{q.text}&rdquo;: {q.results} results, {q.new} new, {q.strong} strong</li>)}
                    </ul>
                  </details>
                )}
                {r.error && <p className="error">{r.error}</p>}
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
