import Link from "next/link";
import { putOnJob } from "@/app/actions";
import { api, type JobSummary } from "@/lib/api";
import { DOMAINS, EMPLOYER_KIND_LABEL, FAMILY_LABEL, LEVELS, READING_WORDS } from "@/lib/format";

export const metadata = { title: "Search" };

type Result = { candidate_id: string; name: string | null; summary: string; reading: string; met?: string[];
  criteria?: { kind: string; label: string; verdict: "met" | "partly" | "missed"; detail: string }[]; met_words?: string };
type Answer = { filters?: string[]; understood?: string[]; ignored?: string[]; people: Result[] };

const MARK = { met: "✓", partly: "~", missed: "✗" } as const;
type Company = { id: string; name: string };

const PARAMS = ["family", "related", "min_years", "level", "employer", "domain", "company", "current"];

export default async function Search({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = await searchParams;
  const one = (k: string) => (Array.isArray(sp[k]) ? (sp[k] as string[])[0] : (sp[k] as string | undefined)) ?? "";
  const many = (k: string) => (Array.isArray(sp[k]) ? (sp[k] as string[]) : sp[k] ? [sp[k] as string] : []).filter(Boolean);
  const text = one("q").trim();
  const asked = !text && PARAMS.some((k) => sp[k] !== undefined);
  const q = new URLSearchParams();
  if (one("family")) q.set("family", one("family"));
  q.set("related", asked && one("related") !== "on" ? "false" : "true");
  if (one("min_years")) q.set("min_years", one("min_years"));
  if (one("level")) q.set("level", one("level"));
  many("employer").forEach((v) => q.append("employer", v));
  many("domain").forEach((v) => q.append("domain", v));
  many("company").forEach((v) => q.append("company", v));
  if (one("current") === "on") q.set("current", "true");
  const [result, jobs, companies] = await Promise.all([
    text ? api<Answer>(`/v1/search?q=${encodeURIComponent(text)}`) : asked ? api<Answer>(`/v1/search?${q}`) : Promise.resolve(null),
    api<JobSummary[]>("/v1/jobs"),
    api<Company[]>("/v1/companies"),
  ]);

  return (
    <>
      <h1>Search the desk</h1>
      <form className="searchbar" method="get" role="search">
        <input name="q" defaultValue={text} aria-label="Search people" autoFocus
          placeholder="e.g. senior devops engineer in Germany with at least 3 years working with kubernetes" />
        <button className="btn primary">Search</button>
      </form>
      <p className="hint">Write what you are looking for in your own words: kind of work, level, years, skills, where they live, background, industry, companies. Best matches come first, each with what it meets. People outside coverage are not searched; personality, culture or fit is never a criterion.</p>
      {result?.understood && (
        <p className="understood">
          Understood as: {result.understood.length ? result.understood.map((u) => <span key={u} className="chip">{u}</span>) : <em>nothing to search by: try naming a kind of work or a skill</em>}
          {result.ignored && result.ignored.length > 0 && <span className="sub"> · left out: {result.ignored.join(", ")}</span>}
        </p>
      )}
      <details className="band" open={asked}>
        <summary>Refine with filters</summary>
      <form className="panel searchform" method="get">
        <div className="row">
          <label>Kind of work{" "}
            <select name="family" defaultValue={one("family")}>
              <option value="">any</option>
              {Object.entries(FAMILY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <label><input type="checkbox" name="related" defaultChecked={!asked || one("related") === "on"} /> include related work</label>
          <label>at least <input name="min_years" type="number" min={0} step={1} defaultValue={one("min_years")} style={{ width: 60 }} /> years</label>
          <label>Level{" "}
            <select name="level" defaultValue={one("level")}>
              <option value="">any</option>
              {LEVELS.map((l) => <option key={l} value={l}>{l} or above</option>)}
            </select>
          </label>
        </div>
        <fieldset className="row">
          <legend className="sub">At least a year at</legend>
          {Object.entries(EMPLOYER_KIND_LABEL).map(([k, v]) => (
            <label key={k}><input type="checkbox" name="employer" value={k} defaultChecked={many("employer").includes(k)} /> {v}</label>
          ))}
        </fieldset>
        <div className="row">
          <label>At least a year in{" "}
            <select name="domain" defaultValue={many("domain")[0] ?? ""}>
              <option value="">any industry</option>
              {DOMAINS.map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
          </label>
          <label>Worked at{" "}
            <select name="company" defaultValue={many("company")[0] ?? ""}>
              <option value="">any company</option>
              {companies.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </label>
          <label><input type="checkbox" name="current" defaultChecked={one("current") === "on"} /> still there</label>
          <button className="btn primary">Search</button>
          <Link href="/search" className="sub">clear</Link>
        </div>
      </form>
      </details>

      {result && (
        <>
          <h2>{result.people.length} {result.people.length === 1 ? "person" : "people"}{result.filters?.length ? `: ${result.filters.join(", ")}` : text ? ", best matches first" : ""}</h2>
          {result.people.length === 0 ? <p className="empty">{text ? "Nobody on the desk meets any of this." : "Nobody on the desk meets all of these. Loosen a filter."}</p> : (
            <ul className="results-list">
              {result.people.map((p) => (
                <li key={p.candidate_id}>
                  <div>
                    <Link href={`/people/${p.candidate_id}`}>{p.name ?? "name not read"}</Link>
                    <span className="sub"> · {READING_WORDS[p.reading] ?? p.reading}</span>
                  </div>
                  <div className="sub">{p.summary}</div>
                  {p.criteria ? (
                    <div className="criteria">
                      <span className="sub">{p.met_words}:</span>{" "}
                      {p.criteria.map((c, i) => (
                        <span key={i} className={`crit ${c.verdict}`} title={c.detail}>{MARK[c.verdict]} {c.label}</span>
                      ))}
                      <div className="why">{p.criteria.filter((c) => c.verdict !== "missed").map((c) => c.detail).join(" · ")}</div>
                    </div>
                  ) : <div className="met">{(p.met ?? []).join(" · ")}</div>}
                  {jobs.length > 0 && (
                    <form action={putOnJob.bind(null, p.candidate_id)} className="row">
                      <select name="job" aria-label={`Job to put ${p.name ?? "this person"} on`} defaultValue="">
                        <option value="" disabled>Put on a job…</option>
                        {jobs.map((j) => <option key={j.id} value={j.id}>{j.title}</option>)}
                      </select>
                      <button className="btn small">Put on job</button>
                    </form>
                  )}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </>
  );
}
