import { correctStep } from "@/app/actions";
import { StepFix } from "@/components/StepFix";
import type { ClaimView, CareerProfile as Profile, StepLabel } from "@/lib/api";
import { DIMENSION_LABEL, FAMILY_LABEL, READING_WORDS } from "@/lib/format";

/** What the career shows, dimension by dimension, from facts. No number anywhere; never personality or "fit". */
export function CareerProfile({ candidateId, path, profile, labels, careers }: {
  candidateId: string; path: string; profile: Profile | null; labels: Record<string, StepLabel>; careers: ClaimView[];
}) {
  if (!profile) {
    return (
      <section className="profile">
        <h2>Career profile</h2>
        <p className="empty">Not built yet. It is built in the background after the CV is read (people outside coverage get none).</p>
      </section>
    );
  }
  return (
    <section className="profile">
      <h2>Career profile</h2>
      <p className={`reading ${profile.reading.label}`}>
        <strong>{READING_WORDS[profile.reading.label] ?? profile.reading.label}</strong> · {profile.reading.reason}
      </p>
      <p className="sub">{profile.summary}</p>
      <div className="tablewrap">
        <table className="dims">
          <tbody>
            {DIMENSION_LABEL.map(([key, title]) => {
              const d = profile.dimensions[key];
              if (!d) return null;
              return (
                <tr key={key}>
                  <th scope="row">{title}</th>
                  <td className="nowrap">{String(d.label).replace(/_/g, " ")}</td>
                  <td>{d.reason}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {profile.notable.length > 0 && (
        <>
          <h3>Notable</h3>
          <ul>{profile.notable.map((n, i) => <li key={i}>{n.text}</li>)}</ul>
        </>
      )}
      {profile.questions.length > 0 && (
        <>
          <h3>Questions for the call</h3>
          <ul className="questions">{profile.questions.map((q, i) => <li key={i}>{q}</li>)}</ul>
        </>
      )}
      {careers.length > 0 && (
        <details className="band">
          <summary>How each job was read ({careers.length})</summary>
          <p className="hint">Kind of work and industry are read from the CV by a model; the level comes from the title words. Correct anything wrong: the profile is rebuilt at once.</p>
          <ul className="steps">
            {careers.map((c) => {
              const label = labels[c.id];
              return (
                <li key={c.id}>
                  <span className="what">{c.payload.title_raw} at {c.payload.company?.raw_name}</span>
                  {label ? (
                    <>
                      <span className="sub">
                        {FAMILY_LABEL[label.role_family] ?? label.role_family} · {label.level ?? "level not clear"}
                        {label.domains.length > 0 && <> · {label.domains.join(", ")}</>}
                        {label.status === "approved" && <> · corrected by a person</>}
                      </span>
                      <StepFix action={correctStep.bind(null, candidateId, path, c.id, label.claim_id,
                        { domains: label.domains, signals: label.signals })} family={label.role_family} level={label.level} />
                    </>
                  ) : <span className="sub">not read yet</span>}
                </li>
              );
            })}
          </ul>
        </details>
      )}
      <p className="hint">Built {profile.computed_at?.slice(0, 10)} with rubric {profile.rubric_version}. There is no overall score, by design.</p>
    </section>
  );
}
