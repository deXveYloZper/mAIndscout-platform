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

export async function refreshAfterUpload(jobId: string | null): Promise<void> {
  revalidatePath(jobId ? `/jobs/${jobId}` : "/people");
  revalidatePath("/");
  revalidatePath("/jobs");
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
  revalidatePath("/jobs");
  redirect("/jobs?erased=1");
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


/** Refill a thin priority queue from the desk's own people. Everyone found goes through the ordinary triage. */
export async function startCampaign(jobId: string, _: FormState, form: FormData): Promise<FormState> {
  const cap = Number(form.get("cap") || 25);
  let c: { added: number; priority_added: number; spent: number; status: string; stop_reason: string | null };
  try {
    c = await apiJson(`/v1/jobs/${jobId}/campaigns`, { source: "desk", cap });
  } catch (e) {
    return fail(e);
  }
  revalidatePath(`/jobs/${jobId}`);
  const why = c.stop_reason === "cap" ? "stopped at the cap" : c.stop_reason === "target_reached" ? "priority target reached" : "no one else on the desk matches";
  return { message: `Looked at ${c.spent}, added ${c.added} (${c.priority_added} priority); ${why}.` };
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

/** Queue fresh public research for a company (even if its facts are still fresh); the workers do the rest. */
export async function researchCompany(companyId: string): Promise<void> {
  await idempotent(() => api(`/v1/companies/${companyId}/research`, { method: "POST" }));
  revalidatePath(`/companies/${companyId}`);
}

/** Un-archive a person the coverage rule archived; the rule then leaves them be. */
export async function bringBack(candidateId: string, path: string): Promise<void> {
  await idempotent(() => apiJson(`/v1/candidates/${candidateId}/bring-back`, {}));
  revalidatePath(path);
  revalidatePath("/people");
}

/** Open a job to countries beyond the desk's coverage (names or codes, comma separated). */
export async function setJobCountries(jobId: string, _: FormState, form: FormData): Promise<FormState> {
  const countries = String(form.get("countries") ?? "").split(",").map((c) => c.trim()).filter(Boolean);
  try {
    await api(`/v1/jobs/${jobId}/countries`, { method: "PUT", body: JSON.stringify({ countries }), headers: { "Content-Type": "application/json" } });
  } catch (e) {
    return fail(e);
  }
  revalidatePath(`/jobs/${jobId}`);
  return { message: countries.length ? "Saved. People on this job were checked again." : "Cleared. People on this job were checked again." };
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

/** Paste the notes from the hiring manager call: requirements are read from them, each with its quote. */
export async function addIntake(jobId: string, _: FormState, form: FormData): Promise<FormState> {
  const text = String(form.get("text") ?? "").trim();
  try {
    const r = await apiJson<{ written: number; replaced: number; seen: number; rejected: { item: string; reason: string }[] }>(
      `/v1/jobs/${jobId}/intake`, { text });
    revalidatePath(`/jobs/${jobId}`);
    const left = r.rejected.length ? ` Left out ${r.rejected.length}: ${r.rejected.map((x) => `${x.item} (${x.reason})`).join("; ")}.` : "";
    return { message: `Read ${r.written} requirement${r.written === 1 ? "" : "s"} (${r.replaced} replacing what the ad said, ${r.seen} already there).${left}` };
  } catch (e) {
    return fail(e);
  }
}

/** A requirement the recruiter types: saved as approved. */
export async function addRequirement(jobId: string, _: FormState, form: FormData): Promise<FormState> {
  const category = String(form.get("category") || "");
  const text_raw = String(form.get("text_raw") || "").trim();
  const list = (name: string) => form.getAll(name).map(String).filter(Boolean);
  if (!text_raw) return { error: "Describe the requirement in a few words." };
  const body: Record<string, unknown> = { category, strength: String(form.get("strength") || "must"), text_raw };
  if (category === "role") Object.assign(body, { role_family: form.get("role_family") || null, level: form.get("level") || null,
    min_years: form.get("min_years") ? Number(form.get("min_years")) : null });
  if (category === "employer") body.employer_kinds = list("employer_kinds");
  if (category === "domain") body.domains = list("domains");
  if (category === "target_company") body.companies = text_raw.split(",").map((s) => s.trim()).filter(Boolean);
  if (category === "employment") body.employment = form.get("employment") || "permanent";
  if (category === "skill") body.normalized_token = text_raw.toLowerCase();
  try {
    await apiJson(`/v1/jobs/${jobId}/requirements`, body);
  } catch (e) {
    return fail(e);
  }
  revalidatePath(`/jobs/${jobId}`);
  return { message: "Added as an approved requirement." };
}

/** Change how much a requirement matters. */
export async function setStrength(claimId: string, path: string, form: FormData): Promise<void> {
  await idempotent(() => apiJson(`/v1/requirements/${claimId}/strength`, { strength: String(form.get("strength")) }));
  revalidatePath(path);
}

/** Capture an answer from the call (the outcome comes from the button pressed). */
export async function answerBrief(itemId: string, path: string, form: FormData): Promise<void> {
  const outcome = String(form.get("outcome") || "noted");
  const answer = String(form.get("answer") || "").trim();
  await idempotent(() => apiJson(`/v1/brief/${itemId}/answer`, { outcome, answer: answer || null }));
  revalidatePath(path);
}

export async function briefAsked(itemId: string, path: string): Promise<void> {
  await idempotent(() => apiJson(`/v1/brief/${itemId}/asked`, {}));
  revalidatePath(path);
}

export async function briefDismiss(itemId: string, path: string): Promise<void> {
  await idempotent(() => apiJson(`/v1/brief/${itemId}/dismiss`, {}));
  revalidatePath(path);
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

export async function removeActivity(activityId: string, path: string): Promise<void> {
  await idempotent(() => api(`/v1/activities/${activityId}`, { method: "DELETE" }));
  revalidatePath(path);
}

export async function tagPerson(candidateId: string, path: string, form: FormData): Promise<void> {
  const tag = String(form.get("tag") || "").trim();
  if (!tag) return;
  await idempotent(() => apiJson(`/v1/candidates/${candidateId}/tags`, { tag }));
  revalidatePath(path);
  revalidatePath("/people");
}

export async function untagPerson(candidateId: string, tag: string, path: string): Promise<void> {
  await idempotent(() => api(`/v1/candidates/${candidateId}/tags/${encodeURIComponent(tag)}`, { method: "DELETE" }));
  revalidatePath(path);
  revalidatePath("/people");
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

export async function removeContact(contactId: string, path: string): Promise<void> {
  await idempotent(() => api(`/v1/contacts/${contactId}`, { method: "DELETE" }));
  revalidatePath(path);
}

/** Lift a client's block, with a note saying why. */
export async function liftBlock(blockId: string, path: string, form: FormData): Promise<void> {
  const note = String(form.get("note") || "").trim();
  if (!note) return;
  await idempotent(() => apiJson(`/v1/blocks/${blockId}/lift`, { note }));
  revalidatePath(path);
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

export async function importRows(batchId: string, path: string, form: FormData): Promise<void> {
  const row_ids = form.getAll("row").map(String);
  if (!row_ids.length) return;
  await apiJson(`/v1/imports/${batchId}/import`, { row_ids });
  revalidatePath(path);
  revalidatePath("/people");
}

export async function acceptImportQuote(batchId: string, path: string): Promise<void> {
  await idempotent(() => apiJson(`/v1/imports/${batchId}/quote/accept`, {}));
  revalidatePath(path);
}

// --- messages and mailbox (Slice 4, step 5): drafts only; you send from your own mailbox ---

export type MessageState = FormState & { link?: string };

export async function draftMessage(candidateId: string, path: string, _: FormState, form: FormData): Promise<FormState> {
  const kind = String(form.get("kind") || "candidate_outreach");
  const contact = String(form.get("contact_id") || "");
  const [contactId, contactJob] = contact ? contact.split("|") : [null, null];
  const body = {
    kind, candidate_id: candidateId, contact_id: contactId,
    job_id: contactJob || String(form.get("job_id") || "") || null,
    note: String(form.get("note") || "").trim() || null,
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

export async function disconnectMailbox(): Promise<void> {
  await idempotent(() => api("/v1/mailbox", { method: "DELETE" }));
  revalidatePath("/mailbox");
}

export async function syncMailbox(path: string): Promise<void> {
  await idempotent(() => apiJson("/v1/mailbox/sync", {}));
  revalidatePath(path);
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

export async function setMemberRole(userId: string, form: FormData): Promise<void> {
  // Not idempotent(): "a desk needs at least one owner" must be shown, not swallowed.
  await apiRaw(`/v1/members/${userId}`, { method: "PATCH", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role: String(form.get("role") || "recruiter") }) });
  revalidatePath("/members");
}

export async function removeMember(userId: string): Promise<void> {
  await apiRaw(`/v1/members/${userId}`, { method: "DELETE" });
  revalidatePath("/members");
}
