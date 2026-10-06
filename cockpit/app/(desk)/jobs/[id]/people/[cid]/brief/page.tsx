import Link from "next/link";
import { BriefLists, ContactCard, type BriefItem, type Contact } from "@/components/BriefParts";
import { api, apiOr404 } from "@/lib/api";

export const metadata = { title: "Brief" };

type Brief = { available: boolean; reason?: string; items: BriefItem[]; contacts?: Contact[];
  header?: { summary: string | null; reading: string | null; band: string; tier: string | null; why: string | null } };
type GapHead = { job: { id: string; title: string }; person: { id: string; name: string | null } };

export default async function BriefPage({ params, searchParams }: { params: Promise<{ id: string; cid: string }>;
  searchParams: Promise<{ force?: string }> }) {
  const { id, cid } = await params;
  const { force } = await searchParams;
  const [head, brief] = await Promise.all([
    apiOr404<GapHead>(`/v1/jobs/${id}/people/${cid}/gaps`),
    api<Brief>(`/v1/jobs/${id}/people/${cid}/brief${force ? "?force=true" : ""}`),
  ]);
  const path = `/jobs/${id}/people/${cid}/brief`;
  return (
    <>
      <div className="pagehead">
        <div>
          <p className="eyebrow">
            <Link href={`/jobs/${id}`}>{head.job.title}</Link> · <Link href={`/jobs/${id}/people/${cid}`}>gap table</Link>
          </p>
          <h1>Brief: {head.person.name ?? "name not read"}</h1>
        </div>
      </div>
      {brief.header && (
        <div className="brief-head">
          {brief.header.summary && <div>{brief.header.summary}</div>}
          {brief.header.why && <div className="sub">On the call list because: {brief.header.why}</div>}
        </div>
      )}
      <ContactCard contacts={brief.contacts ?? []} />
      <p className="hint">What to ask on the call. Every answer you capture becomes an approved fact with you as the source, and the match is updated at once. Questions about the person are asked once and count for every job. Nothing here is ever sent to anyone.</p>
      {!brief.available ? (
        <section className="panel">
          <p>{brief.reason}</p>
          {!force && <Link className="btn small" href={`${path}?force=1`}>Make a Brief anyway</Link>}
        </section>
      ) : (
        <BriefLists items={brief.items} path={path} scopes={["person", "job"]} />
      )}
    </>
  );
}
