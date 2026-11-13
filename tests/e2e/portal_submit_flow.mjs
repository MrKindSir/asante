/** Browser UI smoke: login → new project chat → shape save (upload/submit stay API e2e).
 *
 * Requires Playwright + Chrome, provisioned test accounts, and the local proxy:
 *   ASANTE_BASE_URL=http://localhost node tests/e2e/portal_submit_flow.mjs
 *
 * Full login→upload→submit→isolation API coverage lives in
 * tests/e2e/test_contributor_submit_flow.py (preferred for API/security regressions).
 */
import assert from 'node:assert/strict';
import { mkdir, readFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const { chromium } = await import(process.env.ASANTE_PLAYWRIGHT_MODULE || 'playwright');
const base = (process.env.ASANTE_BASE_URL || 'http://localhost').replace(/\/$/, '');
const evidence = new URL('../../logs/tests/e2e/portal-submit-flow/', import.meta.url).pathname;
await mkdir(evidence, { recursive: true });

const accountsPath = resolve(new URL('../../.env.asante-test-accounts', import.meta.url).pathname);
const passwords = Object.fromEntries(
  (await readFile(accountsPath, 'utf8'))
    .split('\n')
    .filter((line) => line && !line.startsWith('#') && line.includes('='))
    .map((line) => line.split('=', 2)),
);
const password = passwords.ASANTE_TEST_NOMSA_PASSWORD;
if (!password) throw new Error('Missing ASANTE_TEST_NOMSA_PASSWORD in .env.asante-test-accounts');

const browser = await chromium.launch({ headless: true, channel: process.env.ASANTE_BROWSER_CHANNEL || 'chrome' });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
await context.tracing.start({ screenshots: true, snapshots: true });
const page = await context.newPage();
const dialog = () => page.getByRole('dialog');
const shot = (name) => page.screenshot({ path: evidence + name + '.png', fullPage: true });

try {
  await page.goto(base + '/asante/portal/');
  await page.getByLabel('Email', { exact: true }).fill('nomsa@asante.test');
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Sign in →', exact: true }).click();
  await page.getByRole('button', { name: 'New story chat', exact: true }).waitFor();
  await shot('01-signed-in');

  await page.getByRole('button', { name: 'New story chat', exact: true }).click();
  await dialog().getByLabel('Story title').fill('Browser submit-flow smoke story');
  await dialog().getByLabel('Claim, question, or notes').fill('What does the clip show at this landmark?');
  await dialog().locator('.form-save-status').filter({ hasText: /^Saved$/ }).waitFor({ timeout: 15000 });
  await shot('02-shaped-project');
  await dialog().getByRole('button', { name: 'Save and open chat', exact: true }).click();
  await page.waitForURL(/project=/);
  assert.match(page.url(), /project=/);
  await shot('03-project-chat');
  await writeResult({ ok: true, url: page.url() });
} catch (error) {
  await shot('failure');
  await writeResult({ ok: false, error: String(error) });
  throw error;
} finally {
  await context.tracing.stop({ path: evidence + 'trace.zip' });
  await browser.close();
}

async function writeResult(payload) {
  const { writeFile } = await import('node:fs/promises');
  await writeFile(evidence + 'result.json', JSON.stringify(payload, null, 2));
}
