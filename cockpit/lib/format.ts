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
    case "match": {
      const [tier, why] = rest.split(/:(.*)/s);
      return `${TIER_WORDS[tier] ?? tier}${why ? `: ${why}` : ""}`;
    }
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


// The pipeline, in order (Slice 4); the last four are endings.
export const PIPELINE: [string, string][] = [
  ["new", "new"], ["seen", "seen"], ["contacted", "contacted"], ["screened", "screened"], ["submitted", "submitted"],
  ["interviewing", "interviewing"], ["offer", "offer"], ["placed", "placed"],
  ["we_passed", "we passed"], ["withdrawn", "withdrawn"], ["client_rejected", "client rejected"],
];
export const STATE_LABEL: Record<string, string> = Object.fromEntries(PIPELINE);

export const PASS_REASONS: [string, string][] = [
  ["skills", "Skills"],
  ["seniority", "Seniority"],
  ["location", "Location / right to work"],
  ["compensation", "Compensation"],
  ["candidate_not_interested", "Candidate not interested"],
  ["duplicate", "Duplicate"],
  ["other", "Other"],
];

// Career profiles (I3): the same lists as core/maindscout/domain/profile.py.
export const FAMILY_LABEL: Record<string, string> = {
  software_engineering: "software engineering", data_ml: "data / ML", devops_infrastructure: "DevOps / infrastructure",
  security: "security", qa_testing: "QA / testing", embedded_hardware: "embedded / hardware", gis_remote_sensing: "GIS / remote sensing",
  research_science: "research / science", engineering_management: "engineering management", product_management: "product management",
  design: "design", it_support: "IT support", sales: "sales", marketing: "marketing", customer_success: "customer success",
  operations: "operations", finance: "finance", hr_recruiting: "HR / recruiting", business_consulting: "business consulting",
  hospitality: "hospitality", retail: "retail", education: "education", healthcare: "healthcare", other: "other",
};
export const LEVELS = ["intern", "junior", "mid", "senior", "lead", "principal", "manager", "head", "director", "executive", "founder"];
export const DIMENSION_LABEL: [string, string][] = [
  ["relevant_years", "Relevant experience"], ["seniority", "Seniority"], ["progression", "Progression"], ["stability", "Stability"],
  ["employer_mix", "Employers"], ["domain_exposure", "Domains"], ["contractor", "Contracting"], ["early_joiner", "Early joiner"],
  ["education", "Education"],
];
export const READING_WORDS: Record<string, string> = {
  strong: "Strong career", solid: "Solid career", developing: "Developing career", unclear: "Unclear: too little is known",
};

// Hiring profiles (I4)
export const STRENGTH_GROUPS: [string, string[]][] = [
  ["Must", ["must", "deal_breaker"]],
  ["Strong plus", ["strong_plus"]],
  ["Nice to have", ["nice"]],
  ["Not wanted", ["anti"]],
  ["Not graded yet", ["unknown"]],
];
export const STRENGTHS: [string, string][] = [["must", "must"], ["strong_plus", "strong plus"], ["nice", "nice to have"], ["anti", "not wanted"]];
export const KIND_LABEL: Record<string, string> = {
  role: "role", employer: "background", domain: "industry", target_company: "target companies", employment: "employment",
  skill: "skill", seniority: "experience", education: "education", language: "language", authorization: "authorisation",
  other: "other",
};
export const EMPLOYER_KIND_LABEL: Record<string, string> = {
  startup: "start-up", scaleup: "scale-up", large: "large company", consultancy: "consultancy / outsourcer", agency: "agency",
  public_sector: "public sector", non_profit: "non-profit",
};
export const DOMAINS = [
  "fintech", "payments", "banking", "insurance", "crypto / web3", "e-commerce", "retail", "telecommunications",
  "media / entertainment", "gaming / gambling", "healthcare", "pharma / biotech", "energy / utilities",
  "environment / water", "climate / sustainability", "aerospace / defence", "space / earth observation",
  "automotive / mobility", "logistics / supply chain", "procurement", "construction / property", "public sector",
  "education", "travel / hospitality", "marketing / advertising", "it services / consulting", "enterprise software",
  "cybersecurity", "ai / data", "agriculture / food", "manufacturing / industrial", "hr / recruiting", "legal",
  "research / academia", "non-profit", "other",
];

// Matching v2 (I5)
export const TIER_WORDS: Record<string, string> = {
  strong: "strong match", possible: "possible match", unlikely: "unlikely match", unclear: "unclear: too little known",
};
export const VERDICT_LABEL: Record<string, string> = {
  strong: "Met", partial: "Partly", gap: "Gap", against: "Not wanted", ask: "Ask", level_one_below: "Partly",
};

/** "today", "3 days ago", "5 months ago", "2 years ago" (dates in the cockpit's own words). */
export function ago(iso: string | null | undefined): string {
  if (!iso) return "unknown";
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 30) return `${days} days ago`;
  const months = Math.floor(days / 30.4);
  if (months < 12) return `${months} month${months === 1 ? "" : "s"} ago`;
  const years = Math.floor(months / 12);
  return `${years} year${years === 1 ? "" : "s"} ago`;
}

/** Which of a person's jobs to show outside the job itself. "Do not submit" is the default for anyone who doesn't fit,
 *  so it is only worth showing when something happened on that pair (they were contacted, submitted, passed, the client
 *  answered...). The job page still shows every band. */
export function jobsWorthShowing<T extends { band: string; state?: string }>(jobs: T[]): T[] {
  return jobs.filter((j) => j.band !== "do_not_submit" || !["new", "seen", undefined].includes(j.state));
}
