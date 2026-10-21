import Link from "next/link";
import { Pin, PinOff, Radar, Undo2, X } from "lucide-react";
import { addSourcingTarget, buildStrategy, changeSourcingTarget, checkDeeper, draftLinkedIn, runSourcingNow, setSourcingMode,
  setSourcingPlan, widenSourcing } from "@/app/actions";
import { Refresh } from "@/components/CallsClient";
import { QuickLinks, Triage } from "@/components/Outreach";
import { AddTarget, OneClick, PlanSettings, PlanWords } from "@/components/SourcingForms";
import type { CardKeys, CompanyProfile, EvidenceCheck, SourcingMode, SourcingPage, SourcingStats, SourcingTarget, Suggestion, TalentDna,
  Widening } from "@/lib/api";
import { MODE_LABEL, reasonWords } from "@/lib/format";
import { ActForm } from "@/components/ActForm";

/* The role's sourcing (docs/next/PLAN.md, phase 1): how often it searches, the market map, suggestions to contact,
   runs, and what each strategy cost and brought. */

export const TARGET_TIER: Record<string, string> = {
  named: "named by the hiring manager", known: "our people worked there", peer: "peer company",
  adjacent: "adjacent industry", release: "releasing talent", manual: "added by you",
  feeder: "their people came from here", feeder_large: "large feeder", snowball: "strong candidates worked here",
  large_peer: "in the client's market, much bigger",
};
const STOP: Record<string, string> = {
  target: "target reached", budget: "the role's budget is used up", desk_budget: "the desk's budget is used up",
  run_limit: "8 web searches this run", no_queries: "nothing new to search: see the strategy and widening",
  searched: "searched", pool_only: "own pool only: web search is not set up", error: "the web search failed",
};
export const REFUSED: Record<string, string> = {
  off_limits: "at an off-limits company", stop: "asked not to be contacted", client_block: "blocked by the client",
  not_for_them: "said this kind of role isn't for them", outside_countries: "outside the role's countries",
  not_from: "at a company the hiring profile says not to recruit from",
  not_a_profile: "not a person's profile", unreadable: "profile could not be read",
};
const CHANNEL: Record<string, string> = { pool: "our own pool", exa_people: "web people search", exa_news: "talent-release radar" };
const TIER_NAME: Record<string, string> = {
  A: "Tier A: named by the hiring manager, and where the hiring company's people came from",
  B: "Tier B: similar companies, and where strong candidates worked before",
  C: "Tier C: very large feeders and much bigger companies in the market, companies releasing talent, adjacent industries",
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

const day = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" }) : "");
const CHANNEL_WORDS: Record<string, string> = { linkedin_invite: "LinkedIn request", linkedin_message: "LinkedIn message",
  inmail: "InMail / Recruiter", email: "email" };
const OUTCOME_WORDS: Record<string, string> = { interested: "interested", not_now: "not now", not_interested: "not interested", stop: "asked to stop" };
const PASS_WORDS: Record<string, string> = { level: "level", skills: "skills", location: "location", domain: "field", other: "other" };
const LIST_TITLE = { to_contact: "To contact", contacted: "Contacted, waiting for a reply", replied: "Replied", call_booked: "Call booked" };

/** Where the contact stands, in one line: how and when, the acceptance, the reply, the call, the follow-up. */
function trackLine(s: Suggestion): string | null {
  const t = s.contact;
  if (!t) return null;
  const bits: string[] = [];
  if (t.contacted_at) bits.push(`Contacted ${day(t.contacted_at)} by ${CHANNEL_WORDS[t.channel ?? ""] ?? t.channel}`);
  if (t.accepted_at) bits.push(`accepted ${day(t.accepted_at)}`);
  if (s.stage === "contacted" && t.follow_up_due) bits.push(s.follow_up_due ? "follow-up due now" : `follow up ${day(t.follow_up_due)} if no reply`);
  if (t.reply) {
    const said = t.reply.outcome ? `: ${OUTCOME_WORDS[t.reply.outcome]}` : t.reply.source === "linkedin_email" ? " on LinkedIn (say how below)" : "";
    bits.push(`replied ${day(t.reply.at)}${said}${t.reply.check_back ? `, check back from ${day(t.reply.check_back)}` : ""}`);
  }
  if (t.stage === "call_booked") bits.push(t.call_at ? `call ${when(t.call_at)}` : "call booked");
  if (s.stage === "passed" && t.passed_for) bits.push(`not for this role: ${PASS_WORDS[t.passed_for] ?? t.passed_for}`);
  return bits.length ? bits.join(" · ") : null;
}

const OUTCOME: Record<string, string> = {
  confirmed: "Their public work supports this match", mixed: "Their public work both supports and weakens this match",
  weakened: "Their public work speaks against this match", nothing_found: "No public work about them beyond their profile",
};
/** A requirement in a few words, for a tag ("Experience at a small or mid-size brand (…)" -> "small or mid-size brand"). */
function shortReq(text: string): string {
  const t = text.replace(/^(experience (at|in|with)|background (at|in))\s+(a |an )?/i, "").replace(/\s*\(.*?\)\s*/g, " ").trim();
  return t.length > 34 ? `${t.slice(0, 32).trimEnd()}…` : t;
}

const BECAUSE: Record<string, string> = { left_the_field: "left this kind of work", works_elsewhere_now: "works elsewhere now",
  says_otherwise: "says so themselves" };
const host = (u: string) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return u; } };

/** The deeper look at a strong match's public work: what it found, quoted, with the page it came from. */
function EvidenceLine({ jobId, s, deciding }: { jobId: string; s: Suggestion; deciding: boolean }) {
  const e: EvidenceCheck | null | undefined = s.evidence;
  if (!e) {
    return deciding && s.checkable ? (
      <ActForm action={checkDeeper.bind(null, jobId, s.candidate_id)} className="inline">
        <button className="btn small ghost" title="Their own links, then a search for their name with their company (about 1-3 cents)">Check deeper</button>
      </ActForm>
    ) : null;
  }
  if (e.status === "queued" || e.status === "running") return <p className="hint live" role="status">Checking their public work…</p>;
  if (e.status === "failed") return <p className="warn">The deeper check failed{e.error ? `: ${e.error}` : ""}.</p>;
  if (e.status === "skipped") return <p className="hint">Deeper check not run: {e.reason ?? "skipped"}.</p>;
  return (
    <div className={`evidence ${e.outcome ?? ""}`}>
      <p className="hint"><strong>{OUTCOME[e.outcome ?? ""] ?? "Checked"}</strong> ({day(e.at)}: {e.pages} of {e.looked} pages were
        theirs{e.facts_added ? `, ${e.facts_added} skill${e.facts_added === 1 ? "" : "s"} added to review` : ""}{e.usd != null ? `, ${usd(e.usd)}` : ""})</p>
      {e.findings.length > 0 && (
        <ul className="findings">
          {e.findings.map((f, i) => (
            <li key={i} className={f.effect}>
              <span className={`tag ${f.effect === "supports" ? "key" : "warn"}`}>{f.effect === "supports" ? "supports"
                : `against${f.because ? `: ${BECAUSE[f.because] ?? f.because}` : ""}`}</span>{" "}
              {f.requirement}: &ldquo;{f.quote}&rdquo; <a href={f.url} target="_blank" rel="noreferrer">{host(f.url)}</a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const EV_TAG: Record<string, string> = { confirmed: "public work supports it", mixed: "public work: mixed", weakened: "public work speaks against it" };

/** "Communication Manager · Prada Group (12,213 people) · Milan, Italy": the job, the company and its size, where. */
function MainLine({ s }: { s: Suggestion }) {
  const n = s.employer?.employees;
  if (!s.title && !s.company) return <p className="main">{[s.current, s.place ?? s.location].filter(Boolean).join(" · ") || "role and place not on the profile"}</p>;
  return (
    <p className="main">
      {s.title}{s.title && s.company ? " · " : ""}
      {s.company && <strong>{s.company}</strong>}
      {s.company && <span className="num"> ({n ? `${n.toLocaleString("en-GB")} people` : "size not known"})</span>}
      {(s.place ?? s.location) ? ` · ${s.place ?? s.location}` : ""}
    </p>
  );
}

/** A suggestion in a few lines (step E, owner 2026-10-20): one verdict, their public profile a click away, the job and
    the company's size, why, what a possible is short of, what to settle on the call, the buttons. The rest is under
    Details; nothing is gone. */
function SuggestionCard({ jobId, s, since }: { jobId: string; s: Suggestion; since?: string | null }) {
  const fresh = Boolean(since && s.found_by.at && s.found_by.at >= since);
  const track = trackLine(s);
  const deciding = s.stage === "to_review" || s.stage === "later";
  const strong = s.hint === "looks strong";
  const ev = s.evidence?.status === "done" ? s.evidence.outcome : null;
  const open = s.stage !== "passed";
  const keys: CardKeys = { candidate_id: s.candidate_id, stage: s.stage, contact: s.contact, profile: s.profile, links: s.links };
  return (
    <li className={`personcard${s.follow_up_due ? " due" : ""}`}>
      <div className="pc-main">
        <div className="pc-head">
          <Link href={`/jobs/${jobId}/people/${s.candidate_id}`} className="pc-name">{s.name ?? "name not read"}</Link>
          {deciding && (s.match_tier === "unclear"
            ? <span className="cardverdict reading" title="Their career reading is on its way: never strong before it">Being read</span>
            : <span className={`cardverdict ${strong ? "strong" : "possible"}`}
                title="The desk's reading of their profile against this role: a guide, not a band">{strong ? "Strong" : "Possible"}</span>)}
          {ev && EV_TAG[ev] && <span className={`tag ${ev === "confirmed" ? "key" : "warn"}`} title={OUTCOME[ev]}>{EV_TAG[ev]}</span>}
          <QuickLinks jobId={jobId} s={keys} />
          {s.follow_up_due && <span className="pill accent">follow up</span>}
        </div>
        <MainLine s={s} />
        {s.why && s.why.length > 0 && <p className="why">{s.why.join(" · ")}</p>}
        {open && !strong && s.short_of && s.short_of.length > 0 && <p className="shortof"><span className="linetag">short of</span>{s.short_of.join(" · ")}</p>}
        {open && s.settle?.map((x, i) => <p key={i} className="settle"><span className="linetag" title="Only the call can settle it">to settle on the call</span>{x}</p>)}
        {track && <p className="reason">{track}</p>}
        {s.contact?.reply?.text && <p className="hint">&ldquo;{s.contact.reply.text}&rdquo;</p>}
        <Triage jobId={jobId} s={keys} />
        <details className="pc-details">
          <summary>Details</summary>
          <div className="pc-more">
            <p className="hint">
              {s.reason ? reasonWords(s.reason) : null}
              {fresh && <span className="pill accent">just found</span>}
              {s.stage === "to_review" && (s.found_by.new_to_desk ? <span className="pill">new to the desk</span> : <span className="chip small">already on the desk</span>)}
            </p>
            {s.employer && <p className="hint">Works at: {facts(s.employer)}</p>}
            <p className="hint">{foundBy(s.found_by)}</p>
            {s.plus && s.plus.length > 0 && (
              <p className="hint plusline" title="The role's strong-plus items: suggestions meeting more of them come first">
                Strong plus:{" "}
                {s.plus.map((r, i) => (
                  <span key={i} className={`plustag ${r.verdict}`}>{shortReq(r.requirement)}{r.verdict === "partial" ? " (partly)" : r.verdict === "ask" ? " (ask)" : ""}</span>
                ))}
              </p>
            )}
            <EvidenceLine jobId={jobId} s={s} deciding={deciding} />
            <p className="hint"><Link href={`/jobs/${jobId}/people/${s.candidate_id}`}>Every requirement, with its evidence</Link></p>
          </div>
        </details>
      </div>
      {s.profile && (s.stage === "to_contact" || (s.stage === "contacted" && s.follow_up_due)) && (
        <div className="pc-side">
          <ActForm action={draftLinkedIn.bind(null, jobId, s.candidate_id)}>
            <button className="btn small">{s.stage === "contacted" ? "Follow-up draft" : "Draft LinkedIn message"}</button>
          </ActForm>
        </div>
      )}
    </li>
  );
}

function Cards({ jobId, rows, since }: { jobId: string; rows: Suggestion[]; since?: string | null }) {
  return <ul className="people personcards">{rows.map((x) => <SuggestionCard key={x.candidate_id} jobId={jobId} s={x} since={since} />)}</ul>;
}

/** The workflow on one panel: to review, to contact, contacted, replied, call booked; maybe later and passed folded away. */
function Workflow({ jobId, s, since }: { jobId: string; s: SourcingPage; since: string | null }) {
  const c = s.counts;
  const strong = s.suggestions.filter((x) => x.hint === "looks strong");
  const weaker = s.suggestions.filter((x) => x.hint !== "looks strong");
  const steps: [string, number][] = [["to review", c.to_review], ["to contact", c.to_contact], ["contacted", c.contacted],
    ["replied", c.replied], ["call booked", c.call_booked], ["maybe later", c.later]];
  return (
    <section className="panel">
      <h3>Suggestions</h3>
      <p className="funnel" aria-label="Where everyone is">
        {steps.map(([label, n], i) => <span key={label}>{i ? " · " : ""}<strong>{n}</strong> {label}</span>)}
        {s.follow_ups_due > 0 && <span> · <strong>{s.follow_ups_due}</strong> follow-ups due</span>}
      </p>

      <h4>To review {c.to_review > 0 && <span className="pill">{c.to_review}</span>}</h4>
      {s.suggestions.length === 0 ? <p className="empty">Nothing to review. Choose how often to search, or search now.</p> : (
        <>
          {strong.length > 0 && <Cards jobId={jobId} rows={strong} since={since} />}
          {weaker.length > 0 && (
            <details open={strong.length === 0}>
              <summary className="sub">{weaker.length} possible matches (weaker: they miss some of what the role asks for)</summary>
              <Cards jobId={jobId} rows={weaker} since={since} />
            </details>
          )}
        </>
      )}

      {(["to_contact", "contacted", "replied", "call_booked"] as const).map((k) => s.lists[k].length > 0 && (
        <div key={k}>
          <h4>{LIST_TITLE[k]} <span className="pill">{c[k]}</span></h4>
          <Cards jobId={jobId} rows={s.lists[k]} />
        </div>
      ))}
      {s.lists.later.length > 0 && (
        <details>
          <summary className="sub">Maybe later ({c.later})</summary>
          <Cards jobId={jobId} rows={s.lists.later} />
        </details>
      )}
      {s.lists.passed.length > 0 && (
        <details>
          <summary className="sub">Not for this role ({c.passed})</summary>
          <Cards jobId={jobId} rows={s.lists.passed} />
        </details>
      )}
      <details className="howto">
        <summary className="sub">How this works</summary>
        <p className="hint">Open their profile, come back, decide: reach out (they become Priority, your choice), later, or not for this
          role (the reason teaches the desk your taste). Nobody found on the web is in the role&apos;s Priority until you choose them.</p>
        <p className="hint">Public data only: a guide to who to contact. Their CV, contact details and permission come from them. A
          follow-up is due 4 days after contact without a reply. Once your mailbox is connected, LinkedIn&apos;s emails about people
          you contacted there (an accepted invitation, a message) move them on by themselves.</p>
      </details>
    </section>
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

function Note({ note }: { note: SourcingPage["strategy_note"] }) {
  if (!note) return null;
  return <p className={note.level === "error" ? "warn" : "hint"} role="status">{note.text}{note.at ? ` (${when(note.at)})` : ""}</p>;
}

function Dna({ jobId, dna, building, ready, note, built }: { jobId: string; dna: TalentDna | null; building: boolean; ready: boolean;
  note: SourcingPage["strategy_note"]; built: boolean }) {
  if (!dna) {
    return (
      <section className="panel">
        <h3>Strategy</h3>
        {!building && <Note note={note} />}
        <p className="sub">First learn where the hiring company&apos;s own people came from, then build the list of companies to search,
          in tiers, each with its reason. About $0.30, once; you review the list before any wide search.</p>
        {building ? <p className="sub" role="status">Building the strategy…</p>
          : ready ? <OneClick action={buildStrategy.bind(null, jobId)} label={built ? "Build again" : "Build the strategy"} busy="Starting…" primary={!built} />
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
      {!building && <Note note={note} />}
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
        {t.fit && !t.fit.searched && <span className="blocktag" title={t.pinned ? "Pinned: searched anyway" : "Not searched"}>{t.pinned ? "searched though " : "not searched: "}{t.fit.why}</span>}
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
  const since = lastRun?.status !== "running" ? lastRun?.started_at ?? null : null;
  return (
    <>
      {(s.running || s.building || s.suggestions.some((x) => x.evidence?.status === "queued" || x.evidence?.status === "running"))
        && <Refresh every={3000} upTo={300000} />}
      <section className="panel">
        <div className="row spread">
          <h3><Radar aria-hidden="true" className="h-icon" />Sourcing: {MODE_LABEL[p.mode]}</h3>
          <div className="row">
            {(["daily", "weekly", "continuous", "paused"] as SourcingMode[]).filter((m) => m !== p.mode).map((m) => (
              <OneClick key={m} action={setSourcingMode.bind(null, jobId, m)} label={MODE_LABEL[m]} busy="Saving…" />
            ))}
          </div>
        </div>
        <p className="sub">
          {s.strong_waiting} of {p.target} strong suggestions waiting (to review or to contact) ·
          this month {usd(s.budget.role_spent_usd)} of {usd(s.budget.role_budget_usd)} for this role
          (desk {usd(s.budget.desk_spent_usd)} of {usd(s.budget.desk_budget_usd)})
          {p.mode === "paused" ? " · paused: choose how often it searches" : ""}
        </p>
        {!s.web_ready && <p className="warn">Web search is not set up (no Exa key in core/.env): runs search the desk&apos;s own pool only.</p>}
        <div className="row">
          {s.running ? <span className="sub live" role="status"><span className="dot" aria-hidden="true" />Searching… new people appear here as soon
            as the search ends (usually under a minute)</span>
            : <OneClick action={runSourcingNow.bind(null, jobId)} label="Search now" busy="Starting…" primary />}
          {lastRun && <span className="hint">Last run {when(lastRun.started_at)}: {lastRun.stop_reason === "target" && lastRun.found === 0
            ? "did not search, the target was already reached" : STOP[lastRun.stop_reason ?? ""] ?? lastRun.status}</span>}
        </div>
        {s.strong_waiting >= p.target && (
          <p className="warn">Searching waits while {s.strong_waiting} strong suggestions are waiting to be contacted (the target is {p.target}):
            contact or pass on some, or raise the target under &ldquo;Frequency, target and budget&rdquo;.</p>
        )}
        {p.countries.length > 0 && <p className="hint">Only people living in {p.countries.join(", ")} are suggested: the role&apos;s countries,
          kept in its <Link href={`/jobs/${jobId}?tab=profile`}>hiring profile</Link> (&ldquo;where people must live&rdquo;).</p>}
        <details>
          <summary className="sub">Frequency, target and budget</summary>
          <PlanSettings action={setSourcingPlan.bind(null, jobId)} mode={p.mode} target={p.target} budget={p.monthly_budget_usd} />
        </details>
        <p className="hint">Each run goes cheapest first: people already on the desk (free), then a web search (about $0.007 each, never the
          same search twice in 30 days). It stops at the target or the budget. Everyone found goes through the same checks as an uploaded
          CV; off-limits companies, people who asked to stop and people outside the role&apos;s countries are never suggested.</p>
      </section>

      {s.widening && <WideningPanel jobId={jobId} w={s.widening} />}

      <Workflow jobId={jobId} s={s} since={since} />

      <Dna jobId={jobId} dna={p.dna} building={s.building} ready={s.web_ready} note={s.strategy_note} built={live.length > 0} />

      <section className="panel">
        <h3>Market map</h3>
        {s.hiring && (
          <p className="sub">{s.hiring.name}{s.hiring.stage ? ` · ${s.hiring.stage}` : ""}{s.hiring.domains?.length ? ` · ${s.hiring.domains.join(", ")}` : ""}
            {s.hiring.team ? ` · ${s.hiring.team}` : ""}{s.hiring.hq ? ` · ${s.hiring.hq}` : ""}</p>
        )}
        {live.length === 0 ? <p className="empty">No target companies yet: build the strategy, or add some by name.</p> : (
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
