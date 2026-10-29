import { addWorkLine, confirmWorkLines, editWorkLine, readPeopleAgain, readWorkLines, rejectClaim } from "@/app/actions";
import { ActForm } from "@/components/ActForm";
import { Change, Fold } from "@/components/BriefForms";
import { Refresh } from "@/components/CallsClient";
import { OneClick } from "@/components/SourcingForms";
import { WorkLineForm } from "@/components/WorkLineForms";
import type { JobPage, WorkLine, WorkLines as Lines } from "@/lib/api";

/* The role's work, line by line (the core-work reader, owner 2026-10-27: "yes build the reader"): what the hire will
   actually do, and the jobs that share its words but are different jobs. The desk proposes them; nobody is read until a
   person confirms them. They order people within a band and re-rate no one. */

function Row({ l, jobId }: { l: WorkLine; jobId: string }) {
  const [label, cls] = l.kind === "not" ? ["Not this", "anti"] : l.central ? ["The heart", "must"] : ["Work", "nice"];
  return (
    <li className="reqline">
      <span className={`st st-${cls}`}>{label}</span>
      <span className="rtext">{l.words}</span>
      <span className="rsrc">{l.status === "approved" ? "you" : "the desk"}
        {l.status === "proposed" && <span className="waiting" title="Read by the desk, waiting for your confirmation">new</span>}</span>
      <Change label="Change this line">
        <WorkLineForm action={editWorkLine.bind(null, l.id, jobId)} kind={l.kind} words={l.words} central={l.central} submit="Save" />
        <ActForm action={rejectClaim.bind(null, l.id, `/jobs/${jobId}`, "wrong")}>
          <button className="btn small ghost" title="Not this role's work: the reading stops using it">Remove this line</button>
        </ActForm>
      </Change>
    </li>
  );
}

/** How far the reading of the role's strong and possible people is, and a way to read again after the lines changed. */
function Progress({ w, jobId }: { w: Lines; jobId: string }) {
  const p = w.people;
  const bits = [`${p.read} of ${p.people} strong or possible ${p.people === 1 ? "person" : "people"} read against these lines`];
  if (p.waiting) bits.push(`${p.waiting} being read`);
  if (p.skipped) bits.push(`${p.skipped} with nothing of theirs to read`);
  const again = p.stale + p.not_read;
  return (
    <>
      {p.waiting > 0 && <Refresh every={5000} upTo={900000} />}
      <span className="sub" role="status">{bits.join(" · ")}</span>
      {again > 0 && <OneClick action={readPeopleAgain.bind(null, jobId)} label={`Read ${again} against these lines`} busy="Queueing…" />}
    </>
  );
}

export function WorkLines({ job }: { job: JobPage }) {
  const w = job.work_lines;
  const lines = w?.lines ?? [];
  const work = lines.filter((l) => l.kind === "work").sort((a, b) => Number(Boolean(b.central)) - Number(Boolean(a.central)));
  const not = lines.filter((l) => l.kind === "not");
  const waiting = lines.filter((l) => l.status === "proposed");
  return (
    <section className="panel worklines">
      <div className="row spread">
        <h3>The work, line by line</h3>
        <OneClick action={readWorkLines.bind(null, job.id)} label={lines.length ? "Read again" : "Read the work"} busy="Reading…"
          primary={!lines.length} />
      </div>
      <p className="sub">What the hire will actually do, and the jobs that share its words but are different jobs. Each strong or
        possible person&apos;s own words are read against the lines you confirm: whoever&apos;s words show the work comes first in their
        band, whoever&apos;s main work is a look-alike comes last. Titles never count, and nobody is re-rated.</p>
      {!lines.length && <p className="hint">Not read yet: the desk reads the lines with the brief, or now (about a fifth of a cent).</p>}
      {work.length > 0 && <ul className="reqs grouped">{work.map((l) => <Row key={l.id} l={l} jobId={job.id} />)}</ul>}
      {not.length > 0 && (
        <>
          <p className="sub notwork">Not this work: the same words, a different job</p>
          <ul className="reqs grouped">{not.map((l) => <Row key={l.id} l={l} jobId={job.id} />)}</ul>
        </>
      )}
      <Fold className="fold" summary={<>Add a line in your own words</>}>
        <div className="addlines">
          <WorkLineForm action={addWorkLine.bind(null, job.id, "work")} kind="work" submit="Add to the work" />
          <WorkLineForm action={addWorkLine.bind(null, job.id, "not")} kind="not" submit="Add as not this work" />
        </div>
      </Fold>
      <div className="confirmbar">
        {waiting.length > 0 ? (
          <>
            <span className="sub">{waiting.length} of these {lines.length} {waiting.length === 1 ? "was" : "were"} read by the desk
              and {waiting.length === 1 ? "waits" : "wait"} for you: nobody is read until you confirm</span>
            <OneClick action={confirmWorkLines.bind(null, job.id, waiting.map((l) => l.id))}
              label={waiting.length === 1 ? "Confirm this line" : `Confirm these ${waiting.length} lines`} busy="Confirming…" primary />
          </>
        ) : w?.version ? <Progress w={w} jobId={job.id} />
          : lines.length > 0 ? <span className="sub">Confirm or add one line of the work: nobody is read until then.</span> : null}
      </div>
    </section>
  );
}
