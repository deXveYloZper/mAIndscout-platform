import { defineConfig, devices } from "@playwright/test";

// End-to-end tests of the cockpit against a real API, a fresh database and the real model.
// Local only (needs Docker Postgres, XAI_API_KEY in core/.env, and the test_artifacts folder).
// Run: npm run e2e   (about 3 minutes, a few cents of model use)
//
// A test owner (with two-step codes) is created in the fresh database; `e2e/auth.setup.ts` signs in through the real
// login page once and every test reuses that session.

const ORG = "00000000-0000-0000-0000-0000000000e2";
const API_PORT = 8766;
const UI_PORT = 3002;
export const E2E_USER = { email: "e2e-owner@desk.test", password: "copper-lantern-meadow-41", totp: "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP" };
export const STATE = "playwright/.auth/owner.json";

export default defineConfig({
  testDir: "./e2e",
  timeout: 240_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: `http://127.0.0.1:${UI_PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "sign-in", testMatch: /auth\.setup\.ts/, use: { ...devices["Desktop Chrome"] } },
    {
      name: "chromium",
      testMatch: /.*\.spec\.ts/,
      dependencies: ["sign-in"],
      use: { ...devices["Desktop Chrome"], viewport: { width: 1366, height: 900 }, storageState: STATE },
    },
  ],
  webServer: [
    {
      command: `python -m maindscout reset-db maindscout_e2e --org-id ${ORG}`
        + ` && python -m maindscout user create --database maindscout_e2e --org ${ORG} --role owner --email ${E2E_USER.email}`
        + ` --name "E2E Owner" --password-env E2E_PASSWORD --totp-env E2E_TOTP`
        + ` && python -m maindscout serve --port ${API_PORT} --database maindscout_e2e`,
      cwd: "../core",
      url: `http://127.0.0.1:${API_PORT}/v1/health`,
      reuseExistingServer: false,
      timeout: 120_000,
      // RESEARCH_AUTO off: e2e must not pay for real company research on every run.
      env: { SUPPRESSION_KEY: "e2e-suppression-key", AUTH_KEY: "e2e-auth-key", BLOB_DIR: ".blobs-e2e", RESEARCH_AUTO: "false",
        COCKPIT_URL: `http://127.0.0.1:${UI_PORT}`, E2E_PASSWORD: E2E_USER.password, E2E_TOTP: E2E_USER.totp },
    },
    {
      command: `npx next build && npx next start -H 127.0.0.1 -p ${UI_PORT}`,
      url: `http://127.0.0.1:${UI_PORT}/login`,
      reuseExistingServer: false,
      timeout: 300_000,
      env: {
        NEXT_DIST_DIR: ".next-e2e",
        MAINDSCOUT_API: `http://127.0.0.1:${API_PORT}`,
      },
    },
  ],
});
