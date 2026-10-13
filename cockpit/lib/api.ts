// Server-side client for the platform API. Never import this from a client component: it reads the signed-in
// user's session from an httpOnly cookie. `server-only` makes the build fail if one tries (type-only imports are
// erased and stay allowed).
import "server-only";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

const BASE = process.env.MAINDSCOUT_API ?? "http://127.0.0.1:8765";

/** The session token (httpOnly: never readable by page scripts) and the chosen desk. */
export const SESSION_COOKIE = "ms_session";
export const DESK_COOKIE = "ms_desk";
export const TICKET_COOKIE = "ms_ticket";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function headers(extra?: HeadersInit): Promise<Headers> {
  const jar = await cookies();
  const h = new Headers(extra);
  const token = jar.get(SESSION_COOKIE)?.value;
  const desk = jar.get(DESK_COOKIE)?.value;
  if (token) h.set("Authorization", `Bearer ${token}`);
  if (desk) h.set("X-Org-Id", desk);
  return h;
}

/** Calls without a session (sign in, invite links). */
export async function apiPublic<T>(path: string, body?: unknown, forwardedFor?: string | null): Promise<T> {
  const h = new Headers({ "Content-Type": "application/json" });
  if (forwardedFor) h.set("X-Forwarded-For", forwardedFor);
  const res = await fetch(`${BASE}${path}`, { method: body === undefined ? "GET" : "POST", headers: h, cache: "no-store",
    body: body === undefined ? undefined : JSON.stringify(body) });
  if (!res.ok) throw new ApiError(res.status, await detailOf(res));
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

async function detailOf(res: Response): Promise<string> {
  let detail: unknown = res.statusText;
  try {
    detail = (await res.json()).detail ?? detail;
  } catch {}
  return typeof detail === "string" ? detail : JSON.stringify(detail);
}

export async function apiRaw(path: string, init: RequestInit = {}): Promise<Response> {
  const res = await fetch(`${BASE}${path}`, { ...init, headers: await headers(init.headers), cache: "no-store" });
  if (!res.ok) {
    const detail = await detailOf(res);
    // Not signed in, or the session ended: to sign-in. (A page-level redirect keeps the address the browser used;
    // Next's middleware redirects would turn 127.0.0.1 into localhost, which holds different cookies.)
    if (res.status === 401) redirect((await cookies()).get(SESSION_COOKIE) ? "/login?ended=1" : "/login");
    if (res.status === 403 && detail.includes("two-step")) redirect("/account?setup=1"); // an owner must set up codes first
    throw new ApiError(res.status, detail);
  }
  return res;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  return (await apiRaw(path, init)).json() as Promise<T>;
}

export async function apiJson<T>(path: string, body: unknown): Promise<T> {
  return api<T>(path, { method: "POST", body: JSON.stringify(body), headers: { "Content-Type": "application/json" } });
}

// --- shapes returned by the API (only what the cockpit reads) ------------------------------------

export type Band = "priority" | "review_later" | "do_not_submit";

export type Evidence = {
  type: string;
  document_id: string | null;
  filename: string | null;
  page: number | null;
  snippet: string | null;
  note: string | null;
  observed_as_of: string | null;
};

export type ClaimView = {
  id: string;
  claim_type: string;
  status: "proposed" | "approved" | "rejected" | "superseded" | "staged";
  payload: Record<string, any>;
  approved_view: Record<string, any> | null;
  flags: Record<string, any>;
  valid_from: string | null;
  valid_to: string | null;
  temporal_precision: string;
  evidence: Evidence[];
};

export type JobSummary = {
  id: string;
  title: string;
  hiring_company: string | null;
  state: string;
  bands: Record<Band, number>;
  archived?: number;
  to_review?: number;
};

export type PersonOnJob = {
  match_tier?: string | null;
  blocked?: boolean;
  stopped?: boolean;
  candidate_id: string;
  name: string | null;
  band: Band;
  reason: string | null;
  overridden_by: string | null;
  open_decisions: number;
  gaps?: { evidence: number; missing: number; conflict: number; question: number };
  state?: string;
  coverage?: { applicable: number; official: number; needed: number; met: boolean; words: string };
};

export type JobPage = JobSummary & {
  source_document_id: string | null;
  requirements: ClaimView[];
  process_stale: boolean;
  rematching?: boolean;
  people: Record<Band, PersonOnJob[]>;
  archived: { candidate_id: string; name: string | null; reason: string | null }[];
  coverage: { desk: string[]; from_ad: string[]; opened: string[]; names: Record<string, string> };
  stages: Record<string, number>;
  hiring: {
    company: { id: string; name: string; kind?: string | null; stage?: string | null; team?: string | null; founded?: string | null;
      hq?: string | null; domains?: string[]; status?: string | null } | null;
    intakes: { id: string; text: string; by: string; at: string | null }[];
    targets: Record<string, number>;
  };
};

export type PersonPage = {
  id: string;
  name: string | null;
  claims: Record<string, ClaimView[]>;
  jobs: { job_id: string; title: string; band: Band; reason: string | null; state?: string }[];
  documents: { id: string; filename: string | null; doc_type: "cv" | "jd" | "transcript" | "web_profile" | "other"; needs_vision: boolean; as_of: string | null }[];
  open_decisions: string[];
  archived: { at: string; reason: string | null } | null;
  coverage_override: boolean;
  profile: CareerProfile | null;
  classifications: Record<string, StepLabel>;
  freshness: { status: string; since: string | null; words: string };
  blocks: { id: string; company_id: string; company: string | null; reason: string; at: string | null; by: string;
    lifted: boolean; lift_note: string | null }[];
  relationship: { last_contacted: string | null; last_verified: string | null; tags: string[];
    timeline: { at: string | null; type: string; text: string; direction?: string | null; job?: string | null; contact?: string | null;
      by?: string | null; id?: string; removable?: boolean }[] };
  messages: MessageView[];
  client_contacts: { id: string; name: string; role: string | null; job_id: string; job: string }[];
  merged_into: string | null;
  merges: { id: string; drop_id: string; merged_by: string; merged_at: string | null; facts: number; documents: number; jobs: number }[];
  do_not_contact: { at: string | null; note: string | null } | null;
  permissions: Permission[];
  found_by: { job_id: string; job: string; channel: string; target: string | null; query: string | null; at: string | null }[];
};

export type Permission = { id: string; scope: "this_role" | "other_roles"; job_id: string | null; job: string | null;
  how: string | null; note: string | null; by: string; at: string | null };

/** Calls: one line of a Call review (what the transcript said), ticked by default. */
export type CallLine = {
  id: string;
  kind: "brief_answer" | "confirm" | "correct" | "dispute" | "new_fact" | "preference" | "ask";
  text: string;
  quote: string;
  ticked: boolean;
  outcome?: string; // a Brief answer: confirmed | not_met | noted
  result?: string; // once approved: applied | dropped | skipped: why
  note?: string;
  question?: string;
  current?: string;
  summary?: string;
  replaces?: string;
  value?: string;
  fact_type?: string;
  company?: string;
  title?: string | null;
};
export type CallReview = {
  id: string;
  candidate_id: string;
  document_id: string;
  status: "reading" | "pending" | "applied" | "dismissed" | "failed";
  error: string | null;
  filename?: string | null;
  person?: string | null;
  created_by: string;
  created_at: string | null;
  resolved_by: string | null;
  resolved_at: string | null;
  sections: { kind: CallLine["kind"]; title: string; lines: CallLine[] }[];
};
export type Preference = { claim_id: string; facet: string; strength: "must" | "prefer"; summary: string; said: string | null;
  as_of: string | null; stale: boolean };

export type MessageView = {
  id: string;
  kind: "candidate_outreach" | "follow_up" | "client_submission" | "interview_confirm" | "decline";
  to: string;
  subject: string;
  body: string;
  status: "draft" | "in_mailbox" | "sent" | "replied" | "cancelled";
  provider: string | null;
  job_id: string | null;
  follow_up_of: string | null;
  follow_up_due: string | null;
  created_at: string | null;
  sent_at: string | null;
  replied_at: string | null;
};

export type MailboxStatus = {
  connected: boolean;
  provider: "google" | "microsoft" | null;
  account: string | null;
  status: string | null;
  last_sync_at: string | null;
  google_ready: boolean;
  microsoft_ready: boolean;
};

export type Side = {
  claim_id: string;
  claim_type: string;
  status: string;
  payload: Record<string, any>;
  snippet: string | null;
  page: number | null;
  filename: string | null;
};

export type InboxItem = {
  id: string;
  kind: "revision_diff" | "duplicate_stint" | "contradiction" | "identity_note" | "ocr_contact" | "company_same";
  blocking: boolean;
  created_at: string;
  subject: { id: string; name: string | null };
  context?: Record<string, any>;
  claim_id?: string;
  old_view?: Record<string, any>;
  new_view?: Record<string, any>;
  changed_paths?: string[];
  left?: Side;
  right?: Side;
  claim?: Side;
  note?: string | null;
  possibly?: { id: string; name: string | null }[];
  document_id?: string | null;
};

export type PersonSummary = {
  id: string;
  name: string | null;
  created_at: string;
  jobs: { job_id: string; title: string; band: Band; state?: string }[];
  document_id: string | null;
  archived: string | null;
  tags: string[];
  stale: boolean;
};

export type ProcessResult = {
  status: string;
  subject_id: string | null;
  job_id: string | null;
  band: Band | null;
  reason: string | null;
  span_failures: { client_key: string; detail: string }[];
};

/** Like api(), but a 404 shows the cockpit's "not found" page instead of an error. */
export async function apiOr404<T>(path: string): Promise<T> {
  const { notFound } = await import("next/navigation");
  try {
    return await api<T>(path);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }
}

export type ProfileDimension = { label: string; reason: string; evidence: string[]; [k: string]: unknown };
export type CareerProfile = {
  dimensions: Record<string, ProfileDimension>;
  notable: { kind: string; text: string; evidence: string[] }[];
  reading: { label: string; reason: string };
  questions: string[];
  summary: string;
  rubric_version: string;
  as_of: string;
  computed_at: string | null;
};
export type StepLabel = { claim_id: string; status: string; career_claim_id: string; role_family: string; level: string | null;
  domains: string[]; signals: string[] };

export type Me = {
  id: string;
  email: string;
  name: string;
  desk: string;
  role: "owner" | "recruiter";
  desks: { id: string; name: string; role: string }[];
  two_step: boolean;
  needs_two_step: boolean;
};

export type Member = { id: string | null; email: string; name: string | null; role: string; two_step?: boolean;
  disabled?: boolean; joined?: string | null; invited?: boolean; expires_at?: string };

/** Who is signed in, or null (no redirect: the layout uses it on the sign-in page too). */
export async function currentUser(): Promise<Me | null> {
  const h = await headers();
  if (!h.get("Authorization")) return null;
  try {
    const res = await fetch(`${BASE}/v1/auth/me`, { headers: h, cache: "no-store" });
    return res.ok ? ((await res.json()) as Me) : null;
  } catch {
    return null;
  }
}

/** For extras that must never break a page (e.g. the sidebar's counts): the answer, or null on any failure. */
export async function apiOptional<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${BASE}${path}`, { headers: await headers(), cache: "no-store" });
    return res.ok ? ((await res.json()) as T) : null;
  } catch {
    return null;
  }
}


// --- the sourcing engine (docs/next/PLAN.md, phase 1) --------------------------------------------------------------

export type SourcingMode = "daily" | "weekly" | "continuous" | "paused";

export type ReleaseSignal = { kind: string; label: string; quote: string; url: string; source: string; published: string | null };

export type CompanyProfile = { domains: string[]; offering: string | null; industry: string | null; kind: string | null;
  employees: number | null; hq: string | null;
  founded: number | null; latest_round: string | null; team_countries: { country: string; n: number | null; pct: number | null }[];
  categories: string[] };

export type TargetProgress = { searches: number; results: number; known: number; relevant: number; exhausted: boolean;
  last_run_at: string | null };

export type SourcingTarget = { name: string; company_id: string; tier: string; why: string[]; source: string;
  people_on_desk: number; pinned: boolean; removed: boolean; country: string | null; website?: string; off_limits?: string | null;
  release?: ReleaseSignal | null; group: "A" | "B" | "C"; progress?: TargetProgress | null; profile?: CompanyProfile | null;
  fit?: { searched: boolean; why: string | null } };

export type TalentDna = { at: string; people: number; cost_usd: number;
  company: { id: string; name: string; employees: number | null; team_countries: { country: string; pct: number | null }[] | null };
  searches: { text: string; results: number; theirs: number }[]; titles: [string, number][]; before: [string, number][];
  feeders: { company_id: string; name: string; n: number; employees: number; kind: string | null; industry: string | null; hq: string | null }[];
  pattern: { kinds: [string, number][]; sizes: [string, number][]; domains: [string, number][] };
  talent_sources: { name: string; n: number | null }[]; departments: { department: string; n: number | null; pct: number | null }[] };

export type Widening = { why: string; empty?: boolean; options: { option: string; value: string | string[] | null; text: string }[] };

export type SourcingRunView = { id: string; trigger: string; status: string; stop_reason: string | null; found: number; new: number;
  known: number; refused: number; strong: number; cost_usd: number; error: string | null; started_at: string | null; ended_at: string | null;
  report: { pool?: { looked: number; added: number; strong: number }; refused?: Record<string, number>; plan_version?: number;
    web?: { people: number; off_target?: number;
      queries: { text: string; target: string | null; results: number; new: number; strong: number; off_target?: number }[] };
    radar?: { queries: { text: string; results: number; signals: number; companies: string[] }[]; flagged: string[]; added: string[];
      stopped: string | null }; profiles?: { companies: number; people: number }; snowball?: string[] } };

export type Suggestion = { candidate_id: string; name: string | null; band: Band; reason: string | null; match_tier: string | null;
  state: string; current: string | null; location: string | null; profile: string | null; employer: CompanyProfile | null;
  gaps?: PersonOnJob["gaps"]; coverage?: PersonOnJob["coverage"];
  found_by: { channel: string; target: string | null; tier: string | null; query: string | null; at: string | null; new_to_desk: boolean;
    at_target?: "now" | "before" | null } };

export type SourcingPage = {
  job_id: string; title: string; state: string;
  plan: { version: number; mode: SourcingMode; target: number; monthly_budget_usd: number; role_variants: string[]; countries: string[];
    targets: SourcingTarget[]; changed_by: string; changed_at: string | null; dna: TalentDna | null;
    rules: Record<string, number>; open_tiers: string[] };
  hiring: { name: string; stage?: string | null; domains?: string[]; kind?: string | null; team?: string; hq?: string } | null;
  budget: { role_spent_usd: number; role_budget_usd: number; desk_spent_usd: number; desk_budget_usd: number };
  strong_waiting: number; web_ready: boolean; running: boolean; building: boolean; widening: Widening | null;
  runs: SourcingRunView[]; suggestions: Suggestion[]; suggestions_total: number;
};

export type FunnelCounts = { found: number; new_to_desk: number; relevant: number; possible: number; contacted: number; replied: number;
  interested: number; cv: number; submitted: number; interviewed: number; offered: number; placed: number; spend_usd: number;
  cost_per_relevant: number | null; cost_per_interview: number | null; cost_per_placement: number | null };

export type SourcingStats = { job_id: string | null; since: string | null; group: string; totals: FunnelCounts;
  groups: (FunnelCounts & { key: string; label: string })[]; flags: { level: "warn" | "info" | "good"; key: string; text: string }[] };
