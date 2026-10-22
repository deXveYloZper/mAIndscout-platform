import Link from "next/link";
import { api, type LogLine } from "@/lib/api";

export const metadata = { title: "Activity" };

// What the desk did, newest first (owner, 2026-10-22: "logs that are easy to track, what buttons do, what is
// happening, so errors are easier to read ... what is searched, what prompts do we ask xAI").
const KINDS: [string, string][] = [["", "Everything"], ["button", "Buttons"], ["step", "The desk's steps"], ["task", "Tasks"],
  ["search", "Web searches"], ["model", "Model calls and prompts"], ["error", "Errors"]];
const KIND_LABEL: Record<LogLine["kind"], string> = { button: "button", step: "step", task: "task", search: "search", model: "model", error: "error" };

function href(sp: Record<string, string | undefined>, change: Record<string, string | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries({ ...sp, ...change })) if (v) q.set(k, v);
  const s = q.toString();
  return `/activity${s ? `?${s}` : ""}`;
}

function time(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function Detail({ d }: { d: Record<string, unknown> }) {
  const text = (k: string) => (typeof d[k] === "string" ? (d[k] as string) : null);
  const rest = Object.fromEntries(Object.entries(d).filter(([k]) => !["system", "input", "answer", "trace", "stack"].includes(k)));
  return (
    <div className="logdetail">
      {text("system") && <><p className="mini">Instructions given to the model</p><pre>{text("system")}</pre></>}
      {text("input") && <><p className="mini">What it was asked</p><pre>{text("input")}</pre></>}
      {text("answer") && <><p className="mini">What it answered</p><pre>{text("answer")}</pre></>}
      {(text("trace") || text("stack")) && <><p className="mini">Trace</p><pre>{text("trace") || text("stack")}</pre></>}
      {Object.keys(rest).length > 0 && <pre>{JSON.stringify(rest, null, 2)}</pre>}
    </div>
  );
}

export default async function ActivityPage({ searchParams }: {
  searchParams: Promise<{ job?: string; kind?: string; level?: string; q?: string }>;
}) {
  const sp = await searchParams;
  const q = new URLSearchParams({ limit: "300" });
  if (sp.job) q.set("job_id", sp.job);
  if (sp.kind) q.set("kind", sp.kind);
  if (sp.level) q.set("level", sp.level);
  if (sp.q) q.set("q", sp.q);
  const rows = await api<LogLine[]>(`/v1/activity?${q.toString()}`);
  const job = sp.job ? rows.find((r) => r.job)?.job : null;
  return (
    <>
      <h1>Activity</h1>
      <p className="sub">What the desk did, newest first: buttons pressed, its own steps, tasks, every web search and every model call
        with its prompt (a person&apos;s own text, such as a CV, is never shown here), and every error with its trace. Kept 30 days.</p>
      <section className="panel">
        <div className="row wrap">
          {KINDS.map(([k, label]) => (
            <Link key={k || "all"} className={`btn small${(sp.kind || "") === k && !sp.level ? " primary" : " ghost"}`}
                  href={href(sp, { kind: k || undefined, level: undefined })}>{label}</Link>
          ))}
          <Link className={`btn small${sp.level === "error" ? " primary" : " ghost"}`} href={href(sp, { level: "error", kind: undefined })}>Only problems</Link>
        </div>
        <form className="row" action="/activity">
          {sp.job && <input type="hidden" name="job" value={sp.job} />}
          {sp.kind && <input type="hidden" name="kind" value={sp.kind} />}
          <input name="q" defaultValue={sp.q ?? ""} placeholder="find words in the log" aria-label="Find in the log" className="grow" />
          <button className="btn small">Find</button>
        </form>
        {sp.job && <p className="hint">Only the role {job ? <strong>{job}</strong> : "chosen"} · <Link href={href(sp, { job: undefined })}>every role</Link>
          {" "}· <Link href={`/jobs/${sp.job}?tab=find`}>back to the role</Link></p>}
      </section>
      {rows.length === 0 ? <p className="empty">Nothing here yet.</p> : (
        <ol className="loglist">
          {rows.map((r) => (
            <li key={r.id} className={`logline ${r.level}`}>
              <details>
                <summary>
                  <span className="mini">{time(r.at)}</span>{" "}
                  <span className={`pill${r.level === "error" ? " danger" : r.level === "warn" ? " accent" : ""}`}>{KIND_LABEL[r.kind]}</span>{" "}
                  <span>{r.summary}</span>
                  {r.job && !sp.job && <> · <Link href={href(sp, { job: r.job_id ?? undefined })} className="hint">{r.job}</Link></>}
                  {r.actor && <span className="hint"> · {r.actor}</span>}
                </summary>
                <Detail d={r.detail} />
              </details>
            </li>
          ))}
        </ol>
      )}
    </>
  );
}
