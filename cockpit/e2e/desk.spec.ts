import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

// One recruiter's day, in order, through the real cockpit. Uses real files from test_artifacts.
const FOLDER = process.env.TEST_ARTIFACTS ?? path.join(os.homedir(), "Downloads", "test_artifacts");
const file = (name: string) => path.join(FOLDER, name);
const CATALYST = file("Catalyst - InSAR Processing Specialist.pdf");
const PROCURE = file("AI Product Engineer (m_f_d) - full stack; all levels _ Careers at Procure Ai.pdf");
const POOL_CV = file("Theodor Istrate CV.pdf");
const CVS = ["IoannisGkanatsios.pdf", "Jure Domajnko - CV.pdf", "2026 Ovi Grigorescu Resume.pdf", "Yousuf Butt - CV.pdf"].map(file);

test.skip(![CATALYST, PROCURE, POOL_CV, ...CVS].every((f) => fs.existsSync(f)), "test_artifacts folder not available");
test.describe.configure({ mode: "serial" });

let catalystUrl = "";

async function openJob(page: Page, title: RegExp) {
  await page.goto("/");
  await page.getByRole("link", { name: title }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(title);
}

test("an empty desk explains itself", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Jobs" })).toBeVisible();
  await expect(page.getByText("No jobs yet.")).toBeVisible();
  await page.goto("/inbox");
  await expect(page.getByText("Nothing waiting.")).toBeVisible();
});

test("a job is created from its advertisement", async ({ page }) => {
  await page.goto("/");
  await page.locator('input[type="file"]').setInputFiles(CATALYST);
  await page.getByRole("button", { name: "Read ad" }).click();
  await expect(page).toHaveURL(/\/jobs\//, { timeout: 120_000 });
  catalystUrl = page.url();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(/InSAR Processing Specialist/);
  await expect(page.getByText("decides the band").first()).toBeVisible();
  await expect(page.locator(".where")).toContainText("Markham");
  await expect(page.locator(".where")).toContainText("Gatineau");
  await expect(page.getByText(/process dates have passed/)).toHaveCount(0);
});

test("CVs dropped on a job are read one by one and each is banded", async ({ page }) => {
  await page.goto(catalystUrl);
  await page.locator('input[type="file"]').setInputFiles(CVS);
  await page.getByRole("button", { name: "Read and band 4 CVs" }).click();
  await expect(page.getByRole("status")).toContainText("Reading", { timeout: 30_000 });
  const results = page.locator(".results li");
  await expect(results).toHaveCount(4, { timeout: 200_000 });
  await expect(results.filter({ hasText: "Ioannis" })).toContainText("Priority");
  await expect(results.filter({ hasText: "Jure" })).toContainText("Do not submit");
  await expect(results.filter({ hasText: "Priority" })).toHaveCount(1);
  await expect(results.filter({ hasText: "no evidence of insar (must-have)" })).toHaveCount(3);
  // The page itself is refreshed with the new people.
  await expect(page.getByRole("heading", { name: /Priority \(1\)/ })).toBeVisible();
  await expect(page.locator("summary", { hasText: "Do not submit (3)" })).toBeVisible();
});

test("a stale advertisement warns before anyone is submitted", async ({ page }) => {
  await page.goto("/");
  await page.locator('input[type="file"]').setInputFiles(PROCURE);
  await page.getByRole("button", { name: "Read ad" }).click();
  await expect(page).toHaveURL(/\/jobs\//, { timeout: 120_000 });
  await expect(page.getByText(/process dates have passed/)).toBeVisible();
  await expect(page.locator("p.sub").first()).toContainText("Procure Ai");
});

test("the jobs list shows both jobs with their piles and what waits for review", async ({ page }) => {
  await page.goto("/");
  const rows = page.locator("tbody tr");
  await expect(rows).toHaveCount(2);
  const catalyst = rows.filter({ hasText: "InSAR" });
  await expect(catalyst.locator("td").nth(3)).toHaveText("1"); // priority
  await expect(catalyst.locator("td").nth(5)).toHaveText("3"); // do not submit
});

test("the job inbox defaults to priority people; the all-jobs inbox shows the blocking questions", async ({ page }) => {
  await page.goto(catalystUrl);
  await page.getByRole("link", { name: /inbox clear|to review/ }).click();
  await expect(page.getByRole("link", { name: "Priority people" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByText("Nothing waiting.")).toBeVisible(); // Ioannis has nothing blocking
  await page.getByRole("link", { name: "Everyone on this job" }).click();
  await expect(page.getByText("Confirm a contact")).toBeVisible();
  await expect(page.getByText("Who is this?")).toBeVisible();
  await page.goto("/inbox");
  await expect(page.getByRole("heading", { name: "Inbox: all jobs" })).toBeVisible();
  // Blocking items come first.
  await expect(page.locator(".card").first()).toHaveClass(/blocking/);
});

test("a name the machine could not read is typed in the inbox and becomes official", async ({ page }) => {
  await page.goto("/inbox");
  const card = page.locator(".card", { hasText: "Who is this?" });
  await card.getByLabel("Value").fill("Yousuf Butt");
  await card.getByRole("button", { name: "Save name" }).click();
  await expect(page.locator(".card", { hasText: "Who is this?" })).toHaveCount(0);
  await openJob(page, /InSAR Processing Specialist/);
  await page.locator("summary", { hasText: /Do not submit \(\d+\)/ }).click();
  await page.getByRole("link", { name: "Yousuf Butt" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Yousuf Butt");
  await expect(page.locator(".claim", { hasText: "Yousuf Butt" }).getByText("approved")).toBeVisible();
});

test("a contact the file disagrees about is confirmed as it is", async ({ page }) => {
  await page.goto("/inbox");
  const card = page.locator(".card", { hasText: "Confirm a contact" });
  await expect(card).toContainText("The file's own link says");
  await card.getByRole("button", { name: "It is right: approve" }).click();
  await expect(page.locator(".card", { hasText: "Confirm a contact" })).toHaveCount(0);
});

test("facts are approved and rejected one by one on the person page", async ({ page }) => {
  await openJob(page, /InSAR Processing Specialist/);
  await page.locator("summary", { hasText: /Do not submit \(\d+\)/ }).click();
  await page.getByRole("link", { name: /Jure Domajnko/ }).click();
  const name = page.locator(".claim").filter({ hasText: /Jure Domajnko/ }).first();
  await name.getByRole("button", { name: "Approve" }).click();
  await expect(name.getByText("approved")).toBeVisible();
  const firstPlace = page.locator("section", { has: page.getByRole("heading", { name: "Location" }) }).locator(".claim").first();
  const placeText = (await firstPlace.locator(".what").innerText()).trim();
  await firstPlace.getByRole("button", { name: "Reject" }).click();
  await expect(page.locator(".claim", { has: page.locator(".what", { hasText: placeText }) }).getByText("rejected")).toBeVisible();
  // Every fact can show where it came from, with a link to the original file.
  await page.locator(".claim details summary").first().click();
  const original = page.locator(".snippet cite a").first();
  const href = await original.getAttribute("href");
  const res = await page.request.get(href!);
  expect(res.status()).toBe(200);
  expect(res.headers()["content-type"]).toContain("application/pdf");
});

test("a typed contact is saved as an approved fact", async ({ page }) => {
  await openJob(page, /InSAR Processing Specialist/);
  await page.locator("summary", { hasText: /Do not submit \(\d+\)/ }).click();
  await page.getByRole("link", { name: /Jure Domajnko/ }).click();
  const panel = page.locator(".panel", { hasText: "Add or correct a fact" });
  await panel.getByLabel("Kind of fact").selectOption("phone");
  await panel.getByLabel("Value").fill("+43 660 1234567");
  await panel.getByRole("button", { name: "Save" }).click();
  await expect(panel.getByText("Saved as an approved fact.")).toBeVisible();
  await expect(page.locator(".claim", { hasText: "phone: +43 660 1234567" }).getByText("approved")).toBeVisible();
});

test("a recruiter can move someone to another band, with a reason that shows", async ({ page }) => {
  await page.goto(catalystUrl);
  await page.locator("summary", { hasText: /Do not submit \(\d+\)/ }).click();
  const row = page.locator(".people li", { hasText: "Jure Domajnko" });
  await row.getByLabel("Band", { exact: true }).selectOption("priority");
  await row.getByLabel("Reason for changing the band").fill("knows radar from side project");
  await row.getByRole("button", { name: "Set" }).click();
  await expect(page.getByRole("heading", { name: /Priority \(2\)/ })).toBeVisible();
  await expect(page.locator(".people li", { hasText: "Jure Domajnko" })).toContainText("set by hand: knows radar from side project");
});

test("a CV with no job joins the pool and is put on a job later", async ({ page }) => {
  await page.goto("/people");
  await page.locator('input[type="file"]').setInputFiles(POOL_CV);
  await page.getByRole("button", { name: "Read and band" }).click();
  await expect(page.locator(".results li")).toContainText("in the pool", { timeout: 120_000 });
  await page.getByRole("link", { name: "Not on a job" }).click();
  const row = page.locator("tbody tr", { hasText: "Theodor" });
  await expect(row).toContainText("in the pool");
  await row.getByRole("link", { name: /Theodor/ }).click();
  await expect(page.getByText("Not on any job yet (in the pool).")).toBeVisible();
  await page.getByLabel("Job to put this person on").selectOption({ label: "InSAR Processing Specialist" });
  await page.getByRole("button", { name: "Put on job" }).click();
  await expect(page.locator(".people li", { hasText: "InSAR Processing Specialist" })).toContainText(/Do not submit|Priority|Review later/);
  await page.goto("/people?show=pool");
  await expect(page.getByText("Nobody is waiting without a job.")).toBeVisible();
});

test("forgetting a person needs a typed confirmation, then leaves nothing", async ({ page }) => {
  await openJob(page, /InSAR Processing Specialist/);
  await page.locator("summary", { hasText: /Do not submit \(\d+\)/ }).click();
  await page.getByRole("link", { name: "Yousuf Butt" }).click();
  const danger = page.locator("details.danger");
  await danger.locator("summary").click();
  await danger.getByLabel("Type forget to confirm").fill("delete");
  await danger.getByRole("button", { name: "Erase" }).click();
  await expect(danger.getByText(/Type "forget" to confirm/)).toBeVisible();
  await danger.getByLabel("Type forget to confirm").fill("forget");
  await danger.getByRole("button", { name: "Erase" }).click();
  await expect(page).toHaveURL(/erased=1/);
  await expect(page.getByText("The person was erased and the check found nothing left.")).toBeVisible();
  await page.goto(catalystUrl);
  await expect(page.getByText("Yousuf Butt")).toHaveCount(0);
});

test("an erased person uploaded again is not stored", async ({ page }) => {
  await page.goto(catalystUrl);
  await page.locator('input[type="file"]').setInputFiles(CVS[3]);
  await page.getByRole("button", { name: "Read and band" }).click();
  await expect(page.locator(".results li")).toContainText("Not stored: this person was erased earlier.", { timeout: 120_000 });
});

test("an unknown person shows a readable not-found page, not a crash", async ({ page }) => {
  await page.goto("/people/11111111-1111-1111-1111-111111111111");
  await expect(page.getByRole("heading", { name: "Not found" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Back to jobs" })).toBeVisible();
});

test("keyboard users can skip to content, and every control has a name", async ({ page }) => {
  await page.goto(catalystUrl);
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
  const unnamed = await page.locator("input:not([type=hidden]), select, button").evaluateAll((els) =>
    els.filter((el) => {
      const e = el as HTMLInputElement;
      return !(e.labels?.length || e.getAttribute("aria-label") || e.textContent?.trim() || e.getAttribute("placeholder"));
    }).length,
  );
  expect(unnamed).toBe(0);
});

test("pages fit a phone screen without sideways scrolling", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  for (const url of ["/", catalystUrl, "/inbox", "/people"]) {
    await page.goto(url);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, url).toBeLessThanOrEqual(1);
  }
});
