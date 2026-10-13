import Link from "next/link";
import { ExternalLink, Pin, PinOff, Radar, Undo2, X } from "lucide-react";
import { addSourcingTarget, buildStrategy, changeSourcingTarget, draftLinkedIn, findPeerCompanies, runSourcingNow, setSourcingMode, setSourcingPlan,
  widenSourcing } from "@/app/actions";
import { AddTarget, OneClick, PlanSettings, PlanWords } from "@/components/SourcingForms";
import type { CompanyProfile, SourcingMode, SourcingPage, SourcingStats, SourcingTarget, Suggestion, TalentDna, Widening } from "@/lib/api";
import { MODE_LABEL, reasonWords, TIER_WORDS } from "@/lib/format";

/* The role's sourcing (docs/next/PLAN.md, phase 1): how often it searches, the market map, suggestions to contact,
   runs, and what each strategy cost and brought. */

export const TARGET_TIER: Record<string, string> = {
  named: "named by the hiring manager", known: "our people worked there", peer: "peer company",
  adjacent: "adjacent industry", release: "releasing talent", manual: "added by you",
  feeder: "their people came from here", feeder_large: "large feeder", snowball: "strong candidates worked here",
};
const STOP: Record<string, string> = {
  target: "target reached", budget: "the role's budget is used up", desk_budget: "the desk's budget is used up",
  run_limit: "8 web searches this run", no_queries: "nothing new to search: see the strategy and widening",
  searched: "searched", pool_only: "own pool only: web search is not set up", error: "the web search failed",
};
export const REFUSED: Record<string, string> = {
  off_limits: "at an off-limits company", stop: "asked not to be contacted", client_block: "blocked by the client",
  not_for_them: "said this kind of role isn't for them", outside_countries: "outside the role's countries",
  not_a_profile: "not a person's profile", unreadable: "profile could not be read",
};
const CHANNEL: Record<string, string> = { pool: "our own pool", exa_people: "web people search", exa_news: "talent-release radar" };
const TIER_NAME: Record<string, string> = {
  A: "Tier A: named by the hiring manager, and where the hiring company's people came from",
  B: "Tier B: similar companies, and where strong candidates worked before",
  C: "Tier C: very large feeders, companies releasing talent, adjacent industries",
};
const KIND: Record<string, string> = { product: "product company", consultancy: "consultancy", outsourcing: "outsourcing",
  agency: "agency", public_sector: "public sector", non_profit: "non-profit", other: "other", unknown: "kind unknown" };

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** A company in facts: its markets (never "Software Development"), what kind, how big, where, its stage. */
function facts(p: CompanyProfile | null | undefined): string {
  if (!p) return "";
  const what = p.domains?.length ? cap(p.domains.join(", ")) : p.industry;
  return [what ? `${what}${p.kind && p.kind !== "product" ? ` (${KIND[p.kind] ?? p.kind})` : ""}` : null,
    p.employees ? `${p.employees.toLocaleString()} staff` : null, p.hq, p.latest_round].filter(Boolean).join(" · ");
}

function foundBy(f: Suggestion["found_by"]): string {
  if (f.channel === "pool") return "already on the desk (our own pool)";
  if (f.target) {
    const where = f.at_target === "now" ? `works at ${f.target} now` : f.at_target === "before" ? `worked at ${f.target} before` : `searched at ${f.target}`;
    return `${where} · found by "${f.query}"`;
  }
  return f.query ? `found by a country-wide search ("${f.query}")` : CHANNEL[f.channel] ?? f.channel;
}

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
        {s.employer && <p className="hint">Works at: {facts(s.employer)}</p>}
        <p className="hint">{reasonWords(s.reason)} · {foundBy(s.found_by)}</p>
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

function Dna({ jobId, dna, building, ready }: { jobId: string; dna: TalentDna | null; building: boolean; ready: boolean }) {
  if (!dna) {
    return (
      <section className="panel">
        <h3>Strategy</h3>
        <p className="sub">First learn where the hiring company&apos;s own people came from, then build the list of companies to search,
          in tiers, each with its reason. About $0.30, once; you review the list before any wide search.</p>
        {building ? <p className="sub" role="status">Building the strategy…</p>
          : ready ? <OneClick action={buildStrategy.bind(null, jobId)} label="Build the strategy" busy="Starting…" primary />
            : <p className="hint">Needs web search (Exa).</p>}
      </section>
    );
  }
  const pair = (rows: [string, number][]) => rows.map(([k, n]) => `${KIND[k] ?? k} ${n}`).join(", ");
  return (
    <section className="panel">
      <div className="row spread">
        <h3>Strategy: {dna.company.name}&apos;s talent DNA</h3>
        {building ? <span className="sub" role="status">Rebuilding…</span>
          : <OneClick action={buildStrategy.bind(null, jobId)} label="Rebuild" busy="Starting…" />}
      </div>
      <p className="sub">{dna.people} of their people found ({dna.company.employees ? `${dna.company.employees} staff in all` : "size unknown"})
        {dna.company.team_countries?.length ? ` · the team works in ${dna.company.team_countries.map((c) => `${c.country} ${c.pct}%`).join(", ")}` : ""}
        {` · built ${dna.at.slice(0, 10)} for $${dna.cost_usd.toFixed(3)}`}</p>
      <ul className="dna">
        {dna.titles.length > 0 && <li><strong>Their titles there:</strong> {dna.titles.map(([t, n]) => `${t} (${n})`).join(", ")}</li>}
        {dna.before.length > 0 && <li><strong>Just before joining:</strong> {dna.before.map(([t, n]) => `${t} (${n})`).join(", ")}</li>}
        {dna.pattern.kinds.length > 0 && <li><strong>Came from:</strong> {pair(dna.pattern.kinds)}{dna.pattern.sizes.length ? `; ${dna.pattern.sizes.map(([k, n]) => `${k} ${n}`).join(", ")}` : ""}</li>}
        {dna.pattern.domains.length > 0 && <li><strong>Their earlier companies&apos; fields:</strong> {dna.pattern.domains.map(([k]) => k).join(", ")}</li>}
        {dna.feeders.length > 0 && <li><strong>Earlier employers:</strong> {dna.feeders.map((f) => `${f.name}${f.n > 1 ? ` ×${f.n}` : ""}`).join(", ")}</li>}
        {dna.talent_sources.length > 0 && <li><strong>Exa&apos;s talent sources (whole company):</strong> {dna.talent_sources.map((t) => `${t.name}${t.n ? ` ×${t.n}` : ""}`).join(", ")}</li>}
      </ul>
      <p className="hint">Companies with two or more of their people are Tier A targets; very large ones go to Tier C. Nobody found here is
        stored: they work at your client.</p>
    </section>
  );
}

function WideningPanel({ jobId, w }: { jobId: string; w: Widening }) {
  return (
    <section className="panel widening">
      <h3>{w.empty ? "Nothing to search yet" : "Time to widen?"}</h3>
      <p className="sub">{w.why}</p>
      <ul className="targets">
        {w.options.map((o, i) => (
          <li key={i}>
            <span>{o.text}</span>
            {o.option === "must_have" ? <Link className="btn small ghost" href={`/jobs/${jobId}?tab=profile`}>Hiring profile</Link>
              : (o.option !== "country" || (Array.isArray(o.value) && o.value.length > 0)) && (
                <form action={widenSourcing.bind(null, jobId, o.option, o.value)}><button className="btn small">Choose</button></form>
              )}
          </li>
        ))}
      </ul>
      <p className="hint">The platform measures and proposes; you decide. Each choice is a new plan version, so results before and after compare.</p>
    </section>
  );
}

function TargetRow({ jobId, t }: { jobId: string; t: SourcingTarget }) {
  const pr = t.progress;
  return (
    <li className={t.off_limits ? "off" : ""}>
      <div>
        <Link href={`/companies/${t.company_id}`}><strong>{t.name}</strong></Link>
        {t.pinned && <span className="pill">pinned</span>}
        <span className="chip small">{TARGET_TIER[t.tier] ?? t.tier}</span>
        {t.off_limits && <span className="blocktag" title="Never sourced from">off-limits: {t.off_limits}</span>}
        {t.release && t.tier !== "release" && <span className="releasetag" title="Searched first while this is recent">releasing talent: {t.release.label}</span>}
        {pr && (pr.exhausted ? <span className="chip small">exhausted</span> : null)}
        {t.profile && <p className="hint">{facts(t.profile)}</p>}
        {t.why.filter((w) => w !== TARGET_TIER[t.tier]).length > 0 && <p className="hint">{t.why.filter((w) => w !== TARGET_TIER[t.tier]).join(" · ")}</p>}
        {pr && <p className="hint">{pr.searches} {pr.searches === 1 ? "search" : "searches"} · {pr.results} found · {pr.known} already known · {pr.relevant} relevant</p>}
        {t.release && t.tier !== "release" && (
          <p className="hint">&ldquo;{t.release.quote}&rdquo; <a href={t.release.url} target="_blank" rel="noreferrer">{t.release.source}</a>
            {t.release.published ? `, ${t.release.published}` : ""}</p>
        )}
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

      {s.widening && <WideningPanel jobId={jobId} w={s.widening} />}

      <section className="panel">
        <h3>Suggestions to contact {s.suggestions_total > 0 && <span className="pill">{s.suggestions_total}</span>}</h3>
        {s.suggestions.length === 0 ? <p className="empty">No suggestions waiting. Choose how often to search, or search now.</p> : (
          <ul className="people personcards stagger">
            {s.suggestions.map((x) => <SuggestionCard key={x.candidate_id} jobId={jobId} s={x} />)}
          </ul>
        )}
        <p className="hint">Public data only: a guide to who to contact. Their CV, contact details and permission come from them.</p>
      </section>

      <Dna jobId={jobId} dna={p.dna} building={s.building} ready={s.web_ready} />

      <section className="panel">
        <h3>Market map</h3>
        {s.hiring && (
          <p className="sub">{s.hiring.name}{s.hiring.stage ? ` · ${s.hiring.stage}` : ""}{s.hiring.domains?.length ? ` · ${s.hiring.domains.join(", ")}` : ""}
            {s.hiring.team ? ` · ${s.hiring.team}` : ""}{s.hiring.hq ? ` · ${s.hiring.hq}` : ""}</p>
        )}
        {live.length === 0 ? <p className="empty">No target companies yet: build the strategy, add some, or look for peers on the web.</p> : (
          (["A", "B", "C"] as const).map((g) => {
            const rows = live.filter((t) => t.group === g);
            if (!rows.length) return null;
            const open = p.open_tiers.includes(g);
            return (
              <div key={g} className="tier">
                <p className="tierhead"><strong>{TIER_NAME[g]}</strong> <span className="chip small">{open ? "searched" : "closed until you widen"}</span>
                  <span className="hint"> {rows.filter((t) => t.progress?.exhausted).length} of {rows.length} exhausted</span></p>
                <ul className="targets">{rows.map((t) => <TargetRow key={t.company_id} jobId={jobId} t={t} />)}</ul>
              </div>
            );
          })
        )}
        {p.open_tiers.includes("market") && <p className="hint">Country-wide searches by title are open.</p>}
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
                      {r.report.web!.queries.map((q, i) => (
                        <li key={i}>&ldquo;{q.text}&rdquo;: {q.results} results, {q.new} new, {q.strong} strong
                          {q.off_target ? `, ${q.off_target} not from ${q.target} (skipped)` : ""}</li>
                      ))}
                    </ul>
                  </details>
                )}
                {(r.report.radar?.queries?.length ?? 0) > 0 && (
                  <details>
                    <summary className="sub">
                      {r.report.radar!.queries.length} news {r.report.radar!.queries.length === 1 ? "search" : "searches"} (talent-release radar)
                      {r.report.radar!.added.length > 0 ? ` · added ${r.report.radar!.added.join(", ")}` : ""}
                      {r.report.radar!.flagged.length > 0 ? ` · releasing talent: ${r.report.radar!.flagged.join(", ")}` : ""}
                    </summary>
                    <ul className="hint">
                      {r.report.radar!.queries.map((q, i) => (
                        <li key={i}>&ldquo;{q.text}&rdquo;: {q.results} articles, {q.signals} {q.signals === 1 ? "signal" : "signals"}
                          {q.companies.length ? ` (${q.companies.join(", ")})` : ""}</li>
                      ))}
                    </ul>
                  </details>
                )}
                {r.report.profiles && r.report.profiles.companies > 0 && <p className="hint">Profiled {r.report.profiles.companies} employers of the {r.report.profiles.people} people added.</p>}
                {r.report.snowball && r.report.snowball.length > 0 && <p className="hint">Added to the list: {r.report.snowball.join(", ")}</p>}
                {r.error && <p className="error">{r.error}</p>}
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
