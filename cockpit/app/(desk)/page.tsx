import Link from "next/link";
import { ArrowRight, Briefcase, Inbox, RefreshCw, Users } from "lucide-react";
import { FlapNumber } from "@/components/FlapNumber";
import { api, currentUser } from "@/lib/api";

export const metadata = { title: "Today" };

type Today = {
  inbox: number;
  priority: number;
  stale: number;
  pool: number;
  jobs: { id: string; title: string; company: string | null; priority: number; review_later: number; to_review: number }[];
  recent: { at: string; kind: string; person: string | null; person_id: string; job?: string | null; job_id?: string; to?: string; text?: string; by: string }[];
};

const BAND: Record<string, string> = { priority: "Priority", review_later: "Review later", do_not_submit: "Do not submit" };
const STATE: Record<string, string> = {
  contacted: "Contacted", screened: "Screened", submitted: "Submitted", interviewing: "Interviewing", offer: "Offer", placed: "Placed",
  we_passed: "Passed", withdrawn: "Withdrew", client_rejected: "Client said no", seen: "Seen", new: "New",
};

function greeting(): string {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

function ago(iso: string): string {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 90) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  const d = Math.round(s / 86400);
  return d === 1 ? "yesterday" : `${d} days ago`;
}

function what(r: Today["recent"][number]): string {
  if (r.kind === "band") return `${BAND[r.to ?? ""] ?? r.to} on ${r.job ?? "a job"}`;
  if (r.kind === "state") return `${STATE[r.to ?? ""] ?? r.to} · ${r.job ?? "a job"}`;
  return `${r.kind[0]!.toUpperCase()}${r.kind.slice(1)}: ${r.text ?? ""}`;
}

export default async function TodayPage() {
  const [t, me] = await Promise.all([api<Today>("/v1/today"), currentUser()]);
  const first = me?.name.split(/\s+/)[0];
  const waiting = t.jobs.filter((j) => j.priority > 0).sort((a, b) => b.priority - a.priority);
  return (
    <>
      <div className="pagehead">
        <div>
          <p className="eyebrow">Today</p>
          <h1>{greeting()}{first ? `, ${first}` : ""}.</h1>
          <p className="sub">
            {t.inbox || t.priority
              ? "Work the priority people first, then clear what is waiting for a decision."
              : "Nothing is waiting on you. A good moment to open a new job or refresh people going stale."}
          </p>
        </div>
        <div className="actions">
          <Link href="/jobs#new" className="btn primary"><Briefcase aria-hidden="true" />New job</Link>
          <Link href="/people#add" className="btn"><Users aria-hidden="true" />Add CVs</Link>
        </div>
      </div>

      <div className="stats stagger">
        <Link href="/jobs" className="stat accent">
          <span className="label">Priority people</span>
          <span className="value"><FlapNumber value={t.priority} label="priority people" /></span>
          <span className="note">across {t.jobs.length} open job{t.jobs.length === 1 ? "" : "s"}</span>
        </Link>
        <Link href="/inbox" className="stat">
          <span className="label">Waiting for a decision</span>
          <span className="value"><FlapNumber value={t.inbox} label="cards in the inbox" /></span>
          <span className="note">{t.inbox ? "in the inbox" : "inbox clear"}</span>
        </Link>
        <Link href="/refresh" className="stat">
          <span className="label">Going stale</span>
          <span className="value"><FlapNumber value={t.stale} label="people going stale" /></span>
          <span className="note">not touched in 6 months</span>
        </Link>
        <Link href="/people?show=pool" className="stat">
          <span className="label">In the pool</span>
          <span className="value"><FlapNumber value={t.pool} label="people in the pool" /></span>
          <span className="note">on no job yet</span>
        </Link>
      </div>

      <div className="today-grid">
        <section className="panel">
          <div className="panel-head">
            <h3>Priority people, by job</h3>
            <Link href="/jobs" className="btn ghost small">All jobs <ArrowRight aria-hidden="true" /></Link>
          </div>
          {waiting.length === 0 ? (
            <p className="empty">No one is in Priority yet. Drop CVs onto a job and the best fits land here.</p>
          ) : (
            <ul className="joblines stagger">
              {waiting.map((j) => (
                <li key={j.id}>
                  <Link href={`/jobs/${j.id}`} className="jobline">
                    <span className="title">{j.title}</span>
                    <span className="mini">{j.company ?? ""}</span>
                    <span className="badges">
                      <span className="bandtag priority">{j.priority} priority</span>
                      {j.review_later > 0 && <span className="bandtag review_later">{j.review_later} later</span>}
                      {j.to_review > 0 && <span className="pill"><Inbox aria-hidden="true" style={{ width: 12, height: 12 }} /> {j.to_review}</span>}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="panel">
          <div className="panel-head">
            <h3>Recent activity</h3>
            {t.stale > 0 && <Link href="/refresh" className="btn ghost small"><RefreshCw aria-hidden="true" />Refresh list</Link>}
          </div>
          {t.recent.length === 0 ? (
            <p className="empty">Nothing yet. Activity on people and jobs shows up here.</p>
          ) : (
            <ul className="feed">
              {t.recent.map((r, i) => (
                <li key={i}>
                  <span className={`dot ${r.kind}`} aria-hidden="true" />
                  <div>
                    <Link href={`/people/${r.person_id}`}>{r.person ?? "Someone"}</Link>
                    <span className="sub"> · {what(r)}</span>
                    <span className="mini feed-when">{ago(r.at)}{r.by && r.by !== "system" ? ` · ${r.by.split("@")[0]}` : ""}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </>
  );
}
