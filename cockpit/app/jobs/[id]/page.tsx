import Link from "next/link";
import { dropCvs, overrideBand } from "@/app/actions";
import { Snippet } from "@/components/Claim";
import { UploadForm } from "@/components/UploadForm";
import { api, type Band, type JobPage, type PersonOnJob } from "@/lib/api";
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
  const job = await api<JobPage>(`/v1/jobs/${id}`);
  const must = job.requirements.filter((r) => r.payload.category !== "process");
  const dates = job.requirements.filter((r) => r.payload.category === "process");

  return (
    <>
      <h1>{job.title}</h1>
      <p className="sub">{job.hiring_company ?? "Hiring company not stated"} · <Link href={`/inbox?job=${job.id}`}>Inbox for this job</Link></p>
      {job.process_stale && (
        <p className="warn">This posting&apos;s own process dates have passed. Confirm it is still open before submitting anyone.</p>
      )}

      <section className="panel">
        <h3>Drop CVs onto this job</h3>
        <UploadForm action={dropCvs.bind(null, job.id)} multiple label="Read and band" busy="Reading CVs… (about 15 s each)"
          hint="Every file is read. Each person is placed in a band against this job. A band is not a score." />
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
