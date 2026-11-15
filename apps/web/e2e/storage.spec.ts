import {test, expect} from '@playwright/test';

test('renaming preserves emergency drafts, pending command ids and exercise answers', async ({page}) => {
  await page.addInitScript(() => {
    localStorage.setItem('previous-emergency-attempt', '{"draft":"Keep this draft","revision":7}');
    localStorage.setItem('previous-pending-command', '{"payload":{"command_id":"keep-command-id"}}');
    localStorage.setItem('previous-vault-try:primer:question', '{"answer":"7/2"}');
    localStorage.setItem('unrelated-preference', 'keep');
  });
  await page.goto('/');
  await expect(page).toHaveTitle('Crucible · Математика');
  await expect.poll(() => page.evaluate(() => localStorage.getItem('crucible-emergency-attempt')))
    .toBe('{"draft":"Keep this draft","revision":7}');
  const values = await page.evaluate(() => ({...localStorage}));
  expect(values['crucible-pending-command']).toContain('keep-command-id');
  expect(values['crucible-vault-try:primer:question']).toBe('{"answer":"7/2"}');
  expect(values['unrelated-preference']).toBe('keep');
  expect(values['previous-emergency-attempt']).toBeUndefined();
});

test('renaming keeps both values when an existing draft conflicts', async ({page}) => {
  await page.addInitScript(() => {
    localStorage.setItem('previous-emergency-attempt', 'old draft');
    localStorage.setItem('crucible-emergency-attempt', 'current draft');
  });
  await page.goto('/');
  await expect(page).toHaveTitle('Crucible · Математика');
  expect(await page.evaluate(() => localStorage.getItem('crucible-emergency-attempt'))).toBe('current draft');
  expect(await page.evaluate(() => localStorage.getItem('previous-emergency-attempt'))).toBe('old draft');
});
