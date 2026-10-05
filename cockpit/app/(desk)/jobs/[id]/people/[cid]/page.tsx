import Link from "next/link";
import { addSkill, overrideBand, setPairState } from "@/app/actions";
import { StateControls } from "@/components/StateControls";
import { apiOr404, type Band } from "@/lib/api";
import { BAND_LABEL, reasonWords, STATE_LABEL, TIER_WORDS, VERDICT_LABEL } from "@/lib/format";

export const metadata = { title: "Person on job" };

type GapRow = {
  requirement_id: string;
  requirement: string;
  kind: string;
  strength: string;
  distinctive: boolean;
  status: "evidence" | "missing" | "conflict" | "question";
  detail: string;
  official: boolean;
  token: string | null;
  facts: { id: string; claim_type: string; status: string; snippet: string | null }[];
};

type HistoryEvent = { kind: string; from: string | null; to: string; reason: string | null; cause: Record<string, string>; actor: string; at: string };

const CAUSE_LABEL: Record<string, string> = {
  document_processed: "CV read",
  typed: "fact typed",
  approve: "fact approved",
  reject: "fact rejected",
  override: "set by hand",
  state: "status changed",
  sourced: "sourced from the desk",
  career_profile_built: "career profile built",
  hiring_profile_ad: "hiring profile read from the ad",
  hiring_profile_intake: "intake notes read",
  job_countries: "job countries changed",
};

type MatchRow = { requirement_id: string; requirement: string; kind: string; strength: string; verdict: string; detail: string };
type MatchView = { tier: string; engine: string; rules: { id: string; text: string; detail: string }[]; rows: MatchRow[] };

type GapPage = {
  job: { id: string; title: string; hiring_company: string | null };
  person: { id: string; name: string | null };
  band: Band;
  reason: string | null;
  overridden_by: string | null;
  state: string;
  counts: Record<GapRow["status"], number>;
  coverage: { applicable: number; official: number; needed: number; met: boolean; words: string };
  history: HistoryEvent[];
  rows: GapRow[];
  match: MatchView | null;
};

const STATUS_LABEL: Record<GapRow["status"], string> = {
  evidence: "Evidence",
  missing: "Missing",
  conflict: "Conflict",
  question: "Ask",
};

export default async function PersonOnJob({ params }: { params: Promise<{ id: string; cid: string }> }) {
  const { id, cid } = await params;
  const page = await apiOr404<GapPage>(`/v1/jobs/${id}/people/${cid}/gaps`);
  const verdicts = Object.fromEntries((page.match?.rows ?? []).map((v) => [v.requirement_id, v]));
  const questions = page.rows.filter((r) => (verdicts[r.requirement_id]?.verdict ?? (r.status === "question" ? "ask" : "")) === "ask");
  const path = `/jobs/${page.job.id}/people/${page.person.id}`;

  return (
    <>
      <p className="sub"><Link href={`/jobs/${page.job.id}`}>{page.job.title}</Link>{page.job.hiring_company ? ` · ${page.job.hiring_company}` : ""}</p>
      <h1>{page.person.name ?? "Name not read"}</h1>
      <p className="sub">
        <span className={`bandtag ${page.band}`}>{BAND_LABEL[page.band]}</span> {reasonWords(page.reason)} ·{" "}
        <Link href={`/people/${page.person.id}`}>Full profile and facts</Link> ·{" "}
        <Link href={`/jobs/${page.job.id}/people/${page.person.id}/brief`}>Brief for the call</Link>
      </p>

      <section className="panel">
        <StateControls state={page.state} action={setPairState.bind(null, page.job.id, page.person.id, path)} />
      </section>

      <p className="counts" aria-label="Rows by status">
        {(Object.keys(STATUS_LABEL) as GapRow["status"][]).map((s) => (
          <span key={s} className={`gapstatus ${s}`}>{STATUS_LABEL[s]}: {page.counts[s]}</span>
        ))}
      </p>
      <p className="sub">Every requirement of the job against this person&apos;s file. There is no overall score, by design: read the rows.</p>
      {page.match && (
        <section className={`panel match ${page.match.tier}`}>
          <h3>Match: {TIER_WORDS[page.match.tier] ?? page.match.tier}</h3>
          <ul className="rules">
            {page.match.rules.map((r, i) => (
              <li key={i}><strong>{r.text}</strong>{r.detail ? <span className="sub"> ({r.detail})</span> : null}</li>
            ))}
          </ul>
          <p className="hint">The tier comes from these rules, in order, applied to the verdicts below. Where someone lives or their right to work is never a reason for &quot;unlikely&quot;.</p>
        </section>
      )}
      <p className={`coverage ${page.coverage.met ? "met" : "thin"}`}>
        <strong>Official coverage:</strong> {page.coverage.words}.
        {!page.coverage.met && page.coverage.applicable > 0 && " Approve the facts behind the must-haves (on the full profile) before relying on this band."}
      </p>

      <div className="tablewrap">
        <table className="gaps">
          <thead>
            <tr><th>Requirement</th><th>Verdict</th><th>Why</th><th>From the file</th></tr>
          </thead>
          <tbody>
            {page.rows.map((r) => (
              <tr key={r.requirement_id} className={r.status}>
                <td>
                  {r.requirement}
                  <div className="tags">
                    <span className="tag">{r.strength === "unknown" ? r.kind : r.strength}</span>
                    {r.distinctive && <span className="tag key">decides the band</span>}
                  </div>
                </td>
                <td>
                  {verdicts[r.requirement_id] ? (
                    <span className={`verdict ${verdicts[r.requirement_id].verdict}`}>{VERDICT_LABEL[verdicts[r.requirement_id].verdict] ?? verdicts[r.requirement_id].verdict}</span>
                  ) : <span className={`gapstatus ${r.status}`}>{STATUS_LABEL[r.status]}</span>}
                </td>
                <td>
                  {verdicts[r.requirement_id]?.detail ?? r.detail}
                  {r.status === "missing" && r.token && (
                    <div className="row" style={{ marginTop: 6 }}>
                      {r.token.split("/").filter(Boolean).map((t) => (
                        <form key={t} action={addSkill.bind(null, page.person.id, t, path)}>
                          <button className="btn small" title="Record this skill as an approved fact; the band is recomputed">They have {t}</button>
                        </form>
                      ))}
                    </div>
                  )}
                </td>
                <td>
                  {r.facts.length === 0 ? <span className="sub">nothing</span> : (
                    <>
                      {r.facts.filter((f) => f.snippet).slice(0, 2).map((f) => (
                        <blockquote key={f.id} className="snippet">“{f.snippet}”</blockquote>
                      ))}
                      <span className={`status ${r.official ? "approved" : ""}`}>{r.official ? "approved" : "proposed, not yet approved"}</span>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {questions.length > 0 && (
        <section className="panel">
          <h3>To ask on the call ({questions.length})</h3>
          <ul className="questions">
            {questions.map((q) => <li key={q.requirement_id}><strong>{q.requirement}:</strong> {verdicts[q.requirement_id]?.detail ?? q.detail}</li>)}
          </ul>
        </section>
      )}

      {page.history.length > 0 && (
        <section>
          <h2>History</h2>
          <ul className="history">
            {page.history.map((e, i) => (
              <li key={i}>
                <span className="sub">{e.at.slice(0, 16).replace("T", " ")}</span>{" "}
                {(() => {
                  const label = (v: string) => (e.kind === "state" ? STATE_LABEL[v] : BAND_LABEL[v as Band]) ?? v;
                  return <>{e.from && e.from !== "unassigned" ? `${label(e.from)} → ` : ""}<strong>{label(e.to)}</strong></>;
                })()}
                {" "}· {CAUSE_LABEL[e.cause.act] ?? e.cause.act}{e.cause.claim_type ? ` (${e.cause.claim_type.replace("Claim", "").toLowerCase()})` : ""} · {reasonWords(e.reason)} · <span className="sub">{e.actor}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="panel">
        <h3>Change the band</h3>
        <form action={overrideBand.bind(null, page.job.id, page.person.id)} className="row">
          <select name="band" defaultValue={page.band} aria-label="Band">
            {(Object.keys(BAND_LABEL) as Band[]).map((b) => <option key={b} value={b}>{BAND_LABEL[b]}</option>)}
          </select>
          <input name="reason" placeholder="why" aria-label="Reason for changing the band" size={24} />
          <button className="btn small">Set</button>
        </form>
      </section>
    </>
  );
}
