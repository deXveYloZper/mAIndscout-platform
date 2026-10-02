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

export async function dropCvs(jobId: string, _: FormState, form: FormData): Promise<FormState> {
  const files = filesOf(form);
  if (!files.length) return { error: "Choose one or more CVs (PDF)." };
  const done: string[] = [];
  const failed: string[] = [];
  for (const file of files) {
    try {
      const body = new FormData();
      body.append("file", file);
      await api<ProcessResult>(`/v1/jobs/${jobId}/documents`, { method: "POST", body });
      done.push(file.name);
    } catch (e) {
      failed.push(`${file.name}: ${e instanceof ApiError ? e.message : "failed"}`);
    }
  }
  revalidatePath(`/jobs/${jobId}`);
  return {
    message: `${done.length} of ${files.length} read and banded.`,
    error: failed.length ? failed.join("; ") : undefined,
  };
}

export async function overrideBand(jobId: string, candidateId: string, form: FormData): Promise<void> {
  await apiJson(`/v1/jobs/${jobId}/people/${candidateId}/triage`, {
    band: form.get("band"),
    reason: String(form.get("reason") || "") || null,
  });
  revalidatePath(`/jobs/${jobId}`);
}

export async function approveClaim(claimId: string, path: string): Promise<void> {
  await api(`/v1/claims/${claimId}/approve`, { method: "POST" });
  revalidatePath(path);
}

export async function rejectClaim(claimId: string, path: string, code = "wrong"): Promise<void> {
  await apiJson(`/v1/claims/${claimId}/reject`, { code });
  revalidatePath(path);
}

export async function resolveDecision(decisionId: string, action: string, claimId: string | null, path: string): Promise<void> {
  await apiJson(`/v1/decisions/${decisionId}/resolve`, { action, claim_id: claimId });
  revalidatePath(path);
}

export async function correctContact(candidateId: string, replaces: string, path: string, _: FormState, form: FormData): Promise<FormState> {
  const kind = String(form.get("kind") || "email");
  const value = String(form.get("value") || "").trim();
  if (!value) return { error: "Type the correct value." };
  const normalized =
    kind === "email" ? value.toLowerCase()
    : kind === "phone" ? (value.startsWith("+") ? "+" : "") + value.replace(/\D/g, "")
    : value.toLowerCase().replace(/^(https?:\/\/)?(www\.)?/, "").split("?")[0].replace(/\/$/, "");
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
