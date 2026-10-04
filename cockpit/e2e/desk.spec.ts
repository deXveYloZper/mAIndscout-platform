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

/** Open a person from the job page, whichever band they are in (bands can move once career profiles arrive). */
async function openPerson(page: Page, name: string) {
  await page.locator("details.band").evaluateAll((els) => els.forEach((el) => ((el as HTMLDetailsElement).open = true)));
  await page.getByRole("link", { name }).first().click();
}

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
  await expect(page.getByRole("status")).toContainText(/Reading \d+ of 4 done/, { timeout: 30_000 });
  const results = page.locator(".results li");
  await expect(results).toHaveCount(4, { timeout: 200_000 });
  // Rows appear as soon as files are queued; wait until every read has finished before checking bands.
  await expect(results.filter({ hasText: /reading…|waiting/ })).toHaveCount(0, { timeout: 200_000 });
  await expect(results.filter({ hasText: "Ioannis" })).toContainText("Priority");
  await expect(results.filter({ hasText: "Jure" })).toContainText("Do not submit");
  await expect(results.filter({ hasText: "Priority" })).toHaveCount(1);
  await expect(results.filter({ hasText: "no evidence of insar (must-have)" })).toHaveCount(3);
  // The page itself is refreshed with the new people. Once his career profile is built (in the background, a real
  // model call), matching may move Ioannis between Priority and Review later; the InSAR rule keeps the other three out.
  await expect(page.locator("summary", { hasText: "Do not submit (3)" })).toBeVisible();
  await page.locator("details.band").evaluateAll((els) => els.forEach((el) => ((el as HTMLDetailsElement).open = true)));
  await expect(page.getByRole("link", { name: "Ioannis Gkanatsios" }).first()).toBeVisible();
});

test("a job can be opened to more countries, and nobody here is archived", async ({ page }) => {
  await page.goto(catalystUrl);
  await expect(page.locator("summary", { hasText: "Archived: outside coverage (0)" })).toBeVisible();
  const field = page.getByLabel("Also accept people living or working in");
  await field.fill("Brazil, Atlantis");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Atlantis" })).toBeVisible();
  await field.fill("Brazil");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Saved" })).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Also accept people living or working in")).toHaveValue("Brazil");
  await page.getByLabel("Also accept people living or working in").fill("");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Cleared" })).toBeVisible();
});

test("a person on a job opens as a gap table, with no overall score", async ({ page }) => {
  await page.goto(catalystUrl);
  await openPerson(page, "Ioannis Gkanatsios");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Ioannis Gkanatsios");
  const insar = page.locator("table.gaps tr", { hasText: /InSAR/ }).first();
  await expect(insar.locator(".verdict")).toHaveText("Met");
  await expect(insar).toContainText("decides the band");
  await expect(page.getByText("There is no overall score, by design")).toBeVisible();
  await expect(page.locator("body")).not.toContainText(/\d+\s*%/);
  await expect(page.locator(".counts")).toContainText("Evidence:");
  // Nothing is approved yet, so the picture is reported as thin, in counts, never a percentage.
  await expect(page.locator(".coverage")).toContainText("must-haves rest on approved facts: below the floor");
});

test("recording a missing must-have as a fact moves the band, and the history says why", async ({ page }) => {
  await page.goto(catalystUrl);
  await page.locator("summary", { hasText: /Do not submit \(\d+\)/ }).click();
  await page.getByRole("link", { name: /Jure Domajnko/ }).click();
  await expect(page.locator(".bandtag").first()).toHaveText("Do not submit");
  await page.getByRole("button", { name: "They have insar" }).click();
  // The deciding fact is recorded, so the InSAR rule no longer decides. Matching may still keep a software engineer
  // out of an earth-observation role for its other must-haves; either way the reason and the history say why.
  await expect(page.locator("p.sub").filter({ hasText: "no evidence of insar" })).toHaveCount(0);
  const history = page.locator(".history li").last();
  await expect(history).toContainText("fact typed");
  // Put back for the rest of the day: a band set by hand stays.
  await page.getByLabel("Band", { exact: true }).selectOption("do_not_submit");
  await page.getByLabel("Reason for changing the band").fill("e2e reset");
  await page.getByRole("button", { name: "Set" }).click();
  await expect(page.locator(".bandtag").first()).toHaveText("Do not submit");
});

test("a pair moves through the pipeline: passed with a reason, reopened, submitted, all in the history", async ({ page }) => {
  await page.goto(catalystUrl);
  await openPerson(page, "Ioannis Gkanatsios");
  await expect(page.locator(".statetag").first()).toHaveText("new");
  await page.getByLabel("Move to").selectOption("seen");
  await page.getByRole("button", { name: "Move" }).click();
  await expect(page.locator(".statetag").first()).toHaveText("seen");
  await page.getByLabel("Move to").selectOption("we_passed");
  await page.getByLabel("Reason for passing").selectOption("compensation");
  await page.getByRole("button", { name: "Move" }).click();
  await expect(page.locator(".statetag").first()).toHaveText("we passed");
  await page.getByLabel("Move to").selectOption("contacted");
  await page.getByLabel("Note for this move").fill("budget raised");
  await page.getByRole("button", { name: "Move" }).click();
  await expect(page.locator(".statetag").first()).toHaveText("contacted");
  await page.getByLabel("Move to").selectOption("submitted");
  await page.getByLabel("Note for this move").fill("sent to the hiring lead");
  await page.getByRole("button", { name: "Move" }).click();
  await expect(page.locator(".statetag").first()).toHaveText("submitted");
  const history = page.locator(".history");
  await expect(history).toContainText("seen → we passed");
  await expect(history).toContainText("we passed → contacted");
  await expect(history).toContainText("contacted → submitted");
  await page.goto(catalystUrl);
  await expect(page.locator(".people li", { hasText: "Ioannis" }).locator(".statetag")).toHaveText("submitted");
  await expect(page.locator(".stages")).toContainText("submitted 1");
});

test("a stale advertisement warns before anyone is submitted", async ({ page }) => {
  await page.goto("/");
  await page.locator('input[type="file"]').setInputFiles(PROCURE);
  await page.getByRole("button", { name: "Read ad" }).click();
  await expect(page).toHaveURL(/\/jobs\//, { timeout: 120_000 });
  await expect(page.getByText(/process dates have passed/)).toBeVisible();
  await expect(page.locator("p.sub").first()).toContainText("Procure Ai");
  // Residence, visa and relocation are three separate facts, never one location score.
  const mobility = page.locator("ul.reqs").first();
  await expect(mobility).toContainText("Must live in or work from: Germany, United Kingdom");
  await expect(mobility).toContainText("Visa sponsorship: not offered");
  await expect(mobility).toContainText("Relocation assistance: not offered");
});

test("intake notes from the hiring manager become a hiring profile, each with its quote", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: /AI Product Engineer/ }).click();
  await expect(page.getByRole("heading", { name: "Hiring profile" })).toBeVisible();
  await page.getByLabel("Notes from the call with the hiring manager").fill(
    "Early-stage start-up experience is a strong plus. Procurement domain experience is a strong plus and can " +
    "substitute for start-up experience. Must be a great culture fit. Permanent role, not contract.");
  await page.getByRole("button", { name: "Read the notes" }).click();
  await expect(page.getByRole("status").filter({ hasText: /Read \d+ requirement/ })).toBeVisible({ timeout: 90_000 });
  await expect(page.locator(".hiring")).toContainText("from the intake notes");
  await expect(page.locator(".hiring h3.group", { hasText: "Strong plus" })).toBeVisible();
  // Personality, culture or fit never becomes a requirement.
  await expect(page.locator(".hiring ul.reqs").filter({ hasText: /culture/i })).toHaveCount(0);
});

test("a thin job is refilled from the desk's own people, banded by the same rules", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: /AI Product Engineer/ }).click();
  await expect(page.getByText(/priority is thin: 0 of 5/)).toBeVisible();
  await page.getByRole("button", { name: "Find more people" }).click();
  await expect(page.getByRole("status")).toContainText(/Looked at \d+, added \d+/, { timeout: 60_000 });
  await expect(page.locator(".campaigns li").first()).toContainText("desk");
  // People found on the desk now sit on this job in the usual piles, with the usual reasons (any band).
  await page.locator("details.band").evaluateAll((els) => els.forEach((el) => ((el as HTMLDetailsElement).open = true)));
  await expect(page.locator(".people li").first()).toBeVisible();
  await page.locator(".people li a").first().click();
  await expect(page.locator(".history")).toContainText("sourced");
});

test("the desk is searched in plain words, best matches first, each with its reasons", async ({ page }) => {
  await page.goto("/search");
  await expect(page.getByRole("heading", { name: "Search the desk" })).toBeVisible();
  await page.getByLabel("Search people").fill("senior software engineer with react, based in the UK");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page).toHaveURL(/q=senior/);
  // The search is read by a model into criteria the recruiter can see, then ranked by code.
  await expect(page.locator(".understood")).toContainText("Understood as:", { timeout: 60_000 });
  await expect(page.getByRole("heading", { name: /^\d+ (person|people)/ })).toBeVisible();
  await expect(page.locator("body")).not.toContainText(/\d+\s*%/);
});

test("companies from CVs are shared records: who do we know there", async ({ page }) => {
  await page.goto("/companies");
  await expect(page.getByRole("heading", { name: "Companies" })).toBeVisible();
  await page.getByLabel("Search companies").fill("bitpanda");
  await page.getByRole("button", { name: "Search" }).click();
  await page.getByRole("link", { name: /Bitpanda/i }).first().click();
  await expect(page.getByText(/We know \d+ (person|people) who worked here/)).toBeVisible();
  await expect(page.locator(".people li", { hasText: "Jure Domajnko" })).toBeVisible();
});

test("costs are recorded and shown against the budget", async ({ page }) => {
  await page.goto("/costs");
  await expect(page.getByRole("heading", { name: "Costs" })).toBeVisible();
  await expect(page.getByText("Reading CVs")).toBeVisible();
  await expect(page.getByText("Reading job ads")).toBeVisible();
  await expect(page.getByText(/of \$\d+\.\d{2} budget/)).toBeVisible();
});

test("the jobs list shows both jobs with their piles and what waits for review", async ({ page }) => {
  await page.goto("/");
  const rows = page.locator("tbody tr");
  await expect(rows).toHaveCount(2);
  const catalyst = rows.filter({ hasText: "InSAR" });
  // Ioannis is in Priority or Review later (matching may move him once his profile is built); three are out.
  const priority = Number(await catalyst.locator("td").nth(3).textContent());
  const later = Number(await catalyst.locator("td").nth(4).textContent());
  expect(priority + later).toBe(1);
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
  await page.getByRole("link", { name: "Full profile and facts" }).click();
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
  await page.getByRole("link", { name: "Full profile and facts" }).click();
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

test("a person's career profile is built in the background: dimensions, questions, and each job correctable", async ({ page }) => {
  await page.goto("/people");
  const personUrl = (await page.locator("tbody tr").filter({ hasText: "Ioannis" }).getByRole("link", { name: /Ioannis/ }).getAttribute("href"))!;
  // Classification is a real model call made by the workers; reload until the profile is there.
  await expect(async () => {
    await page.goto(personUrl);
    await expect(page.locator(".profile .reading")).toBeVisible({ timeout: 2_000 });
  }).toPass({ timeout: 120_000, intervals: [3_000] });
  await expect(page.getByRole("heading", { name: "Career profile" })).toBeVisible();
  await expect(page.locator("table.dims")).toContainText("Relevant experience");
  await expect(page.locator("table.dims")).toContainText("Stability");
  await expect(page.locator(".profile")).toContainText("There is no overall score, by design");
  await expect(page.locator(".profile")).not.toContainText(/\d+\s*%/);
  await page.locator("summary", { hasText: "How each job was read" }).click();
  await expect(page.getByLabel("Kind of work").first()).toBeVisible();
});

test("a Brief for the call: answers become official, are not asked again, and nothing is sent", async ({ page }) => {
  await page.goto(catalystUrl);
  await openPerson(page, "Ioannis Gkanatsios");
  await page.getByRole("link", { name: "Brief for the call" }).click();
  await expect(page.getByRole("heading", { name: /^Brief: Ioannis/ })).toBeVisible();
  // Priority by default; for anyone else the recruiter can still ask for one.
  const anyway = page.getByRole("link", { name: "Make a Brief anyway" });
  if (await anyway.isVisible()) await anyway.click();
  await expect(page.getByText("Nothing here is ever sent to anyone.")).toBeVisible();
  const notice = page.locator(".brief-item", { hasText: "Notice period and availability" });
  await notice.getByRole("textbox").fill("one month");
  await notice.getByRole("button", { name: "Note it" }).click();
  const answered = page.locator("section", { has: page.getByRole("heading", { name: /^Answered/ }) });
  await expect(answered).toContainText("one month");
  await page.reload();
  await expect(page.locator(".brief-item.open", { hasText: "Notice period and availability" })).toHaveCount(0);
  await expect(answered).toContainText("one month");
});

test("relationship memory: a logged call, last contacted, and a tag that becomes a talent pool", async ({ page }) => {
  await page.goto("/people");
  await page.locator("tbody tr").filter({ hasText: "Ioannis" }).getByRole("link", { name: /Ioannis/ }).click();
  const rel = page.locator("section.relationship");
  // An earlier test answered his Brief (a call), which already counts as contact; the timeline joins it all.
  await expect(rel.locator(".timeline")).toContainText("Brief answer");
  await rel.getByLabel("What happened, in a line").fill("Intro call, open to InSAR roles");
  await rel.getByRole("button", { name: "Log it" }).click();
  await expect(rel.getByRole("status")).toContainText("Logged.");
  await expect(rel).toContainText("Last contacted: today");
  await expect(rel.locator(".timeline")).toContainText("Intro call, open to InSAR roles");
  await rel.getByLabel("Add a tag (talent pool)").fill("InSAR pool");
  await rel.getByRole("button", { name: "Tag" }).click();
  await expect(rel.locator(".chip", { hasText: "insar-pool" })).toBeVisible();
  await page.goto("/people");
  await page.getByRole("link", { name: /insar-pool \(1\)/ }).click();
  await expect(page.locator("tbody tr")).toHaveCount(1);
  await expect(page.locator("tbody tr")).toContainText("Ioannis");
});

test("the Refresh page lists who to re-contact and which clients to reconnect with", async ({ page }) => {
  await page.goto("/refresh");
  await expect(page.getByRole("heading", { name: "Refresh" })).toBeVisible();
  await expect(page.getByRole("heading", { name: /^Re-contact these people/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: /^Clients to reconnect with/ })).toBeVisible();
  // Everyone on this desk was read today, so nobody is stale yet.
  await expect(page.getByText("Nobody is stale.")).toBeVisible();
});

test("import from a CSV: preview, tick what you vouch for, approved facts; export is free", async ({ page }) => {
  await page.goto("/import");
  await expect(page.getByRole("heading", { name: "Import and export" })).toBeVisible();
  const csv = [
    "Full Name,Email,City,Current Company,Job Title,Last Contacted",
    'Maria Importer,maria.importer@example.com,"Berlin, Germany",Acme Space,Senior DevOps Engineer,2023-01-15',
    "No Way To Reach,,London,,,",
  ].join("\n");
  await page.getByLabel("CSV file").setInputFiles({ name: "ats-export.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await page.getByRole("button", { name: "Preview" }).click();
  await expect(page).toHaveURL(/\/import\//);
  await expect(page.locator(".import-rows").first()).toContainText("Maria Importer");
  await expect(page.locator("details.band")).toContainText("cannot use");
  await page.getByRole("button", { name: "Import ticked rows" }).click();
  const imported = page.locator(".import-rows li", { hasText: "Maria Importer" });
  await expect(imported).toContainText("imported");
  await imported.getByRole("link", { name: "open" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Maria Importer");
  // The old system's "last contacted" is a note, never contact.
  await expect(page.locator("section.relationship")).toContainText("Last contacted: never");
  await expect(page.locator("section.relationship .timeline")).toContainText("not counted as contact");
  await page.goto("/import");
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download everyone as CSV" }).click();
  expect((await download).suggestedFilename()).toBe("maindscout-people.csv");
});

test("a typed contact is saved as an approved fact", async ({ page }) => {
  await openJob(page, /InSAR Processing Specialist/);
  await page.locator("summary", { hasText: /Do not submit \(\d+\)/ }).click();
  await page.getByRole("link", { name: /Jure Domajnko/ }).click();
  await page.getByRole("link", { name: "Full profile and facts" }).click();
  const panel = page.locator(".panel", { hasText: "Add or correct a fact" });
  await panel.getByLabel("Kind of fact").selectOption("phone");
  await panel.getByLabel("Value").fill("+43 660 1234567");
  await panel.getByRole("button", { name: "Save" }).click();
  await expect(panel.getByText("Saved as an approved fact.")).toBeVisible();
  await expect(page.locator(".claim", { hasText: "phone: +43 660 1234567" }).getByText("approved")).toBeVisible();
});

test("a recruiter can move someone to another band, with a reason that shows", async ({ page }) => {
  await page.goto(catalystUrl);
  const before = Number((await page.getByRole("heading", { name: /^Priority \(\d+\)/ }).textContent())!.match(/\d+/)![0]);
  await page.locator("summary", { hasText: /Do not submit \(\d+\)/ }).click();
  const row = page.locator(".people li", { hasText: "Jure Domajnko" });
  await row.getByLabel("Band", { exact: true }).selectOption("priority");
  await row.getByLabel("Reason for changing the band").fill("knows radar from side project");
  await row.getByRole("button", { name: "Set" }).click();
  await expect(page.getByRole("heading", { name: new RegExp(`^Priority \\(${before + 1}\\)`) })).toBeVisible();
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
  // Theodor has left the pool (people imported earlier may still be waiting in it).
  await expect(page.locator("tbody tr", { hasText: "Theodor" })).toHaveCount(0);
});

test("forgetting a person needs a typed confirmation, then leaves nothing", async ({ page }) => {
  await openJob(page, /InSAR Processing Specialist/);
  await page.locator("summary", { hasText: /Do not submit \(\d+\)/ }).click();
  await page.getByRole("link", { name: "Yousuf Butt" }).click();
  await page.getByRole("link", { name: "Full profile and facts" }).click();
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
