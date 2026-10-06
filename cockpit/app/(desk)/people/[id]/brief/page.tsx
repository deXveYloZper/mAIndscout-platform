import Link from "next/link";
import { BriefLists, ContactCard, type BriefItem, type Contact } from "@/components/BriefParts";
import { api, apiOr404, type PersonPage } from "@/lib/api";

export const metadata = { title: "Brief" };

type Brief = { available: boolean; reason?: string; items: BriefItem[]; contacts: Contact[];
  header: { summary: string | null; reading: string | null } };

/** A Brief without a job: for anyone on the desk (in the pool, sent a CV, or met at an event). */
export default async function PersonBrief({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [person, brief] = await Promise.all([apiOr404<PersonPage>(`/v1/candidates/${id}`), api<Brief>(`/v1/candidates/${id}/brief`)]);
  const path = `/people/${id}/brief`;
  return (
    <>
      <div className="pagehead">
        <div>
          <p className="eyebrow"><Link href={`/people/${id}`}>{person.name ?? "name not read"}</Link> · Brief for a call</p>
          <h1>Brief: {person.name ?? "name not read"}</h1>
          {brief.header.summary && <p className="sub">{brief.header.summary}</p>}
        </div>
      </div>
      <ContactCard contacts={brief.contacts} />
      <p className="hint">
        What to ask on the call, whatever the job. Every answer becomes an approved fact with you as the source, and counts for every
        job they are matched to, now or later. Nothing here is ever sent to anyone.
        {person.jobs.length > 0 && <> For job-specific questions, open the Brief from one of their jobs.</>}
      </p>
      {!brief.available ? <section className="panel"><p>{brief.reason}</p></section> : <BriefLists items={brief.items} path={path} scopes={["person"]} />}
    </>
  );
}
