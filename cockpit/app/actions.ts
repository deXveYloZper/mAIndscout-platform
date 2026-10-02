"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { ApiError, api, apiJson, type ProcessResult } from "@/lib/api";

export type FormState = { error?: string; message?: string };

function fail(error: unknown): FormState {
  return { error: error instanceof ApiError ? error.message : "Something went wrong. Try again." };
}

function filesOf(form: FormData): File[] {
  return form.getAll("file").filter((f): f is File => f instanceof File && f.size > 0);
}

export async function createJob(_: FormState, form: FormData): Promise<FormState> {
  const [file] = filesOf(form);
  if (!file) return { error: "Choose the job advertisement (PDF)." };
  let jobId: string | null = null;
  try {
    const body = new FormData();
    body.append("file", file);
    jobId = (await api<ProcessResult>("/v1/jobs", { method: "POST", body })).job_id;
  } catch (e) {
    return fail(e);
  }
  revalidatePath("/");
  redirect(`/jobs/${jobId}`);
}

export async function overrideBand(jobId: string, candidateId: string, form: FormData): Promise<void> {
  await apiJson(`/v1/jobs/${jobId}/people/${candidateId}/triage`, {
    band: form.get("band"),
    reason: String(form.get("reason") || "") || null,
  });
  revalidatePath(`/jobs/${jobId}`);
}

/** A repeated click (already approved, already resolved) is not an error worth a crash page: just refresh. */
async function idempotent(call: () => Promise<unknown>): Promise<void> {
  try {
    await call();
  } catch (e) {
    if (!(e instanceof ApiError) || ![404, 409, 422].includes(e.status)) throw e;
  }
}

export async function approveClaim(claimId: string, path: string): Promise<void> {
  await idempotent(() => api(`/v1/claims/${claimId}/approve`, { method: "POST" }));
  revalidatePath(path);
}

export async function rejectClaim(claimId: string, path: string, code = "wrong"): Promise<void> {
  await idempotent(() => apiJson(`/v1/claims/${claimId}/reject`, { code }));
  revalidatePath(path);
}

export async function resolveDecision(decisionId: string, action: string, claimId: string | null, path: string): Promise<void> {
  await idempotent(() => apiJson(`/v1/decisions/${decisionId}/resolve`, { action, claim_id: claimId }));
  revalidatePath(path);
}

export type DropResult = { file: string; ok: boolean; name?: string | null; band?: string | null; reason?: string | null;
  personId?: string | null; status?: string; error?: string };

/** One CV onto a job, or into the unassigned pool when jobId is null. Called once per file for live progress. */
export async function dropOneCv(jobId: string | null, form: FormData): Promise<DropResult> {
  const file = form.get("file");
  if (!(file instanceof File) || !file.size) return { file: "?", ok: false, error: "empty file" };
  try {
    const body = new FormData();
    body.append("file", file);
    const r = await api<ProcessResult>(jobId ? `/v1/jobs/${jobId}/documents` : "/v1/candidates", { method: "POST", body });
    let name: string | null = null;
    if (r.subject_id) {
      try {
        name = (await api<{ name: string | null }>(`/v1/candidates/${r.subject_id}`)).name;
      } catch {}
    }
    return { file: file.name, ok: r.status === "committed", status: r.status, band: r.band, reason: r.reason, personId: r.subject_id, name };
  } catch (e) {
    return { file: file.name, ok: false, error: e instanceof ApiError ? e.message : "failed" };
  }
}

export async function refreshAfterUpload(jobId: string | null): Promise<void> {
  revalidatePath(jobId ? `/jobs/${jobId}` : "/people");
  revalidatePath("/");
}

export async function putOnJob(candidateId: string, form: FormData): Promise<void> {
  const jobId = String(form.get("job") || "");
  if (!jobId) return;
  await apiJson(`/v1/jobs/${jobId}/people/${candidateId}`, {});
  revalidatePath(`/people/${candidateId}`);
  revalidatePath(`/jobs/${jobId}`);
  revalidatePath("/people");
}

const FACT_KINDS = ["name", "email", "phone", "linkedin"] as const;

/** A fact typed by the recruiter: born approved. Optionally replaces a claim and closes a note in the same go. */
export async function addFact(candidateId: string, path: string, replaces: string | null, closeDecision: string | null,
                              _: FormState, form: FormData): Promise<FormState> {
  const kind = String(form.get("kind") || "name") as (typeof FACT_KINDS)[number];
  const value = String(form.get("value") || "").trim();
  if (!FACT_KINDS.includes(kind)) return { error: "Unknown kind of fact." };
  if (!value) return { error: "Type a value." };
  const body =
    kind === "name"
      ? { claim_type: "IdentityClaim", payload: { full_name: value, name_variants: [] } }
      : { claim_type: "ContactClaim", payload: { kind, value, normalized: normaliseContact(kind, value) } };
  try {
    await apiJson("/v1/claims", { subject_type: "candidate", subject_id: candidateId, replaces, ...body });
    if (closeDecision) await idempotent(() => apiJson(`/v1/decisions/${closeDecision}/resolve`, { action: "acknowledge" }));
  } catch (e) {
    return fail(e);
  }
  revalidatePath(path);
  return { message: "Saved as an approved fact." };
}

function normaliseContact(kind: string, value: string): string {
  if (kind === "email") return value.toLowerCase();
  if (kind === "phone") return (value.startsWith("+") ? "+" : "") + value.replace(/\D/g, "");
  return value.toLowerCase().replace(/^(https?:\/\/)?(www\.)?/, "").split("?")[0].replace(/\/$/, "");
}

export async function correctContact(candidateId: string, replaces: string, path: string, _: FormState, form: FormData): Promise<FormState> {
  const kind = String(form.get("kind") || "email");
  const value = String(form.get("value") || "").trim();
  if (!value) return { error: "Type the correct value." };
  const normalized = normaliseContact(kind, value);
  try {
    await apiJson("/v1/claims", {
      subject_type: "candidate",
      subject_id: candidateId,
      claim_type: "ContactClaim",
      payload: { kind, value, normalized },
      replaces,
    });
  } catch (e) {
    return fail(e);
  }
  revalidatePath(path);
  return { message: "Saved as an approved contact." };
}

export async function eraseCandidate(candidateId: string, _: FormState, form: FormData): Promise<FormState> {
  if (String(form.get("confirm") || "").trim().toLowerCase() !== "forget") {
    return { error: 'Type "forget" to confirm. This cannot be undone.' };
  }
  let result: { clean: boolean; survivors: string[] };
  try {
    result = await apiJson(`/v1/subjects/candidate/${candidateId}/erase`, { reason: String(form.get("reason") || "") || null });
  } catch (e) {
    return fail(e);
  }
  if (!result.clean) {
    return { error: `Erasure did NOT complete. Still found: ${result.survivors.join("; ")}` };
  }
  revalidatePath("/");
  redirect("/?erased=1");
}


/** The recruiter knows the person has a skill the file did not show: record it as an approved fact.
 *  Bands that depend on it are recomputed by the platform, and the change appears in the pair history. */
export async function addSkill(candidateId: string, token: string, path: string): Promise<void> {
  await apiJson("/v1/claims", {
    subject_type: "candidate",
    subject_id: candidateId,
    claim_type: "SkillClaim",
    payload: { raw_label: token, normalized_skill: token.toLowerCase() },
  });
  revalidatePath(path);
}
