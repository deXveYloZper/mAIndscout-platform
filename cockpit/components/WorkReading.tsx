import type { WorkReading } from "@/lib/api";

/* What a person's own words show of the role's confirmed work (the core-work reader, owner 2026-10-27), on a card: one
   line on its face, and each line of the work with their exact words under Details. It orders people within a band and
   never rates anyone. */

const short = (s: string, n = 52) => (s.length <= n ? s : `${s.slice(0, s.lastIndexOf(" ", n) > 20 ? s.lastIndexOf(" ", n) : n)}…`);

/** On the card's face: "shows the work" with the lines it shows, or "main work looks like" a look-alike. Nothing else. */
export function WorkTag({ w }: { w?: WorkReading | null }) {
  if (!w || w.status !== "done") return null;
  if (w.group === "looks_like") {
    const main = w.not.find((x) => x.verdict === "main");
    return main ? (
      <p className="shortof workline looks" title={`“${main.quote}”`}>
        <span className="linetag" title="Their own words show that most of their work is a job that looks like this one but is not">main work looks like</span>
        {short(main.line, 70)}
      </p>
    ) : null;
  }
  if (w.group !== "shows" || !w.work.length) return null;
  const lines = [...w.work].sort((a, b) => Number(b.central) - Number(a.central) || Number(b.verdict === "shown") - Number(a.verdict === "shown"));
  return (
    <p className="why workline shows" title={lines.map((x) => `${x.line}: “${x.quote}”`).join("\n")}>
      <span className="linetag" title="What their own words show of the role's confirmed work">shows the work</span>
      {lines.slice(0, 2).map((x) => `${short(x.line)}${x.verdict === "partly" ? " (partly)" : ""}`).join(" · ")}
      {lines.length > 2 ? ` · and ${lines.length - 2} more` : ""}
      {w.lines ? <span className="num"> ({w.work.length} of {w.lines})</span> : null}
    </p>
  );
}

/** Under Details: every line their words show, and every look-alike, each with their exact words; or why not read. */
export function WorkDetails({ w }: { w?: WorkReading | null }) {
  if (!w) return null;
  if (w.status === "queued" || w.status === "running") return <p className="hint live" role="status">Reading their work against the role…</p>;
  if (w.status === "failed") return <p className="warn">Reading their work failed{w.error ? `: ${w.error}` : ""}.</p>;
  if (w.status === "skipped") return <p className="hint">Their work was not read: {w.reason ?? "skipped"}.</p>;
  if (w.status === "stale") return <p className="hint">Read against earlier lines of the work: read again from the hiring profile.</p>;
  const from = w.source === "cv" ? "their CV" : "their public profile";
  if (!w.work.length && !w.not.length) return <p className="hint">The work: nothing in {from} shows it either way (titles never count).</p>;
  return (
    <div className="evidence workread">
      <p className="hint">The work, in {from}{w.lines ? ` (${w.work.length} of ${w.lines} lines)` : ""}:</p>
      <ul className="findings">
        {w.work.map((x, i) => (
          <li key={`w${i}`}><span className={`tag${x.verdict === "shown" ? " key" : ""}`}>{x.verdict === "shown" ? "shows" : "partly"}</span>{" "}
            {x.line}: &ldquo;{x.quote}&rdquo;</li>
        ))}
        {w.not.map((x, i) => (
          <li key={`n${i}`}><span className="tag warn">{x.verdict === "main" ? "main work: not this" : "also: not this"}</span>{" "}
            {x.line}: &ldquo;{x.quote}&rdquo;</li>
        ))}
      </ul>
    </div>
  );
}
