import { removeActivity } from "@/app/actions";
import { LogActivity } from "@/components/LogActivity";
import { ago } from "@/lib/format";

export type TimelineRow = { at: string | null; type: string; text: string; direction?: string | null; job?: string | null;
  contact?: string | null; by?: string | null; id?: string; removable?: boolean };

const TYPE_LABEL: Record<string, string> = {
  call: "Call", email: "Email", meeting: "Meeting", message: "Message", note: "Note", cv: "CV", band: "Band", state: "Stage",
  brief: "Brief answer", job: "Job",
};

export function Timeline({ rows, path }: { rows: TimelineRow[]; path: string }) {
  if (!rows.length) return <p className="empty">Nothing yet.</p>;
  return (
    <ul className="timeline">
      {rows.map((r, i) => (
        <li key={r.id ?? i} className={`tl ${r.type}`}>
          <span className="tl-when" title={r.at ?? ""}>{ago(r.at)}</span>
          <span className="tl-type">{TYPE_LABEL[r.type] ?? r.type}{r.direction === "in" ? " (in)" : r.direction === "out" ? " (out)" : ""}</span>
          <span className="tl-text">
            {r.text}
            {(r.contact || r.job) && <span className="sub"> · {[r.contact, r.job].filter(Boolean).join(" · ")}</span>}
            {r.by && r.by !== "system" && <span className="sub"> · {r.by}</span>}
          </span>
          {r.removable && r.id && (
            <form action={removeActivity.bind(null, r.id, path)}><button className="btn small ghost" aria-label="Remove this entry">×</button></form>
          )}
        </li>
      ))}
    </ul>
  );
}

export function Dates({ lastContacted, lastVerified, verifiedLabel = "Facts last verified" }: { lastContacted: string | null;
  lastVerified?: string | null; verifiedLabel?: string }) {
  return (
    <p className="rel-dates">
      <span>Last contacted: <strong>{lastContacted ? ago(lastContacted) : "never"}</strong></span>
      {lastVerified !== undefined && <span>{verifiedLabel}: <strong>{lastVerified ? ago(lastVerified) : "never"}</strong></span>}
    </p>
  );
}

export { LogActivity };
