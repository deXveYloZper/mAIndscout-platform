import { approveClaim, rejectClaim } from "@/app/actions";
import type { ClaimView, Evidence } from "@/lib/api";
import { flagWords, period, summary } from "@/lib/format";

export function Snippet({ ev }: { ev?: Evidence | null }) {
  if (!ev) return null;
  const where = [ev.filename, ev.page ? `p.${ev.page}` : null].filter(Boolean).join(" · ");
  return (
    <blockquote className="snippet">
      {ev.snippet ? `“${ev.snippet}”` : <em>{ev.type === "human_assertion" ? "typed by a person" : "no snippet"}</em>}
      {where && (
        <cite>
          {ev.document_id ? <a href={`/files/${ev.document_id}`} target="_blank" rel="noreferrer">{where}</a> : where}
        </cite>
      )}
      {ev.note && <span className="note">{ev.note}</span>}
    </blockquote>
  );
}

export function Status({ status }: { status: string }) {
  return <span className={`status ${status}`}>{status}</span>;
}

/** One fact: what it says, where it came from, and the two human acts. */
export function ClaimRow({ claim, path }: { claim: ClaimView; path: string }) {
  const flags = flagWords(claim.flags);
  const when = period(claim);
  return (
    <li className={`claim ${claim.status}`}>
      <div className="claim-head">
        <span className="what">{summary({ claim_type: claim.claim_type, payload: claim.approved_view ?? claim.payload })}</span>
        {when && <span className="when">{when}</span>}
        <Status status={claim.status} />
        {claim.status === "proposed" && (
          <span className="acts">
            <form action={approveClaim.bind(null, claim.id, path)}>
              <button className="btn small">Approve</button>
            </form>
            <form action={rejectClaim.bind(null, claim.id, path, "wrong")}>
              <button className="btn small ghost">Reject</button>
            </form>
          </span>
        )}
      </div>
      {flags.length > 0 && <ul className="flags">{flags.map((f) => <li key={f}>{f}</li>)}</ul>}
      <details>
        <summary>source{claim.evidence.length > 1 ? `s (${claim.evidence.length})` : ""}</summary>
        {claim.evidence.map((ev, i) => <Snippet key={i} ev={ev} />)}
      </details>
    </li>
  );
}
