// Server-side client for the platform API. Never import this from a client component:
// it reads the operator token from the server environment.

const BASE = process.env.MAINDSCOUT_API ?? "http://127.0.0.1:8765";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

function headers(extra?: HeadersInit): Headers {
  const token = process.env.OPERATOR_TOKEN;
  const org = process.env.ORG_ID;
  if (!token || !org) throw new ApiError(500, "Cockpit is not configured: set OPERATOR_TOKEN and ORG_ID in cockpit/.env.local");
  const h = new Headers(extra);
  h.set("Authorization", `Bearer ${token}`);
  h.set("X-Org-Id", org);
  return h;
}

export async function apiRaw(path: string, init: RequestInit = {}): Promise<Response> {
  const res = await fetch(`${BASE}${path}`, { ...init, headers: headers(init.headers), cache: "no-store" });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {}
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
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
  jobs: { job_id: string; title: string; band: Band; reason: string | null }[];
  documents: { id: string; filename: string | null; needs_vision: boolean; as_of: string | null }[];
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
  jobs: { job_id: string; title: string; band: Band }[];
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
