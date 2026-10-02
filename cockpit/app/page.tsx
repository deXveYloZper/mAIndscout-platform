import Link from "next/link";
import { createJob } from "@/app/actions";
import { UploadForm } from "@/components/UploadForm";
import { api, type JobSummary } from "@/lib/api";

export const metadata = { title: "Jobs" };

export default async function JobsPage() {
  const jobs = await api<JobSummary[]>("/v1/jobs");
  return (
    <>
      <h1>Jobs</h1>
      <p className="sub">Open a job, drop CVs onto it, work the priority pile first.</p>

      <section className="panel">
        <h3>New job from its advertisement</h3>
        <UploadForm action={createJob} label="Read ad" busy="Reading the ad…" hint="PDF of the job ad. Requirements and dates are read; nothing is believed until you approve it." />
      </section>

      {jobs.length === 0 ? (
        <p className="empty">No jobs yet.</p>
      ) : (
        <table>
          <thead>
            <tr><th>Job</th><th>Hiring company</th><th className="num">Priority</th><th className="num">Later</th><th className="num">Do not submit</th></tr>
          </thead>
          <tbody>
            {jobs.map((j) => (
              <tr key={j.id}>
                <td><Link href={`/jobs/${j.id}`}>{j.title}</Link></td>
                <td>{j.hiring_company ?? <span className="sub">not stated</span>}</td>
                <td className="num">{j.bands.priority}</td>
                <td className="num">{j.bands.review_later}</td>
                <td className="num">{j.bands.do_not_submit}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
