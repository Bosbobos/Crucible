import {test, expect} from '@playwright/test';
import type {Page} from '@playwright/test';
import {readFileSync} from 'node:fs';

const topics = [
  {id: 'vault-bayes', questions: 3, label: 'Три вопроса (новых, не из банка)'},
  {id: 'vault-first-order', questions: 4, label: 'Четыре уравнения (новых, не из банка)'},
].map(topic => {
  const text = readFileSync(new URL(`../../../content/topics/${topic.id}/core.md`, import.meta.url), 'utf8');
  return {...topic, text, title: text.match(/^# (.+)$/m)![1]};
});

async function openTopic(page: Page, topic: typeof topics[number]) {
  await page.route('**/api/v1/**', async route => {
    expect(route.request().method()).toBe('GET');
    const path = new URL(route.request().url()).pathname.replace('/api/v1/', '');
    let data: unknown;
    if (path === 'practice/auth/session') data = {csrf: 'synthetic'};
    else if (path === 'practice/current') data = {attempt: null, learning_input_seq: 0};
    else if (path === 'learning/today') data = {settings: {daily_count: 3, timezone: 'Europe/Moscow'}, plan: {items: []}, catalog_available: true};
    else if (path === 'learning/progress') data = {skills: [], applied_practice_seq: 0};
    else if (path === 'practice/attempts') data = {attempts: []};
    else if (path === 'practice/review-queue') data = {questions: []};
    else if (path === 'content/catalog') data = {content_release_id: 'synthetic', problems: [], topics: [{id: topic.id, title: topic.title, materials: {core: true}}]};
    else if (path.startsWith(`content/topics/${topic.id}/`)) data = {...topic, provenance: {kind: 'obsidian_vault'}};
    else throw new Error('Unexpected API request: ' + path);
    await route.fulfill({json: data});
  });
  await page.goto('/');
  await page.getByRole('button', {name: 'Материалы', exact: true}).click();
  await page.locator('.topic-grid .card').getByRole('button').click();
  await expect(page.locator('.chapter-reader')).toBeVisible();
  const contents = page.getByRole('button', {name: /^Содержание/});
  if (await contents.isVisible()) await contents.click();
  await page.getByRole('button', {name: 'Самопроверка', exact: true}).click();
}

for (const topic of topics) {
  for (const width of [1440, 390]) {
    test(`${topic.id}: вопросы видны сразу, ответы раскрываются отдельно (${width})`, async ({page}, testInfo) => {
      await page.setViewportSize({width, height: 1000});
      await openTopic(page, topic);
      const chapter = page.locator('.reader-chapter:not([hidden])');
      const quiz = chapter.locator('.source-callout.quiz');
      const questions = quiz.locator(':scope > ol > li');
      const answers = quiz.locator('details.success');
      await expect(quiz).toContainText(topic.label);
      await expect(questions).toHaveCount(topic.questions);
      for (const question of await questions.all()) await expect(question).toBeVisible({timeout: 3000});
      await expect(answers).not.toHaveAttribute('open', '');
      await expect(answers.locator('li').first()).not.toBeVisible();
      await page.screenshot({path: testInfo.outputPath('quiz.png'), fullPage: true});
      await answers.locator('summary').click();
      await expect(answers.locator('li')).toHaveCount(topic.questions);
      for (const answer of await answers.locator('li').all()) await expect(answer).toBeVisible();
      await page.getByRole('button', {name: 'Следующий раздел', exact: true}).click();
      await page.getByRole('button', {name: 'Предыдущий раздел', exact: true}).click();
      await expect(answers).toHaveAttribute('open', '');
      await expect(questions.first()).toBeVisible();
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    });
  }
}
