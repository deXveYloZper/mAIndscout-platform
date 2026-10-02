import type { Band, ClaimView } from "@/lib/api";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export const BAND_LABEL: Record<Band, string> = {
  priority: "Priority",
  review_later: "Review later",
  do_not_submit: "Do not submit",
};

function when(iso: string | null, precision: string): string {
  if (!iso) return "?";
  const [y, m] = iso.split("-");
  return precision === "year_only" ? y : `${MONTHS[Number(m) - 1]} ${y}`;
}

/** "Mar 2019 – present", "2015", "Jan 2016 – Feb 2019" */
export function period(c: Pick<ClaimView, "valid_from" | "valid_to" | "temporal_precision">): string {
  if (!c.valid_from && !c.valid_to) return "";
  const from = when(c.valid_from, c.temporal_precision);
  if (!c.valid_to) return `${from} – present`;
  const to = when(c.valid_to, c.temporal_precision);
  return from === to ? from : `${from} – ${to}`;
}

/** Plain words for flags. A flag is a reason to look, never a verdict. */
export function flagWords(flags: Record<string, any>): string[] {
  const out: string[] = [];
  if (flags.possible_ocr_identifier) out.push("may be a text-layer error: confirm before use");
  if (flags.possible_duplicate_stint) out.push("may be the same job as another entry");
  if (flags["concurrency.overlap_with"]) out.push("overlaps another current-looking job");
  if (flags.job_process_stale) out.push("this date has already passed");
  return out;
}

/** "no_support_for_must_have:insar" -> "no evidence of insar (must-have)" */
export function reasonWords(reason: string | null): string {
  if (!reason) return "";
  const [code, rest] = reason.split(/:(.*)/s);
  switch (code) {
    case "no_support_for_must_have":
      return `no evidence of ${rest} (must-have)`;
    case "supported":
      return `evidence of ${rest.replaceAll(",", ", ")}`;
    case "no_distinctive_requirements":
      return "job has no distinctive must-haves yet";
    case "human_override":
      return `set by hand: ${rest}`;
    default:
      return reason;
  }
}

export function summary(c: { claim_type: string; payload: Record<string, any> }): string {
  const p = c.payload;
  switch (c.claim_type) {
    case "IdentityClaim":
      return p.full_name;
    case "ContactClaim":
      return `${p.kind}: ${p.value}`;
    case "CareerStepClaim":
      return `${p.title_raw} · ${p.company?.raw_name ?? ""}`;
    case "EducationClaim":
      return [p.credential, p.field, p.institution_raw].filter(Boolean).join(" · ");
    case "SkillClaim":
      return p.raw_label;
    case "LocationClaim":
      return `${p.place_raw}${p.kind && p.kind !== "current" ? ` (${p.kind})` : ""}`;
    case "JobRequirementClaim":
      return p.text_raw;
    default:
      return JSON.stringify(p);
  }
}

const COUNTRY: Record<string, string> = {
  GB: "United Kingdom", DE: "Germany", US: "United States", NL: "Netherlands", CA: "Canada", FR: "France",
  IT: "Italy", ES: "Spain", AT: "Austria", CH: "Switzerland", IE: "Ireland", PL: "Poland", RO: "Romania", RS: "Serbia",
};

export function countryName(code: string): string {
  return COUNTRY[code] ?? code;
}


export const STATE_LABEL: Record<string, string> = { new: "new", seen: "seen", submitted: "submitted", we_passed: "we passed" };

export const PASS_REASONS: [string, string][] = [
  ["skills", "Skills"],
  ["seniority", "Seniority"],
  ["location", "Location / right to work"],
  ["compensation", "Compensation"],
  ["candidate_not_interested", "Candidate not interested"],
  ["client_rejected", "Client rejected"],
  ["duplicate", "Duplicate"],
  ["other", "Other"],
];
