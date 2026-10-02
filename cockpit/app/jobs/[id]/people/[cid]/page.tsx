import Link from "next/link";
import { overrideBand } from "@/app/actions";
import { apiOr404, type Band } from "@/lib/api";
import { BAND_LABEL, reasonWords } from "@/lib/format";

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
  facts: { id: string; claim_type: string; status: string; snippet: string | null }[];
};

type GapPage = {
  job: { id: string; title: string; hiring_company: string | null };
  person: { id: string; name: string | null };
  band: Band;
  reason: string | null;
  overridden_by: string | null;
  counts: Record<GapRow["status"], number>;
  rows: GapRow[];
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
  const questions = page.rows.filter((r) => r.status === "question");

  return (
    <>
      <p className="sub"><Link href={`/jobs/${page.job.id}`}>{page.job.title}</Link>{page.job.hiring_company ? ` · ${page.job.hiring_company}` : ""}</p>
      <h1>{page.person.name ?? "Name not read"}</h1>
      <p className="sub">
        <span className={`bandtag ${page.band}`}>{BAND_LABEL[page.band]}</span> {reasonWords(page.reason)} ·{" "}
        <Link href={`/people/${page.person.id}`}>Full profile and facts</Link>
      </p>

      <p className="counts" aria-label="Rows by status">
        {(Object.keys(STATUS_LABEL) as GapRow["status"][]).map((s) => (
          <span key={s} className={`gapstatus ${s}`}>{STATUS_LABEL[s]}: {page.counts[s]}</span>
        ))}
      </p>
      <p className="sub">Every requirement of the job against this person&apos;s file. There is no overall score, by design: read the rows.</p>

      <div className="tablewrap">
        <table className="gaps">
          <thead>
            <tr><th>Requirement</th><th>Status</th><th>Why</th><th>From the file</th></tr>
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
                <td><span className={`gapstatus ${r.status}`}>{STATUS_LABEL[r.status]}</span></td>
                <td>{r.detail}</td>
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
            {questions.map((q) => <li key={q.requirement_id}><strong>{q.requirement}:</strong> {q.detail}</li>)}
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
