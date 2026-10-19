"use client";

import { useActionState, useState } from "react";
import type { FormState } from "@/app/actions";
import { DOMAINS, EMPLOYER_KIND_LABEL, FAMILY_LABEL, KIND_LABEL, LEVELS, STRENGTHS } from "@/lib/format";

const KINDS = ["role", "employer", "domain", "target_company", "employment", "skill", "other"];
/** Company size in people (the desk's size bands, owner 2026-10-19): "min-max", either end open. */
const SIZES: [string, string][] = [["", "any size"], ["-50", "up to 50 people"], ["-250", "up to 250 people"],
  ["-500", "up to 500 people"], ["501-5000", "501-5,000 people"], ["5001-", "over 5,000 people"]];

export function AddRequirement({ action }: { action: (s: FormState, f: FormData) => Promise<FormState> }) {
  const [state, formAction, pending] = useActionState(action, {});
  const [kind, setKind] = useState("employer");
  return (
    <form action={formAction} className="addreq">
      <div className="row">
        <select name="category" value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Kind of requirement">
          {KINDS.map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
        </select>
        <select name="strength" defaultValue="strong_plus" aria-label="How much it matters">
          {STRENGTHS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <input name="text_raw" aria-label="Requirement" size={28}
          placeholder={kind === "target_company" ? "companies, comma separated" : kind === "skill" ? "skill, e.g. typescript" : "in a few words"} />
      </div>
      {kind === "role" && (
        <div className="row">
          <select name="role_family" aria-label="Kind of work">
            {Object.entries(FAMILY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <select name="level" aria-label="Level" defaultValue="">
            <option value="">any level</option>
            {LEVELS.map((l) => <option key={l}>{l}</option>)}
          </select>
          <input name="min_years" type="number" min={0} step={1} aria-label="Minimum years" placeholder="years" size={5} />
        </div>
      )}
      {kind === "employer" && (
        <fieldset className="row">
          <legend className="sub">Background</legend>
          {Object.entries(EMPLOYER_KIND_LABEL).map(([k, v]) => (
            <label key={k}><input type="checkbox" name="employer_kinds" value={k} /> {v}</label>
          ))}
          <select name="staff" defaultValue="" aria-label="Company size">
            {SIZES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </fieldset>
      )}
      {kind === "target_company" && (
        <label className="sub">If not wanted, people who left it within
          <input name="recent_months" type="number" min={0} max={60} step={1} size={3} placeholder="6" aria-label="Months" /> months count as from it
        </label>
      )}
      {kind === "domain" && (
        <div className="row">
          <select name="domains" multiple size={5} aria-label="Industries">
            {DOMAINS.map((d) => <option key={d}>{d}</option>)}
          </select>
          <input name="company_words" size={30} aria-label="Industry as companies describe themselves"
            placeholder="or as companies describe themselves: leather goods, bags" />
        </div>
      )}
      {kind === "employment" && (
        <select name="employment" aria-label="Employment">
          <option value="permanent">permanent</option>
          <option value="contract">contract</option>
          <option value="either">either</option>
        </select>
      )}
      <button className="btn small" disabled={pending}>{pending ? "Adding…" : "Add requirement"}</button>
      {state.error && <span className="error" role="alert">{state.error}</span>}
      {state.message && <span className="sub" role="status">{state.message}</span>}
    </form>
  );
}
