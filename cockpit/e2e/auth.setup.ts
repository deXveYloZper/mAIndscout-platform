import { createHmac } from "node:crypto";
import { expect, test as setup } from "@playwright/test";
import { E2E_USER, STATE } from "../playwright.config";

/** The current six-digit code for a base32 secret (RFC 6238, like an authenticator app). */
export function totp(secret: string, at = Date.now()): string {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const c of secret.replace(/=+$/, "").toUpperCase()) bits += alphabet.indexOf(c).toString(2).padStart(5, "0");
  const key = Buffer.from(bits.match(/.{8}/g)!.map((b) => parseInt(b, 2)));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(at / 1000 / 30)));
  const mac = createHmac("sha1", key).update(counter).digest();
  const offset = mac[mac.length - 1] & 0x0f;
  return String((mac.readUInt32BE(offset) & 0x7fffffff) % 1_000_000).padStart(6, "0");
}

setup("the owner signs in with a password and a two-step code", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login/);
  await page.getByLabel("Email").fill(E2E_USER.email);
  await page.getByLabel("Password").fill(E2E_USER.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByLabel("Code from your authenticator app").fill(totp(E2E_USER.totp));
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { name: "Jobs" })).toBeVisible();
  expect(await page.evaluate(() => document.cookie)).not.toContain("ms_session"); // httpOnly: never readable by scripts
  await page.context().storageState({ path: STATE });
});
