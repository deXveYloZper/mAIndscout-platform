import Link from "next/link";
import { overrideBand } from "@/app/actions";
import { Snippet } from "@/components/Claim";
import { MultiUpload } from "@/components/MultiUpload";
import { api, apiOr404, type Band, type InboxItem, type JobPage, type PersonOnJob } from "@/lib/api";
import { BAND_LABEL, reasonWords } from "@/lib/format";

export const metadata = { title: "Job" };

function People({ jobId, people }: { jobId: string; people: PersonOnJob[] }) {
  if (!people.length) return <p className="empty">Nobody here.</p>;
  return (
    <ul className="people">
      {people.map((p) => (
        <li key={p.candidate_id}>
          <span>
            <Link href={`/people/${p.candidate_id}`}>{p.name ?? "name not read"}</Link>
            {p.open_decisions > 0 && <span className="pill">{p.open_decisions} to review</span>}
          </span>
          <span className="reason">{reasonWords(p.reason)}</span>
          <form action={overrideBand.bind(null, jobId, p.candidate_id)} className="row">
            <select name="band" defaultValue={p.band} aria-label="Band">
              {(Object.keys(BAND_LABEL) as Band[]).map((b) => <option key={b} value={b}>{BAND_LABEL[b]}</option>)}
            </select>
            <input name="reason" placeholder="why" aria-label="Reason for changing the band" size={10} />
            <button className="btn small">Set</button>
          </form>
        </li>
      ))}
    </ul>
  );
}

export default async function Job({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [job, waiting] = await Promise.all([
    apiOr404<JobPage>(`/v1/jobs/${id}`),
    api<InboxItem[]>(`/v1/inbox?job_id=${id}&band=priority`),
  ]);
  const places = job.requirements.filter((r) => r.payload.category === "location" && r.payload.strength === "unknown");
  const must = job.requirements.filter((r) => r.payload.category !== "process" && !places.includes(r));
  const dates = job.requirements.filter((r) => r.payload.category === "process");

  return (
    <>
      <h1>{job.title}</h1>
      <p className="sub">
        {job.hiring_company ?? "Hiring company not stated"} · {job.people.priority.length} priority · {job.people.review_later.length} later · {job.people.do_not_submit.length} do not submit ·{" "}
        <Link href={`/inbox?job=${job.id}`}>{waiting.length ? `${waiting.length} to review` : "inbox clear"}</Link>
      </p>
      {places.length > 0 && <p className="where">Where: {places.map((p) => p.payload.text_raw).join(" · ")}</p>}
      {job.process_stale && (
        <p className="warn">This posting&apos;s own process dates have passed. Confirm it is still open before submitting anyone.</p>
      )}

      <section className="panel">
        <h3>Drop CVs onto this job</h3>
        <MultiUpload jobId={job.id} />
      </section>

      <h2>{BAND_LABEL.priority} ({job.people.priority.length})</h2>
      <People jobId={job.id} people={job.people.priority} />

      <details className="band">
        <summary>{BAND_LABEL.review_later} ({job.people.review_later.length})</summary>
        <People jobId={job.id} people={job.people.review_later} />
      </details>
      <details className="band">
        <summary>{BAND_LABEL.do_not_submit} ({job.people.do_not_submit.length})</summary>
        <People jobId={job.id} people={job.people.do_not_submit} />
      </details>

      <h2>Requirements</h2>
      <ul className="reqs">
        {must.map((r) => (
          <li key={r.id}>
            <span className="tag">{r.payload.strength}</span>
            {r.payload.distinctive && <span className="tag key" title="Zero evidence of this puts a person in Do not submit">decides the band</span>}
            {r.payload.text_raw}
            <details><summary>source</summary><Snippet ev={r.evidence[0]} /></details>
          </li>
        ))}
      </ul>
      {dates.length > 0 && (
        <>
          <h2>Process dates</h2>
          <ul className="reqs">
            {dates.map((d) => (
              <li key={d.id}>
                {d.payload.normalized_token} · {d.payload.text_raw}
                {d.flags.job_process_stale && <span className="pill">passed</span>}
              </li>
            ))}
          </ul>
        </>
      )}
      {job.source_document_id && <p className="sub"><a href={`/files/${job.source_document_id}`} target="_blank" rel="noreferrer">Open the original ad</a></p>}
    </>
  );
}
