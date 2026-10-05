import Link from "next/link";
import { Briefcase } from "lucide-react";
import { createJob } from "@/app/actions";
import { UploadForm } from "@/components/UploadForm";
import { api, type JobSummary } from "@/lib/api";

export const metadata = { title: "Jobs" };

export default async function JobsPage({ searchParams }: { searchParams: Promise<{ erased?: string }> }) {
  const { erased } = await searchParams;
  const jobs = await api<JobSummary[]>("/v1/jobs");
  return (
    <>
      <div className="pagehead">
        <div>
          <p className="eyebrow">Work</p>
          <h1>Jobs</h1>
          <p className="sub">Open a job, drop CVs onto it, work the priority pile first.</p>
        </div>
      </div>
      {erased && <p className="ok" role="status">The person was erased and the check found nothing left.</p>}

      <section className="panel" id="new">
        <h3>New job from its advertisement</h3>
        <UploadForm action={createJob} label="Read the ad" busy="Reading the ad…" drop="Drop the job ad (PDF) here"
          hint="Requirements and dates are read; nothing is believed until you approve it." />
      </section>

      {jobs.length === 0 ? (
        <div className="empty">
          <Briefcase aria-hidden="true" style={{ width: 28, height: 28, opacity: 0.5 }} />
          <p>No jobs yet. Drop a job ad above to start.</p>
        </div>
      ) : (
        <div className="tablewrap">
          <table className="cards">
            <thead>
              <tr>
                <th>Job</th><th>Hiring company</th><th className="num">To review</th><th className="num">Priority</th>
                <th className="num hide-narrow">Later</th><th className="num">Do not submit</th>
              </tr>
            </thead>
            <tbody className="stagger">
              {jobs.map((j) => (
                <tr key={j.id} className="rowlink">
                  <td><Link href={`/jobs/${j.id}`} className="stretch">{j.title}</Link></td>
                  <td>{j.hiring_company ?? <span className="sub">not stated</span>}</td>
                  <td className="num" data-label="To review">
                    {j.to_review ? <Link href={`/inbox?job=${j.id}`} className="pill above">{j.to_review}</Link> : <span className="sub">–</span>}
                  </td>
                  <td className="num" data-label="Priority">{j.bands.priority ? <span className="bandtag priority">{j.bands.priority}</span> : <span className="sub">0</span>}</td>
                  <td className="num hide-narrow" data-label="Later">{j.bands.review_later}</td>
                  <td className="num" data-label="Do not submit">{j.bands.do_not_submit}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
