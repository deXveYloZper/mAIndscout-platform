import { defineConfig, devices } from "@playwright/test";

// End-to-end tests of the cockpit against a real API, a fresh database and the real model.
// Local only (needs Docker Postgres, XAI_API_KEY in core/.env, and the test_artifacts folder).
// Run: npm run e2e   (about 3 minutes, a few cents of model use)

const ORG = "00000000-0000-0000-0000-0000000000e2";
const TOKEN = "e2e-operator-token";
const API_PORT = 8766;
const UI_PORT = 3002;

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
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1366, height: 900 } } }],
  webServer: [
    {
      command: `python -m maindscout reset-db maindscout_e2e --org-id ${ORG} && python -m maindscout serve --port ${API_PORT} --database maindscout_e2e`,
      cwd: "../core",
      url: `http://127.0.0.1:${API_PORT}/v1/health`,
      reuseExistingServer: false,
      timeout: 120_000,
      // RESEARCH_AUTO off: e2e must not pay for real company research on every run.
      env: { OPERATOR_TOKEN: TOKEN, SUPPRESSION_KEY: "e2e-suppression-key", BLOB_DIR: ".blobs-e2e", RESEARCH_AUTO: "false" },
    },
    {
      command: `npx next build && npx next start -p ${UI_PORT}`,
      url: `http://127.0.0.1:${UI_PORT}`,
      reuseExistingServer: false,
      timeout: 300_000,
      env: {
        NEXT_DIST_DIR: ".next-e2e",
        MAINDSCOUT_API: `http://127.0.0.1:${API_PORT}`,
        OPERATOR_TOKEN: TOKEN,
        ORG_ID: ORG,
      },
    },
  ],
});
