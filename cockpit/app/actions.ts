"use server";

import { revalidatePath } from "next/cache";
import { cookies, headers } from "next/headers";
import { redirect, unstable_rethrow } from "next/navigation";
import { ApiError, DESK_COOKIE, SESSION_COOKIE, TICKET_COOKIE, api, apiJson, apiPublic, apiRaw, type ProcessResult } from "@/lib/api";

export type FormState = { error?: string; message?: string };

function fail(error: unknown): FormState {
  unstable_rethrow(error); // "sign in again" and other redirects must not be swallowed as form errors
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
  revalidatePath("/jobs");
  redirect(`/jobs/${jobId}`);
}

export async function overrideBand(jobId: string, candidateId: string, form: FormData): Promise<FormState> {
  try {
    await apiJson(`/v1/jobs/${jobId}/people/${candidateId}/triage`, {
      band: form.get("band"),
      reason: String(form.get("reason") || "") || null,
    });
  } catch (e) {
    return fail(e);
  }
  revalidatePath(`/jobs/${jobId}`);
  return {};
}

/** A repeated click (already approved, already resolved) is not an error worth a crash page: just refresh. Used only
 *  where the cockpit cannot show a message (a button inside a client card). */
async function idempotent(call: () => Promise<unknown>): Promise<void> {
  try {
    await call();
  } catch (e) {
    if (!(e instanceof ApiError) || ![404, 409, 422].includes(e.status)) throw e;
  }
}

/** For forms (ActForm): a repeated click (already done, already gone) is quiet; a refusal for a reason is said, never
 *  swallowed (x-ray A7, 2026-10-13: an invalid strength or a refused answer used to do nothing on screen). */
async function attempt(call: () => Promise<unknown>): Promise<FormState> {
  try {
    await call();
    return {};
  } catch (e) {
    unstable_rethrow(e);
    if (e instanceof ApiError && [404, 409].includes(e.status)) return {};
    return fail(e);
  }
}

export async function approveClaim(claimId: string, path: string): Promise<FormState> {
  const r = await attempt(() => api(`/v1/claims/${claimId}/approve`, { method: "POST" }));
  if (r.error) return r;
  revalidatePath(path);
  return {};
}

export async function rejectClaim(claimId: string, path: string, code = "wrong"): Promise<FormState> {
  const r = await attempt(() => apiJson(`/v1/claims/${claimId}/reject`, { code }));
  if (r.error) return r;
  revalidatePath(path);
  return {};
}

export async function resolveDecision(decisionId: string, action: string, claimId: string | null, path: string): Promise<FormState> {
  const r = await attempt(() => apiJson(`/v1/decisions/${decisionId}/resolve`, { action, claim_id: claimId }));
  if (r.error) return r;
  revalidatePath(path);
  return {};
}

export async function refreshAfterUpload(jobId: string | null): Promise<void> {
  revalidatePath(jobId ? `/jobs/${jobId}` : "/people");
  revalidatePath("/");
  revalidatePath("/jobs");
}

export async function putOnJob(candidateId: string, form: FormData): Promise<FormState> {
  const jobId = String(form.get("job") || "");
  if (!jobId) return {};
  try {
    await apiJson(`/v1/jobs/${jobId}/people/${candidateId}`, {});
  } catch (e) {
    return fail(e);
  }
  revalidatePath(`/people/${candidateId}`);
  revalidatePath(`/jobs/${jobId}`);
  revalidatePath("/people");
  return {};
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
  revalidatePath("/jobs");
  redirect("/jobs?erased=1");
}


/** The recruiter knows the person has a skill the file did not show: record it as an approved fact.
 *  Bands that depend on it are recomputed by the platform, and the change appears in the pair history. */
export async function addSkill(candidateId: string, token: string, path: string): Promise<FormState> {
  try {
    await apiJson("/v1/claims", {
      subject_type: "candidate",
      subject_id: candidateId,
      claim_type: "SkillClaim",
      payload: { raw_label: token, normalized_skill: token.toLowerCase() },
    });
  } catch (e) {
    return fail(e);
  }
  revalidatePath(path);
  return {};
}


/** Move a person-job pair: seen, submitted (with a note) or we_passed (with a reason). Pairs are never deleted. */
export async function setPairState(jobId: string, candidateId: string, path: string, _: FormState, form: FormData): Promise<FormState> {
  try {
    await apiJson(`/v1/jobs/${jobId}/people/${candidateId}/state`, {
      state: String(form.get("state") || ""),
      reason: String(form.get("reason") || "") || null,
      note: String(form.get("note") || "") || null,
    });
  } catch (e) {
    return fail(e);
  }
  revalidatePath(path);
  revalidatePath(`/jobs/${jobId}`);
  return { message: "Saved." };
}


export type QueuedFile = { file: string; taskId?: string; error?: string };
export type TaskView = { id: string; status: string; error: string | null; result: Record<string, any> | null; name?: string | null };

/** Store one CV and queue its reading; returns at once. */
export async function queueCv(jobId: string | null, form: FormData): Promise<QueuedFile> {
  const file = form.get("file");
  if (!(file instanceof File) || !file.size) return { file: "?", error: "empty file" };
  try {
    const body = new FormData();
    body.append("file", file);
    const path = jobId ? `/v1/jobs/${jobId}/documents?background=true` : "/v1/candidates?background=true";
    const r = await api<{ task_id: string }>(path, { method: "POST", body });
    return { file: file.name, taskId: r.task_id };
  } catch (e) {
    return { file: file.name, error: e instanceof ApiError ? e.message : "failed" };
  }
}

/** Progress of queued reads, with the person's name once a read is done. */
export async function checkTasks(ids: string[]): Promise<TaskView[]> {
  if (!ids.length) return [];
  const rows = await api<TaskView[]>(`/v1/tasks?ids=${ids.join(",")}`);
  for (const row of rows) {
    const sid = row.result?.subject_id;
    if (row.status === "done" && sid && row.result?.subject_type === "candidate") {
      try {
        row.name = (await api<{ name: string | null }>(`/v1/candidates/${sid}`)).name;
      } catch {}
    }
  }
  return rows;
}

/** A company's website or LinkedIn page, typed: how Exa confirms it (and so how a role's talent DNA is learned). */
export async function setCompanyKeys(companyId: string, _: FormState, form: FormData): Promise<FormState> {
  const body = { website: String(form.get("website") || "").trim() || null, linkedin: String(form.get("linkedin") || "").trim() || null };
  if (!body.website && !body.linkedin) return { error: "Type its website or its LinkedIn page." };
  let out: { clash: { id: string; name: string } | null };
  try {
    out = await apiSend(`/v1/companies/${companyId}/keys`, "PUT", body);
  } catch (e) {
    return fail(e);
  }
  revalidatePath(`/companies/${companyId}`);
  return out.clash
    ? { message: `${out.clash.name} already has that website or page: the inbox asks whether they are the same company.` }
    : { message: "Saved. A role with this hiring company can now learn its talent DNA (Build the strategy)." };
}

/** Queue fresh public research for a company (even if its facts are still fresh); the workers do the rest. */
export async function researchCompany(companyId: string): Promise<FormState> {
  const r = await attempt(() => api(`/v1/companies/${companyId}/research`, { method: "POST" }));
  if (r.error) return r;
  revalidatePath(`/companies/${companyId}`);
  return {};
}

/** Un-archive a person the coverage rule archived; the rule then leaves them be. */
export async function bringBack(candidateId: string, path: string): Promise<FormState> {
  const r = await attempt(() => apiJson(`/v1/candidates/${candidateId}/bring-back`, {}));
  if (r.error) return r;
  revalidatePath(path);
  revalidatePath("/people");
  return {};
}

/** Where people must live for the role (names or codes, comma separated): the one place its countries are kept. */
export async function setJobCountries(jobId: string, _: FormState, form: FormData): Promise<FormState> {
  const countries = String(form.get("countries") ?? "").split(",").map((c) => c.trim()).filter(Boolean);
  try {
    await api(`/v1/jobs/${jobId}/countries`, { method: "PUT", body: JSON.stringify({ countries }), headers: { "Content-Type": "application/json" } });
  } catch (e) {
    return fail(e);
  }
  revalidatePath(`/jobs/${jobId}`);
  return { message: countries.length ? "Saved. Sourcing follows it; people on this role were checked again." : "Cleared: no country limit for this role." };
}

/** Correct how one career step was read (kind of work, level). Saved as approved; it replaces the machine's reading. */
export async function correctStep(candidateId: string, path: string, careerClaimId: string, replaces: string | null,
                                  keep: { domains: string[]; signals: string[] }, _: FormState, form: FormData): Promise<FormState> {
  const role_family = String(form.get("role_family") || "");
  const level = String(form.get("level") || "") || null;
  if (!role_family) return { error: "Choose a kind of work." };
  try {
    await apiJson("/v1/claims", {
      subject_type: "candidate", subject_id: candidateId, claim_type: "StepClassificationClaim", replaces,
      payload: { career_claim_id: careerClaimId, role_family, level, domains: keep.domains, signals: keep.signals },
    });
  } catch (e) {
    return fail(e);
  }
  revalidatePath(path);
  return { message: "Saved. The profile was rebuilt." };
}

/** "Confirm all" on the hiring profile: the requirements the desk read, approved together; everyone re-matched once. */
export async function confirmRequirements(jobId: string, ids: string[]): Promise<FormState> {
  try {
    const r = await apiJson<{ confirmed: number; already: number }>(`/v1/jobs/${jobId}/requirements/confirm`, { ids });
    revalidatePath(`/jobs/${jobId}`);
    return { message: `Confirmed ${r.confirmed}.` };
  } catch (e) {
    return fail(e);
  }
}

/** A requirement in the recruiter's own words and how much it matters; the desk reads changed words again. */
export async function editRequirement(claimId: string, path: string, _: FormState, form: FormData): Promise<FormState> {
  const text = String(form.get("text") ?? "").trim();
  const strength = String(form.get("strength") ?? "") || null;
  try {
    await apiJson(`/v1/requirements/${claimId}/edit`, { text, strength });
  } catch (e) {
    return fail(e);
  }
  revalidatePath(path);
  return {};
}

/** Anything about the role in your own words: read like notes, then the brief again. */
export async function tellDesk(jobId: string, _: FormState, form: FormData): Promise<FormState> {
  const text = String(form.get("text") ?? "").trim();
  if (!text) return { error: "Write something first." };
  try {
    const r = await apiJson<{ notes: { written: number; replaced: number; seen: number; rejected: { item: string; reason: string }[] };
      lines?: number; dates?: { event: string; date: string; replaced: [string, string] | null }[] }>(`/v1/jobs/${jobId}/tell`, { text });
    revalidatePath(`/jobs/${jobId}`);
    const n = r.notes;
    const day = (iso: string) => new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
    const dated = (r.dates ?? []).map((d) => `${d.event} on ${day(d.date)}${d.replaced ? ` (replacing ${d.replaced[0]}, ${day(d.replaced[1])})` : ""}`);
    if (dated.length) return { message: `Dates: ${dated.join("; ")}.${n.written ? ` And ${n.written} requirement${n.written === 1 ? "" : "s"} to confirm.` : ""}` };
    const read = n.written ? `Read ${n.written} requirement${n.written === 1 ? "" : "s"}${n.replaced ? ` (${n.replaced} replacing earlier ones)` : ""}: they wait for Confirm all.`
      : n.seen ? "Nothing new: the profile already says it." : "No requirement in it; kept with the notes.";
    const left = n.rejected.length ? ` Left out: ${n.rejected.map((x) => `${x.item} (${x.reason})`).join("; ")}.` : "";
    return { message: `${read}${r.lines ? " The brief is read again." : ""}${left}` };
  } catch (e) {
    return fail(e);
  }
}

/** Read the role brief (about a cent): what the hire will really do, from the ad, the notes and research. */
export async function readRoleBrief(jobId: string): Promise<FormState> {
  try {
    const r = await apiJson<{ lines?: number; questions?: number; skipped?: string }>(`/v1/jobs/${jobId}/role-brief`, {});
    revalidatePath(`/jobs/${jobId}`);
    if (r.skipped) return { error: `Not read: ${r.skipped}.` };
    return { message: `Read ${r.lines} lines${r.questions ? `, ${r.questions} question${r.questions === 1 ? "" : "s"} for you` : ""}.` };
  } catch (e) {
    return fail(e);
  }
}

/** The role's work, line by line, and its look-alikes (the core-work reader, owner 2026-10-27): read again by the desk
    (about a fifth of a cent); the lines you confirmed or typed stay. */
export async function readWorkLines(jobId: string): Promise<FormState> {
  try {
    const r = await apiJson<{ lines?: number; skipped?: string }>(`/v1/jobs/${jobId}/work-lines`, {});
    revalidatePath(`/jobs/${jobId}`);
    if (r.skipped) return { error: `Not read: ${r.skipped}.` };
    return { message: `Read ${r.lines} lines.` };
  } catch (e) {
    return fail(e);
  }
}

/** Confirm the desk's lines: everyone strong or possible is then read against them in the background. */
export async function confirmWorkLines(jobId: string, ids: string[]): Promise<FormState> {
  try {
    const r = await apiJson<{ confirmed: number; queued: number }>(`/v1/jobs/${jobId}/work-lines/confirm`, { ids });
    revalidatePath(`/jobs/${jobId}`);
    return { message: `Confirmed ${r.confirmed}.${r.queued ? ` Reading ${r.queued} ${r.queued === 1 ? "person" : "people"} against them.` : ""}` };
  } catch (e) {
    return fail(e);
  }
}

/** A line of the work in your own words (confirmed at once), or a look-alike job that is not this work. */
export async function addWorkLine(jobId: string, kind: "work" | "not", _: FormState, form: FormData): Promise<FormState> {
  const words = String(form.get("words") ?? "").trim();
  if (!words) return { error: "Write the line first." };
  try {
    await apiJson(`/v1/jobs/${jobId}/work-lines/add`, { kind, words, central: form.get("central") === "on" });
  } catch (e) {
    return fail(e);
  }
  revalidatePath(`/jobs/${jobId}`);
  return { message: "Added." };
}

/** A line in your own words, replacing the desk's (or your earlier) wording. */
export async function editWorkLine(claimId: string, jobId: string, _: FormState, form: FormData): Promise<FormState> {
  const words = String(form.get("words") ?? "").trim();
  if (!words) return { error: "Write the line first." };
  try {
    await apiJson(`/v1/work-lines/${claimId}/edit`, { words, central: form.get("central") === "on" });
  } catch (e) {
    return fail(e);
  }
  revalidatePath(`/jobs/${jobId}`);
  return {};
}

/** After the lines changed: read again everyone whose reading is against earlier lines. */
export async function readPeopleAgain(jobId: string): Promise<FormState> {
  try {
    const r = await apiJson<{ queued: number }>(`/v1/jobs/${jobId}/work-readings`, {});
    revalidatePath(`/jobs/${jobId}`);
    return { message: r.queued ? `Reading ${r.queued} ${r.queued === 1 ? "person" : "people"} again.` : "Everyone is read against these lines." };
  } catch (e) {
    return fail(e);
  }
}

/** The uploader's answer to one of the brief's questions: read like notes from the hiring manager, then the brief again. */
export async function answerBriefQuestion(jobId: string, facet: string, _: FormState, form: FormData): Promise<FormState> {
  const answer = String(form.get("answer") ?? "").trim();
  if (!answer) return { error: "Write the answer first." };
  try {
    await apiJson(`/v1/jobs/${jobId}/role-brief/answer`, { facet, answer });
  } catch (e) {
    return fail(e);
  }
  revalidatePath(`/jobs/${jobId}`);
  return { message: "Read. The brief and the requirements are updated." };
}

/** Close a role (on hold, filled, cancelled) or open it again. */
export async function setJobState(jobId: string, _: FormState, form: FormData): Promise<FormState> {
  try {
    await apiSend(`/v1/jobs/${jobId}/state`, "PUT", { state: String(form.get("state") || ""), note: String(form.get("note") || "").trim() || null });
  } catch (e) {
    return fail(e);
  }
  revalidatePath(`/jobs/${jobId}`);
  revalidatePath("/jobs");
  revalidatePath("/");
  return {};
}

/** Delete a role added by mistake (optionally with the people only its sourcing found). */
export async function deleteJob(jobId: string, _: FormState, form: FormData): Promise<FormState> {
  try {
    await apiSend(`/v1/jobs/${jobId}?remove_people=${form.get("remove_people") === "on"}`, "DELETE");
  } catch (e) {
    return fail(e);
  }
  revalidatePath("/jobs");
  revalidatePath("/");
  redirect("/jobs?deleted=1");
}

/** Who is hiring, typed by a person (an anonymised ad names nobody). */
export async function setHiringCompany(jobId: string, _: FormState, form: FormData): Promise<FormState> {
  const name = String(form.get("name") ?? "").trim();
  if (!name) return { error: "Type the hiring company's name." };
  try {
    await apiSend(`/v1/jobs/${jobId}/hiring-company`, "PUT", { name });
  } catch (e) {
    return fail(e);
  }
  revalidatePath(`/jobs/${jobId}`);
  return { message: `${name} is the hiring company. Build the strategy on the Sourcing tab to use it.` };
}

/** Capture an answer from the call (the outcome comes from the button pressed). */
export async function answerBrief(itemId: string, path: string, form: FormData): Promise<FormState> {
  const outcome = String(form.get("outcome") || "noted");
  const answer = String(form.get("answer") || "").trim();
  const r = await attempt(() => apiJson(`/v1/brief/${itemId}/answer`, { outcome, answer: answer || null }));
  if (r.error) return r;
  revalidatePath(path);
  return {};
}

export async function briefAsked(itemId: string, path: string): Promise<FormState> {
  const r = await attempt(() => apiJson(`/v1/brief/${itemId}/asked`, {}));
  if (r.error) return r;
  revalidatePath(path);
  return {};
}

export async function briefDismiss(itemId: string, path: string): Promise<FormState> {
  const r = await attempt(() => apiJson(`/v1/brief/${itemId}/dismiss`, {}));
  if (r.error) return r;
  revalidatePath(path);
  return {};
}

// --- relationship memory (Slice 4) ---

/** Log a call, email, meeting, message or note with a person or a client. */
export async function logActivity(subject: "candidates" | "companies", subjectId: string, path: string, _: FormState, form: FormData): Promise<FormState> {
  const body: Record<string, unknown> = {
    kind: String(form.get("kind") || "note"), summary: String(form.get("summary") || "").trim(),
    direction: String(form.get("direction") || "") || null,
    occurred_at: String(form.get("occurred_at") || "") || null,
    job_id: String(form.get("job_id") || "") || null,
    contact_id: String(form.get("contact_id") || "") || null,
  };
  if (!body.summary) return { error: "Write what happened, in a line." };
  try {
    await apiJson(`/v1/${subject}/${subjectId}/activities`, body);
  } catch (e) {
    return fail(e);
  }
  revalidatePath(path);
  return { message: "Logged." };
}

export async function removeActivity(activityId: string, path: string): Promise<FormState> {
  const r = await attempt(() => api(`/v1/activities/${activityId}`, { method: "DELETE" }));
  if (r.error) return r;
  revalidatePath(path);
  return {};
}

export async function tagPerson(candidateId: string, path: string, form: FormData): Promise<FormState> {
  const tag = String(form.get("tag") || "").trim();
  if (!tag) return {};
  const r = await attempt(() => apiJson(`/v1/candidates/${candidateId}/tags`, { tag }));
  if (r.error) return r;
  revalidatePath(path);
  revalidatePath("/people");
  return {};
}

export async function untagPerson(candidateId: string, tag: string, path: string): Promise<FormState> {
  const r = await attempt(() => api(`/v1/candidates/${candidateId}/tags/${encodeURIComponent(tag)}`, { method: "DELETE" }));
  if (r.error) return r;
  revalidatePath(path);
  revalidatePath("/people");
  return {};
}

export async function addContact(companyId: string, path: string, _: FormState, form: FormData): Promise<FormState> {
  const body = Object.fromEntries(["name", "role", "email", "phone", "linkedin"].map((k) => [k, String(form.get(k) || "").trim() || null]));
  if (!body.name) return { error: "A contact needs a name." };
  try {
    await apiJson(`/v1/companies/${companyId}/contacts`, body);
  } catch (e) {
    return fail(e);
  }
  revalidatePath(path);
  return { message: "Contact added." };
}

export async function removeContact(contactId: string, path: string): Promise<FormState> {
  const r = await attempt(() => api(`/v1/contacts/${contactId}`, { method: "DELETE" }));
  if (r.error) return r;
  revalidatePath(path);
  return {};
}

/** Lift a client's block, with a note saying why. */
export async function liftBlock(blockId: string, path: string, form: FormData): Promise<FormState> {
  const note = String(form.get("note") || "").trim();
  if (!note) return {};
  const r = await attempt(() => apiJson(`/v1/blocks/${blockId}/lift`, { note }));
  if (r.error) return r;
  revalidatePath(path);
  return {};
}

// --- import (Slice 4, step 4) ---

export async function uploadImport(form: FormData): Promise<void> {
  const file = form.get("file");
  if (!(file instanceof File) || !file.size) return;
  const body = new FormData();
  body.append("file", file);
  body.append("kind", String(form.get("kind") || "candidates"));
  const batch = await api<{ id: string }>("/v1/imports", { method: "POST", body });
  redirect(`/import/${batch.id}`);
}

export async function importRows(batchId: string, path: string, form: FormData): Promise<FormState> {
  const row_ids = form.getAll("row").map(String);
  if (!row_ids.length) return {};
  try {
    await apiJson(`/v1/imports/${batchId}/import`, { row_ids });
  } catch (e) {
    return fail(e);
  }
  revalidatePath(path);
  revalidatePath("/people");
  return {};
}

export async function acceptImportQuote(batchId: string, path: string): Promise<FormState> {
  const r = await attempt(() => apiJson(`/v1/imports/${batchId}/quote/accept`, {}));
  if (r.error) return r;
  revalidatePath(path);
  return {};
}

// --- messages and mailbox (Slice 4, step 5): drafts only; you send from your own mailbox ---

export type MessageState = FormState & { link?: string };

export async function draftMessage(candidateId: string, path: string, _: FormState, form: FormData): Promise<FormState> {
  const chosen = String(form.get("kind") || "candidate_outreach");
  const linkedin = chosen === "linkedin_outreach";
  const kind = linkedin ? "candidate_outreach" : chosen;
  const contact = String(form.get("contact_id") || "");
  const [contactId, contactJob] = contact ? contact.split("|") : [null, null];
  const body = {
    kind, candidate_id: candidateId, contact_id: contactId,
    job_id: contactJob || String(form.get("job_id") || "") || null,
    note: String(form.get("note") || "").trim() || null,
    channel: linkedin ? "linkedin" : "email",
  };
  if (kind === "client_submission" && !contactId) return { error: "Choose who at the client it goes to." };
  try {
    await apiJson("/v1/messages", body);
  } catch (e) {
    return fail(e);
  }
  revalidatePath(path);
  return { message: "Drafted below. Read it, edit it, then put it in your drafts." };
}

export async function editMessage(messageId: string, path: string, _: MessageState, form: FormData): Promise<MessageState> {
  try {
    await api(`/v1/messages/${messageId}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ subject: String(form.get("subject") || ""), body: String(form.get("body") || "") }),
    });
  } catch (e) {
    return fail(e);
  }
  revalidatePath(path);
  return { message: "Saved." };
}

export async function messageToMailbox(messageId: string, path: string, _: MessageState): Promise<MessageState> {
  let link: string | undefined;
  try {
    link = (await apiJson<{ open: string | null }>(`/v1/messages/${messageId}/mailbox`, {})).open ?? undefined;
  } catch (e) {
    return fail(e);
  }
  revalidatePath(path);
  return { message: "In your drafts. Send it from there.", link };
}

export async function markMessage(messageId: string, what: "sent" | "replied", path: string): Promise<void> {
  await idempotent(() => apiJson(`/v1/messages/${messageId}/${what}`, {}));
  revalidatePath(path);
}

export async function connectMailbox(provider: "google" | "microsoft"): Promise<void> {
  const { url } = await apiJson<{ url: string }>(`/v1/mailbox/connect/${provider}`, {});
  redirect(url);
}

export async function disconnectMailbox(): Promise<FormState> {
  const r = await attempt(() => api("/v1/mailbox", { method: "DELETE" }));
  if (r.error) return r;
  revalidatePath("/mailbox");
  return {};
}

export async function syncMailbox(path: string): Promise<FormState> {
  const r = await attempt(() => apiJson("/v1/mailbox/sync", {}));
  if (r.error) return r;
  revalidatePath(path);
  return {};
}

// --- access: sign in, account, members ---

const COOKIE = { httpOnly: true, sameSite: "lax" as const, secure: process.env.COOKIE_SECURE === "true", path: "/" };

async function forwardedFor(): Promise<string | null> {
  return (await headers()).get("x-forwarded-for");
}

async function startSession(token: string): Promise<void> {
  const jar = await cookies();
  jar.set(SESSION_COOKIE, token, { ...COOKIE, maxAge: 14 * 24 * 3600 });
  jar.delete(TICKET_COOKIE);
}

export async function signIn(_: FormState, form: FormData): Promise<FormState> {
  const email = String(form.get("email") || "").trim();
  const password = String(form.get("password") || "");
  if (!email || !password) return { error: "Enter your email and password." };
  let result: { token?: string; needs_code?: boolean; ticket?: string };
  try {
    result = await apiPublic("/v1/auth/login", { email, password }, await forwardedFor());
  } catch (e) {
    return fail(e);
  }
  if (result.needs_code && result.ticket) {
    (await cookies()).set(TICKET_COOKIE, result.ticket, { ...COOKIE, maxAge: 300 });
    redirect("/login?step=code");
  }
  await startSession(result.token!);
  redirect("/");
}

export async function signInCode(_: FormState, form: FormData): Promise<FormState> {
  const ticket = (await cookies()).get(TICKET_COOKIE)?.value;
  if (!ticket) redirect("/login");
  let token: string;
  try {
    token = (await apiPublic<{ token: string }>("/v1/auth/login/code", { ticket, code: String(form.get("code") || "") },
      await forwardedFor())).token;
  } catch (e) {
    return fail(e);
  }
  await startSession(token);
  redirect("/");
}

export async function signOut(): Promise<void> {
  try {
    await apiRaw("/v1/auth/logout", { method: "POST" });
  } catch (e) {
    unstable_rethrow(e);
  }
  const jar = await cookies();
  jar.delete(SESSION_COOKIE);
  jar.delete(DESK_COOKIE);
  redirect("/login");
}

export async function switchDesk(form: FormData): Promise<void> {
  const desk = String(form.get("desk") || "");
  if (/^[0-9a-f-]{36}$/i.test(desk)) (await cookies()).set(DESK_COOKIE, desk, { ...COOKIE, maxAge: 14 * 24 * 3600 });
  redirect("/");
}

export async function acceptInvite(token: string, _: FormState, form: FormData): Promise<FormState> {
  const password = String(form.get("password") || "");
  if (form.has("repeat") && password !== String(form.get("repeat"))) return { error: "The two passwords differ." };
  try {
    await apiPublic(`/v1/auth/invites/${encodeURIComponent(token)}/accept`,
      { password, name: String(form.get("name") || "").trim() || null });
  } catch (e) {
    return fail(e);
  }
  redirect("/login?ready=1");
}

export async function changePassword(_: FormState, form: FormData): Promise<FormState> {
  const next = String(form.get("new") || "");
  if (next !== String(form.get("repeat") || "")) return { error: "The two new passwords differ." };
  try {
    await apiRaw("/v1/auth/password", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ current: String(form.get("current") || ""), new: next }) });
  } catch (e) {
    return fail(e);
  }
  return { message: "Password changed. Your other sessions have ended." };
}

export type TwoStepState = FormState & { secret?: string; uri?: string };

export async function startTwoStep(_: TwoStepState): Promise<TwoStepState> {
  try {
    return await apiJson<{ secret: string; uri: string }>("/v1/auth/two-step/start", {});
  } catch (e) {
    return fail(e);
  }
}

export async function confirmTwoStep(_: FormState, form: FormData): Promise<FormState> {
  try {
    await apiRaw("/v1/auth/two-step/confirm", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: String(form.get("code") || "") }) });
  } catch (e) {
    return fail(e);
  }
  revalidatePath("/account");
  redirect("/account?two_step=on");
}

export async function disableTwoStep(_: FormState, form: FormData): Promise<FormState> {
  try {
    await apiRaw("/v1/auth/two-step/disable", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: String(form.get("password") || "") }) });
  } catch (e) {
    return fail(e);
  }
  revalidatePath("/account");
  redirect("/account?two_step=off");
}

export async function endOtherSessions(): Promise<void> {
  await apiJson("/v1/auth/sessions/end-others", {});
  revalidatePath("/account");
}

export type LinkState = FormState & { link?: string };

export async function inviteMember(_: LinkState, form: FormData): Promise<LinkState> {
  try {
    const out = await apiJson<{ link: string; email: string }>("/v1/members/invites",
      { email: String(form.get("email") || "").trim(), role: String(form.get("role") || "recruiter") });
    revalidatePath("/members");
    return { message: `Invitation for ${out.email}, valid 7 days. Copy the link and send it yourself:`, link: out.link };
  } catch (e) {
    return fail(e);
  }
}

export async function resetMember(userId: string, _: LinkState): Promise<LinkState> {
  try {
    const out = await apiJson<{ link: string; email: string }>(`/v1/members/${userId}/reset`, {});
    return { message: `A new sign-in link for ${out.email}, valid 24 hours. It also clears their two-step codes:`, link: out.link };
  } catch (e) {
    return fail(e);
  }
}

export async function setMemberRole(userId: string, form: FormData): Promise<FormState> {
  // Not idempotent(): "a desk needs at least one owner" must be shown, not swallowed.
  try {
    await apiRaw(`/v1/members/${userId}`, { method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role: String(form.get("role") || "recruiter") }) });
  } catch (e) {
    return fail(e);
  }
  revalidatePath("/members");
  return {};
}

export async function removeMember(userId: string): Promise<FormState> {
  try {
    await apiRaw(`/v1/members/${userId}`, { method: "DELETE" });
  } catch (e) {
    return fail(e);
  }
  revalidatePath("/members");
  return {};
}

// --- calls -------------------------------------------------------------------------------------

/** A call transcript, pasted or as a file: stored as the person's document and read in the background. */
export async function addTranscript(candidateId: string, path: string, _: FormState, form: FormData): Promise<FormState> {
  const [file] = filesOf(form);
  const text = String(form.get("text") || "").trim();
  if (!file && !text) return { error: "Paste the transcript or choose a file." };
  const body = new FormData();
  if (file) body.append("file", file);
  else body.append("text", text);
  try {
    await api(`/v1/candidates/${candidateId}/transcripts`, { method: "POST", body });
  } catch (e) {
    return fail(e);
  }
  revalidatePath(path);
  return { message: "Reading the call. The review appears here in a moment." };
}

/** Approve the ticked lines of a Call review in one go; unticked lines are dropped. */
export async function applyCallReview(reviewId: string, path: string, form: FormData): Promise<FormState> {
  const ticked = form.getAll("tick").map(String);
  const r = await attempt(() => apiJson(`/v1/call-reviews/${reviewId}/apply`, { ticked }));
  if (r.error) return r;
  revalidatePath(path);
  return {};
}

export async function dismissCallReview(reviewId: string, path: string): Promise<FormState> {
  const r = await attempt(() => api(`/v1/call-reviews/${reviewId}/dismiss`, { method: "POST" }));
  if (r.error) return r;
  revalidatePath(path);
  return {};
}

export async function retryCallReview(reviewId: string, path: string): Promise<FormState> {
  const r = await attempt(() => api(`/v1/call-reviews/${reviewId}/retry`, { method: "POST" }));
  if (r.error) return r;
  revalidatePath(path);
  return {};
}

/** Every proposed fact read from this CV, approved at once; questions stay one by one. */
export async function approveAllFromDocument(candidateId: string, documentId: string, path: string): Promise<FormState> {
  const r = await attempt(() => api(`/v1/candidates/${candidateId}/documents/${documentId}/approve-all`, { method: "POST" }));
  if (r.error) return r;
  revalidatePath(path);
  return {};
}

// --- same person -------------------------------------------------------------------------------

/** Two records of one person made one (the older is kept); the "Who is this?" question is answered with it. */
export async function mergePeople(candidateId: string, otherId: string, path: string): Promise<FormState> {
  const r = await attempt(() => apiJson(`/v1/candidates/${candidateId}/merge`, { other_id: otherId }));
  if (r.error) return r;
  revalidatePath(path);
  return {};
}

export async function undoMerge(mergeId: string, path: string): Promise<FormState> {
  const r = await attempt(() => api(`/v1/merges/${mergeId}/undo`, { method: "POST" }));
  if (r.error) return r;
  revalidatePath(path);
  return {};
}


// --- the sourcing engine (docs/next/PLAN.md, phase 1) --------------------------------------------------------------

async function apiSend<T>(path: string, method: "PATCH" | "PUT" | "DELETE" | "POST", body?: unknown): Promise<T> {
  return api<T>(path, { method, body: body === undefined ? undefined : JSON.stringify(body),
    headers: body === undefined ? undefined : { "Content-Type": "application/json" } });
}

const words = (v: FormDataEntryValue | null) => String(v || "").split(/[,\n]/).map((x) => x.trim()).filter(Boolean);

export async function setSourcingPlan(jobId: string, _: FormState, form: FormData): Promise<FormState> {
  const body: Record<string, unknown> = {};
  if (form.has("mode")) body.mode = String(form.get("mode"));
  if (form.get("target")) body.target = Number(form.get("target"));
  if (form.get("budget")) body.monthly_budget_usd = Number(form.get("budget"));
  if (form.has("variants")) body.role_variants = words(form.get("variants"));
  if (form.has("countries")) body.countries = words(form.get("countries")); // names or codes; written to the hiring profile
  try {
    await apiSend(`/v1/jobs/${jobId}/sourcing/plan`, "PATCH", body);
  } catch (e) {
    return fail(e);
  }
  revalidatePath(`/jobs/${jobId}`);
  return { message: "Saved: a new version of the plan." };
}

export async function setSourcingMode(jobId: string, mode: string, _: FormState): Promise<FormState> {
  try {
    await apiSend(`/v1/jobs/${jobId}/sourcing/plan`, "PATCH", { mode });
  } catch (e) {
    return fail(e);
  }
  revalidatePath(`/jobs/${jobId}`);
  return {};
}

export async function addSourcingTarget(jobId: string, _: FormState, form: FormData): Promise<FormState> {
  const name = String(form.get("name") || "").trim();
  if (!name) return { error: "Type a company name." };
  try {
    await apiJson(`/v1/jobs/${jobId}/sourcing/targets`, { name });
  } catch (e) {
    return fail(e);
  }
  revalidatePath(`/jobs/${jobId}`);
  return { message: `${name} added, pinned to the top.` };
}

export async function changeSourcingTarget(jobId: string, companyId: string, change: "pin" | "unpin" | "remove" | "restore"): Promise<void> {
  const body = change === "pin" ? { pinned: true } : change === "unpin" ? { pinned: false } : { removed: change === "remove" };
  await idempotent(() => apiSend(`/v1/jobs/${jobId}/sourcing/targets/${companyId}`, "PATCH", body));
  revalidatePath(`/jobs/${jobId}`);
}

export async function runSourcingNow(jobId: string, _: FormState): Promise<FormState> {
  let status = "";
  try {
    status = (await apiJson<{ status: string }>(`/v1/jobs/${jobId}/sourcing/run`, {})).status;
  } catch (e) {
    return fail(e);
  }
  revalidatePath(`/jobs/${jobId}`);
  return {
    message: status === "building"
      ? "This role's company list was never built: building it first (the client's competitors, a few minutes), then the search starts by itself."
      : "Searching: your own desk first, then the web within the budgets. This page updates by itself.",
  };
}

export async function setSourcingFocus(jobId: string, widen: boolean, _: FormState, form: FormData): Promise<FormState> {
  const words = widen ? null : String(form.get("words") || "").trim();
  if (!widen && !words) return { error: "Write what to focus on, e.g. luxury apparel." };
  try {
    await api(`/v1/jobs/${jobId}/sourcing/focus`, { method: "PUT", body: JSON.stringify({ words }),
      headers: { "Content-Type": "application/json" } });
  } catch (e) {
    return fail(e);
  }
  revalidatePath(`/jobs/${jobId}`);
  return { message: widen ? "Widened: every company on the list is searched again." : `Focused on “${words}”.` };
}

export async function widenSourcingFocus(jobId: string, state: FormState): Promise<FormState> {
  return setSourcingFocus(jobId, true, state, new FormData());
}

/** A page that crashed in the browser says so in the activity log (owner, 2026-10-22). Never throws. */
export async function reportClientError(report: { message: string; stack?: string; url?: string; digest?: string }): Promise<void> {
  try {
    await apiJson("/v1/activity/client-error", report);
  } catch {
    // signed out, or the API is down: nothing more to do
  }
}

export async function buildStrategy(jobId: string, _: FormState): Promise<FormState> {
  try {
    await apiJson(`/v1/jobs/${jobId}/sourcing/strategy`, {});
  } catch (e) {
    return fail(e);
  }
  revalidatePath(`/jobs/${jobId}`);
  return { message: "Building: the hiring company's people, where they came from, and similar companies. This page updates by itself." };
}

export async function widenSourcing(jobId: string, option: string, value: string | string[] | null): Promise<void> {
  await idempotent(() => apiSend(`/v1/jobs/${jobId}/sourcing/widen`, "POST", { option, value }));
  revalidatePath(`/jobs/${jobId}`);
}

/** One step of the owner's workflow on a role's suggestion (phase 1c): viewed, decide, undo, contacted, replied,
 *  call-booked, or settling which person a LinkedIn email is about. */
export async function outreachStep(jobId: string, candidateId: string, step: string, body: Record<string, unknown>): Promise<FormState> {
  try {
    await apiJson(`/v1/jobs/${jobId}/people/${candidateId}/${step}`, body);
  } catch (e) {
    return fail(e);
  }
  revalidatePath(`/jobs/${jobId}`);
  return {};
}

export async function checkDeeper(jobId: string, candidateId: string): Promise<FormState> {
  try {
    await apiJson(`/v1/jobs/${jobId}/sourcing/people/${candidateId}/evidence`, {});
  } catch (e) {
    return fail(e);
  }
  revalidatePath(`/jobs/${jobId}`);
  return { message: "Checking their public work: their own links, then their name with their company. This card updates by itself." };
}

export async function draftLinkedIn(jobId: string, candidateId: string): Promise<FormState> {
  try {
    await apiJson("/v1/messages", { kind: "candidate_outreach", candidate_id: candidateId, job_id: jobId, channel: "linkedin" });
  } catch (e) {
    return fail(e);
  }
  redirect(`/people/${candidateId}?tab=messages`);
}

export async function recordPermission(candidateId: string, path: string, _: FormState, form: FormData): Promise<FormState> {
  const body = { job_id: String(form.get("job_id") || "") || null, this_role: form.get("this_role") === "on",
    other_roles: form.get("other_roles") === "on", how: String(form.get("how") || "") || null,
    note: String(form.get("note") || "").trim() || null };
  if (!body.this_role && !body.other_roles) return { error: "Tick what they said yes to." };
  if (body.this_role && !body.job_id) return { error: "Choose the role they said yes to." };
  try {
    await apiJson(`/v1/candidates/${candidateId}/permission`, body);
  } catch (e) {
    return fail(e);
  }
  revalidatePath(path);
  return { message: "Recorded." };
}

export async function stopContact(candidateId: string, path: string, form: FormData): Promise<FormState> {
  try {
    await apiJson(`/v1/candidates/${candidateId}/stop`, { note: String(form.get("note") || "").trim() || null });
  } catch (e) {
    return fail(e);
  }
  revalidatePath(path);
  return {};
}

export async function liftStopContact(candidateId: string, path: string, _: FormState, form: FormData): Promise<FormState> {
  try {
    await apiJson(`/v1/candidates/${candidateId}/stop/lift`, { note: String(form.get("note") || "").trim() });
  } catch (e) {
    return fail(e);
  }
  revalidatePath(path);
  return { message: "They may be contacted again." };
}

export async function setDeskSourcingBudget(_: FormState, form: FormData): Promise<FormState> {
  try {
    await apiSend("/v1/sourcing/settings", "PUT", { sourcing_budget_usd: Number(form.get("budget")) });
  } catch (e) {
    return fail(e);
  }
  revalidatePath("/sourcing");
  return { message: "Saved." };
}

export async function addOffLimits(_: FormState, form: FormData): Promise<FormState> {
  const name = String(form.get("name") || "").trim();
  if (!name) return { error: "Type a company name." };
  try {
    await apiJson("/v1/off-limits", { name, until: String(form.get("until") || "") || null, note: String(form.get("note") || "").trim() || null });
  } catch (e) {
    return fail(e);
  }
  revalidatePath("/sourcing");
  return { message: `${name} is off-limits.` };
}

export async function removeOffLimits(rowId: string): Promise<void> {
  await idempotent(() => apiSend(`/v1/off-limits/${rowId}`, "DELETE"));
  revalidatePath("/sourcing");
}
