import Link from "next/link";
import { Briefcase, FileText, MapPin, MessageSquareText, Phone } from "lucide-react";
import { addFact, bringBack, draftMessage, editMessage, eraseCandidate, liftBlock, logActivity, markMessage, messageToMailbox, putOnJob, syncMailbox,
  tagPerson, untagPerson } from "@/app/actions";
import { DraftMessage, MessageCard } from "@/components/Messages";
import { CareerProfile } from "@/components/CareerProfile";
import { Dates, LogActivity, Timeline } from "@/components/Relationship";
import { ClaimRow, Status } from "@/components/Claim";
import { EraseForm } from "@/components/EraseForm";
import { FactForm } from "@/components/FactForm";
import { api, apiOr404, type JobSummary, type MailboxStatus, type PersonPage } from "@/lib/api";
import { BAND_LABEL, jobsWorthShowing, reasonWords } from "@/lib/format";

export const metadata = { title: "Person" };

const SECTIONS: [string, string][] = [
  ["IdentityClaim", "Name"],
  ["ContactClaim", "Contacts"],
  ["CareerStepClaim", "Career"],
  ["EducationClaim", "Education"],
  ["LocationClaim", "Location"],
];
const TABS: [string, string][] = [["overview", "Overview"], ["facts", "Facts"], ["messages", "Messages"], ["timeline", "Timeline"], ["documents", "Documents"]];

function initials(name: string | null): string {
  return (name ?? "?").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]!.toUpperCase()).join("") || "?";
}

export default async function Person({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ tab?: string }> }) {
  const [{ id }, sp] = await Promise.all([params, searchParams]);
  const [person, jobs, mailbox] = await Promise.all([apiOr404<PersonPage>(`/v1/candidates/${id}`), api<JobSummary[]>("/v1/jobs"),
    api<MailboxStatus>("/v1/mailbox")]);
  const tab = TABS.some(([k]) => k === sp.tab) ? sp.tab! : "overview";
  const otherJobs = jobs.filter((j) => !person.jobs.some((p) => p.job_id === j.id));
  const path = `/people/${id}`;
  const skills = person.claims.SkillClaim ?? [];
  const live = (t: string) => (person.claims[t] ?? []).filter((c) => c.status === "proposed" || c.status === "approved");
  const hasEmail = live("ContactClaim").some((c) => c.payload.kind === "email");
  const current = live("CareerStepClaim").find((c) => !c.valid_to);
  const place = live("LocationClaim").find((c) => (c.payload.kind ?? "current") === "current");
  const toApprove = Object.values(person.claims).flat().filter((c) => c.status === "proposed").length;
  const cv = person.documents[0];

  return (
    <>
      <section className="personhead">
        <span className="bigavatar" aria-hidden="true">{initials(person.name)}</span>
        <div className="ph-main">
          <h1>{person.name ?? "Name not read"}</h1>
          <p className="ph-line">
            {current && <span><Briefcase aria-hidden="true" />{current.payload.title_raw}{current.payload.company?.raw_name ? ` at ${current.payload.company.raw_name}` : ""}</span>}
            {place && <span><MapPin aria-hidden="true" />{place.payload.place_raw}</span>}
            <span className={`freshtag ${person.freshness.status}`} title={person.freshness.words}>
              {person.freshness.status === "stale" ? `Stale · ${person.freshness.words}` : person.freshness.words}
            </span>
          </p>
          <div className="row tags">
            {person.relationship.tags.map((t) => (
              <form key={t} action={untagPerson.bind(null, person.id, t, path)} className="chipform">
                <span className="chip">{t} <button className="chip-x" aria-label={`Remove tag ${t}`}>×</button></span>
              </form>
            ))}
            <form action={tagPerson.bind(null, person.id, path)} className="row tagadd">
              <input name="tag" aria-label="Add a tag (talent pool)" placeholder="+ tag, e.g. insar-pool" size={18} />
              <button className="btn small ghost">Tag</button>
            </form>
          </div>
        </div>
        <div className="ph-actions">
          {otherJobs.length > 0 && (
            <form action={putOnJob.bind(null, person.id)} className="row">
              <select name="job" aria-label="Job to put this person on" defaultValue="">
                <option value="" disabled>Put on a job…</option>
                {otherJobs.map((j) => <option key={j.id} value={j.id}>{j.title}</option>)}
              </select>
              <button className="btn small">Put on job</button>
            </form>
          )}
          <div className="row">
            {!person.archived && <Link href={`${path}/brief`} className="btn small primary"><Phone aria-hidden="true" />Brief for a call</Link>}
            {!person.archived && <Link href={`${path}?tab=messages`} className="btn small"><MessageSquareText aria-hidden="true" />Draft a message</Link>}
            {cv && <a href={`/files/${cv.id}`} target="_blank" rel="noreferrer" className="btn small ghost"><FileText aria-hidden="true" />CV</a>}
          </div>
        </div>
      </section>

      {person.archived && (
        <div className="warn archived-note">
          Archived: {person.archived.reason ?? "outside the desk's coverage"}. No company research or profiling is spent on archived people.
          <form action={bringBack.bind(null, person.id, path)}><button className="btn small">Bring back</button></form>
        </div>
      )}
      {person.coverage_override && !person.archived && <p className="hint">Brought back by a person: the coverage rule leaves them be.</p>}
      {person.blocks.filter((b) => !b.lifted).map((b) => (
        <div key={b.id} className="warn archived-note">
          Blocked at <Link href={`/companies/${b.company_id}`}>{b.company ?? "a client"}</Link>: the client said no ({b.reason}).
          <form action={liftBlock.bind(null, b.id, path)} className="row">
            <input name="note" aria-label="Why lift the block" placeholder="why lift it" size={22} required />
            <button className="btn small">Lift block</button>
          </form>
        </div>
      ))}
      {person.open_decisions.length > 0 && (
        <p className="warn">{person.open_decisions.length} question{person.open_decisions.length > 1 ? "s" : ""} about this person wait in the <Link href="/inbox">inbox</Link>.</p>
      )}

      <nav className="tabs" aria-label="Person sections">
        {TABS.map(([k, label]) => (
          <Link key={k} href={`${path}?tab=${k}`} aria-current={tab === k ? "page" : undefined}>
            {label}
            {k === "facts" && toApprove > 0 && <span className="pill">{toApprove}</span>}
            {k === "messages" && person.messages.length > 0 && <span className="pill">{person.messages.length}</span>}
          </Link>
        ))}
      </nav>

      {tab === "overview" && (
        <>
          <section className="panel">
            <h3>Jobs</h3>
            {person.jobs.length === 0 ? <p className="sub">Not on any job yet (in the pool).</p> : jobsWorthShowing(person.jobs).length === 0 ? (
              <p className="sub">No open job on the desk matches them yet ({person.jobs.length} checked). A Brief call may tell you what they are looking for.</p>
            ) : (
              <ul className="people">
                {jobsWorthShowing(person.jobs).map((j) => (
                  <li key={j.job_id}>
                    <Link href={`/jobs/${j.job_id}/people/${person.id}`}>{j.title}</Link>
                    <span><span className={`bandtag ${j.band}`}>{BAND_LABEL[j.band]}</span></span>
                    <span className="reason">{reasonWords(j.reason)}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
          {!person.archived && (
            <CareerProfile candidateId={person.id} path={path} profile={person.profile} labels={person.classifications}
              careers={live("CareerStepClaim")} />
          )}
          <section className="panel relationship">
            <h3>Relationship</h3>
            <Dates lastContacted={person.relationship.last_contacted} lastVerified={person.relationship.last_verified} />
            {person.freshness.status === "stale" && <p className="stale-note">Stale: {person.freshness.words}. Worth a call before relying on these facts.</p>}
            <LogActivity action={logActivity.bind(null, "candidates", person.id, path)} jobs={person.jobs.map((j) => ({ id: j.job_id, title: j.title }))} />
          </section>
        </>
      )}

      {tab === "facts" && (
        <>
          <p className="sub">Facts are proposed by the machine and official only once approved.</p>
          {SECTIONS.map(([type, title]) =>
            person.claims[type]?.length ? (
              <section key={type} className="panel">
                <h3>{title}</h3>
                <ul>{person.claims[type].map((c) => <ClaimRow key={c.id} claim={c} path={path} />)}</ul>
              </section>
            ) : null,
          )}
          {skills.length > 0 && (
            <section className="panel">
              <h3>Skills ({skills.length})</h3>
              <ul className="chips">
                {skills.map((s) => (
                  <li key={s.id} title={s.evidence[0]?.snippet ?? ""}>
                    {s.payload.raw_label} {s.status !== "proposed" && <Status status={s.status} />}
                  </li>
                ))}
              </ul>
            </section>
          )}
          <section className="panel">
            <h3>Add or correct a fact</h3>
            <p className="sub">What you type is saved as approved, with you as the source. A typed email, phone or LinkedIn can be used to recognise this person in later CVs.</p>
            <FactForm action={addFact.bind(null, person.id, path, null, null)} defaultKind={person.name ? "email" : "name"} />
          </section>
        </>
      )}

      {tab === "messages" && (person.archived ? <p className="empty">No messages for archived people.</p> : (
        <section className="panel messages">
          <h3>Messages</h3>
          <p className="sub">
            Drafts use only approved facts, the job&apos;s public details and what was said on the call. Nothing is sent from here:{" "}
            {mailbox.connected
              ? <>drafts go to your {mailbox.provider === "microsoft" ? "Outlook" : "Gmail"} ({mailbox.account}) and you send them yourself.</>
              : <>copy the text, or <Link href="/mailbox">connect Gmail or Outlook</Link> to put drafts straight in your mailbox.</>}
          </p>
          <DraftMessage action={draftMessage.bind(null, person.id, path)} hasEmail={hasEmail}
            jobs={person.jobs.map((j) => ({ id: j.job_id, title: j.title }))} contacts={person.client_contacts} />
          {person.messages.length > 0 && (
            <ul className="messages-list">
              {person.messages.map((m) => (
                <MessageCard key={m.id} m={m} connected={mailbox.connected} provider={mailbox.provider}
                  edit={editMessage.bind(null, m.id, path)} toMailbox={messageToMailbox.bind(null, m.id, path)}
                  markSent={markMessage.bind(null, m.id, "sent", path)} markReplied={markMessage.bind(null, m.id, "replied", path)} />
              ))}
            </ul>
          )}
          {mailbox.connected && person.messages.some((m) => m.status === "in_mailbox" || m.status === "sent") && (
            <form action={syncMailbox.bind(null, path)}><button className="btn small">Check my mailbox now</button></form>
          )}
        </section>
      ))}

      {tab === "timeline" && (
        <section className="panel relationship">
          <h3>Timeline ({person.relationship.timeline.length})</h3>
          <LogActivity action={logActivity.bind(null, "candidates", person.id, path)} jobs={person.jobs.map((j) => ({ id: j.job_id, title: j.title }))} />
          <Timeline rows={person.relationship.timeline} path={path} />
        </section>
      )}

      {tab === "documents" && (
        <>
          <section className="panel">
            <h3>Documents</h3>
            <ul className="doclist">
              {person.documents.map((d) => (
                <li key={d.id}>
                  <FileText aria-hidden="true" />
                  <a href={`/files/${d.id}`} target="_blank" rel="noreferrer">{d.filename ?? d.id}</a>
                  <span className="sub"> · as of {d.as_of ?? "unknown"}{d.needs_vision ? " · has images or a lossy layout: the text may be incomplete" : ""}</span>
                </li>
              ))}
            </ul>
          </section>
          <EraseForm action={eraseCandidate.bind(null, person.id)} />
        </>
      )}
    </>
  );
}
