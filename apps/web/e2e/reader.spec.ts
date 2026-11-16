import {test, expect} from '@playwright/test';
import type {Page} from '@playwright/test';
import {mkdirSync} from 'node:fs';

const paragraph = 'Write a count as a sum of indicators. Each indicator is one when its event occurs and zero otherwise. Linearity of expectation does not require independence.';
const longText = Array.from({length: 16}, () => paragraph).join('\n\n');
const exercise = '```vault-exercise\n' + JSON.stringify({kind: 'ask', id: 'reader-check', q: 'Find $E[X]$ for a fair die.', ans: '7/2', explain: 'Average the six equally likely values.'}) + '\n```';
const material = {
  title: 'Ожидание и индикаторы', widget: 'vault-indicators',
  text: '# Ожидание и индикаторы\n\n' + paragraph + '\n\n' + exercise + '\n\n' + longText +
    '\n\n## Линейность ожидания\n\n> [!note] Linearity\n> Expectation is additive even for dependent variables.\n\n' +
    '| Event | Indicator | Probability | Contribution |\n|---|---|---|---|\n| A fixed point | $I_k$ | $1/n$ | $E[I_k]=1/n$ |\n\n' +
    '$$\n' + Array.from({length: 65}, (_, i) => `X_{${i + 1}}`).join('+') + '\n$$\n\n' + longText +
    '\n\n## Пары индикаторов\n\n' + longText + '\n\n## Самопроверка\n\n' + paragraph,
};
const restoredAttempt = {
  id: 'reader-attempt', state: 'paused', revision: 4, learning_input_seq: 0,
  draft: 'Saved solution: write X as a sum of indicators.', reflection: '',
  active_seconds: 12, unconfirmed_seconds: 0, heartbeat_at: '2026-11-15T12:00:00Z',
  help: [{kind: 'core', mathematical: true}], part_outcomes: [], questions: [], reviews: [], proposals: [],
  problem: {id: 'P-READER', title: 'Count fixed points', statement: 'Find the expected number of fixed points.', section: 'probability', primary_skill_id: 'indicators', level: 2, topic_id: 'reader-0', content_release_id: 'synthetic', materials: {core: true}, parts: [{id: 'a', title: '(a)'}]},
};

test.beforeEach(async ({page}) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname.replace('/api/v1/', '');
    expect(route.request().method()).toBe('GET');
    let data: unknown;
    if (path === 'practice/auth/session') data = {csrf: 'synthetic'};
    else if (path === 'practice/current') data = {attempt: null, learning_input_seq: 0};
    else if (path === 'learning/today') data = {settings: {daily_count: 3, timezone: 'Europe/Moscow'}, plan: {items: []}, catalog_available: true};
    else if (path === 'learning/progress') data = {skills: [], applied_practice_seq: 0};
    else if (path === 'practice/attempts') data = {attempts: []};
    else if (path === 'practice/review-queue') data = {questions: []};
    else if (path === 'practice/attempts/reader-attempt') data = restoredAttempt;
    else if (path === 'content/catalog') data = {content_release_id: 'synthetic', problems: [], topics: [0,1,2].map(i => ({id: 'reader-' + i, title: i ? ['','Линейность и суммы','Вероятности событий'][i] : material.title, materials: {core: true}}))};
    else if (path.startsWith('content/topics/')) data = material;
    else throw new Error('Unexpected API request: ' + path);
    await route.fulfill({json: data});
  });
  await page.goto('/');
  await page.getByRole('button', {name: 'Материалы', exact: true}).click();
  await expect(page.locator('.topic-grid .card')).toHaveCount(3);
  await page.locator('.topic-grid .card').first().getByRole('button').click();
  await expect(page.getByRole('heading', {name: 'Введение', exact: true})).toBeVisible();
  expect(errors).toEqual([]);
});

const current = (page: Page) => page.locator('.reader-chapter:not([hidden])');
async function wheel(page: Page, dx: number, dy: number, dt = 16) {
  // Событие проходит через настоящий non-passive обработчик, без зависимости от ОС.
  return current(page).evaluate((element, delta) => {
    const clock = window as Window & {readerWheelAt?: number};
    clock.readerWheelAt = (clock.readerWheelAt ?? performance.now()) + delta.dt;
    const event = new WheelEvent('wheel', {deltaX: delta.dx, deltaY: delta.dy, bubbles: true, cancelable: true});
    Object.defineProperty(event, 'timeStamp', {value: clock.readerWheelAt});
    return !element.dispatchEvent(event);
  }, {dx, dy, dt});
}
async function wheelRun(page: Page, values: number[], axis: 'x' | 'y' = 'x') {
  for (const value of values) await wheel(page, axis === 'x' ? value : 0, axis === 'y' ? value : 0);
}
async function bottom(page: Page) {
  await expect.poll(() => page.evaluate(async () => {
    await document.fonts.ready;
    window.scrollTo(0, document.documentElement.scrollHeight);
    await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
    return document.querySelector('.reading-paper')!.getBoundingClientRect().bottom <= innerHeight + 2;
  })).toBeTruthy();
}
async function next(page: Page) {await page.getByRole('button', {name: 'Следующий раздел', exact: true}).click();}

test('стрелки листают разделы и сохраняют ответы; ввод и модификаторы не перехватываются', async ({page}) => {
  const answer = page.getByLabel('Ответ', {exact: true});
  await answer.fill('7/2');
  for (const key of ['ArrowLeft', 'ArrowUp', 'ArrowRight', 'ArrowDown']) await answer.press(key);
  await expect(current(page)).toHaveAttribute('aria-label', 'Введение');
  await page.getByRole('button', {name: 'Проверить', exact: true}).click();
  await page.keyboard.press('Control+ArrowRight');
  await page.keyboard.press('Control+ArrowDown');
  await expect(current(page)).toHaveAttribute('aria-label', 'Введение');
  await page.keyboard.press('ArrowRight');
  await expect(current(page)).toHaveAttribute('aria-label', 'Линейность ожидания');
  await expect.poll(() => page.evaluate(() => scrollY)).toBe(0);
  await page.keyboard.press('ArrowUp');
  await expect(answer).toHaveValue('7/2');
  await expect(page.getByRole('region', {name: 'reader-check'}).getByRole('status')).toHaveText('Верно.');
  await page.keyboard.press('ArrowDown');
  await expect(current(page)).toHaveAttribute('aria-label', 'Линейность ожидания');
  await page.keyboard.press('ArrowLeft');
  await expect(current(page)).toHaveAttribute('aria-label', 'Введение');
  await page.keyboard.press('ArrowUp');
  await expect(page.getByRole('button', {name: 'Предыдущий раздел', exact: true})).toBeDisabled();
  for (let i = 0; i < 3; i++) await next(page);
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('ArrowDown');
  await expect(current(page)).toHaveAttribute('aria-label', 'Самопроверка');
  await expect(page.getByRole('button', {name: 'Следующий раздел', exact: true})).toBeDisabled();
});

test('горизонтальные жесты сразу повторяются и меняют направление без ожидания', async ({page}) => {
  await wheel(page, 0, 300);
  await wheelRun(page, [12,24,36,54,72,80,76,65,50,38,26,16,9,5]);
  await expect(current(page)).toHaveAttribute('aria-label', 'Линейность ожидания');
  // Повторный разгон начинается во время хвоста, без паузы и ожидания анимации.
  await wheelRun(page, [8,16,30,45,60,50,35,20,10,5]);
  await expect(current(page)).toHaveAttribute('aria-label', 'Пары индикаторов');
  await wheel(page, -70, 5);
  await expect(current(page)).toHaveAttribute('aria-label', 'Линейность ожидания');
  await wheelRun(page, [-60,-40,-20,-8,-12,-24,-36,-50]);
  await expect(current(page)).toHaveAttribute('aria-label', 'Введение');
  await wheel(page, -90, 0);
  await expect(current(page)).toHaveAttribute('aria-label', 'Введение');
});

test('длинная инерция, единичный всплеск и мелкий отскок не перелистывают повторно', async ({page}) => {
  await wheelRun(page, [12,24,36,54,72,80,76,65,50,38,26,16,9,5,4,3,34,2.8,-1.5,2.5,2]);
  await wheelRun(page, Array.from({length: 80}, (_, i) => 1.9 * 0.96 ** i));
  await expect(current(page)).toHaveAttribute('aria-label', 'Линейность ожидания');
  await wheel(page, -75, 0);
  await expect(current(page)).toHaveAttribute('aria-label', 'Введение');
});

test('настоящие wheel-события прокручивают текст и переключают раздел боковым жестом', async ({page}) => {
  await current(page).locator('.markdown > p').first().hover();
  await page.mouse.wheel(0, 280);
  await expect.poll(() => page.evaluate(() => scrollY)).toBeGreaterThan(0);
  await expect(current(page)).toHaveAttribute('aria-label', 'Введение');
  await page.mouse.move(800, 500);
  await page.mouse.wheel(90, 3);
  await expect(current(page)).toHaveAttribute('aria-label', 'Линейность ожидания');
  await expect.poll(() => page.evaluate(() => scrollY)).toBe(0);
  await current(page).locator('.markdown > p:not(:has(.katex-display))').first().hover();
  await page.mouse.wheel(-90, 1);
  await expect(current(page)).toHaveAttribute('aria-label', 'Введение');
});

test('инерция вертикального скролла не листает у края, новый импульс листает без паузы', async ({page}) => {
  await wheelRun(page, [80,140,180,160,120], 'y');
  await bottom(page);
  await wheelRun(page, [90,65,40,25,12,6], 'y');
  await expect(page.locator('.reader-edge-cue')).toBeHidden();
  await expect(current(page)).toHaveAttribute('aria-label', 'Введение');
  await wheelRun(page, [14,30,60], 'y');
  await expect(page.locator('.reader-edge-cue')).toContainText('следующий раздел');
  await expect(page.locator('.reader-edge-cue')).toBeVisible();
  await expect(current(page)).toHaveAttribute('aria-label', 'Введение');
  await wheelRun(page, [100,140], 'y');
  await expect(current(page)).toHaveAttribute('aria-label', 'Линейность ожидания');
  expect(await wheel(page, 0, 120)).toBe(true); // Хвост не сдвигает новую страницу.
  await wheelRun(page, [90,60,30,12,6], 'y');
  await wheel(page, 0, 15);
  expect(await wheel(page, 0, 35)).toBe(false); // Новый импульс сразу может прокручивать её.
  await expect(current(page)).toHaveAttribute('aria-label', 'Линейность ожидания');
  await expect.poll(() => page.evaluate(() => scrollY)).toBe(0);
  await wheel(page, 0, -100);
  await expect(page.locator('.reader-edge-cue')).toContainText('предыдущий раздел');
  await wheel(page, 0, -150);
  await expect(current(page)).toHaveAttribute('aria-label', 'Введение');
});

test('незавершённый вертикальный жест сбрасывается, первый и последний раздел не зацикливаются', async ({page}) => {
  await wheel(page, 0, -300);
  await expect(current(page)).toHaveAttribute('aria-label', 'Введение');
  await bottom(page);
  await page.waitForTimeout(260);
  await wheel(page, 0, 150, 300);
  await expect(page.locator('.reader-edge-cue')).toBeVisible();
  await page.waitForTimeout(700);
  await expect(page.locator('.reader-edge-cue')).toBeHidden();
  await wheel(page, 0, 150, 700);
  await expect(current(page)).toHaveAttribute('aria-label', 'Введение');
  for (let i = 0; i < 3; i++) await next(page);
  await bottom(page);
  await page.waitForTimeout(260);
  expect(await wheel(page, 0, 500, 300)).toBe(false);
  await expect(current(page)).toHaveAttribute('aria-label', 'Самопроверка');
});

test('плашка не мигает при замедлении, диагональных колебаниях и короткой паузе', async ({page}) => {
  await bottom(page);
  const cue = page.locator('.reader-edge-cue');
  const original = await cue.elementHandle();
  await cue.evaluate(element => {
    const record = window as Window & {cueVisibility?: string[]};
    record.cueVisibility = [];
    new MutationObserver(() => record.cueVisibility!.push(element.getAttribute('data-visible')!))
      .observe(element, {attributes: true, attributeFilter: ['data-visible']});
  });
  await wheel(page, 0, 18, 300);
  await expect(cue).toBeHidden(); // Мелкие движения ещё не показывают плашку.
  await wheel(page, 0, 30);
  await expect(cue).toBeVisible();
  await wheelRun(page, [24,18], 'y');
  await wheel(page, 26, 17);
  await wheel(page, 0, -3);
  await page.waitForTimeout(220);
  await expect(cue).toBeVisible();
  expect(await page.evaluate(() => (window as Window & {cueVisibility?: string[]}).cueVisibility)).toEqual(['true']);
  await wheel(page, 0, 34, 220);
  await wheelRun(page, [45,40,20], 'y');
  await expect(current(page)).toHaveAttribute('aria-label', 'Линейность ожидания');
  await expect(cue).toHaveAttribute('data-visible', 'false');
  expect(await cue.evaluate((element, previous) => element === previous, original)).toBe(true);
  expect(await page.evaluate(() => (window as Window & {cueVisibility?: string[]}).cueVisibility)).toEqual(['true','false']);
});

test('обычный скролл до края не показывает плашку, новое усилие начинает её заполнять', async ({page}) => {
  await wheelRun(page, [80,100,130], 'y');
  await bottom(page);
  await wheelRun(page, [140,135,120,90,60,30,10], 'y');
  await expect(page.locator('.reader-edge-cue')).toBeHidden();
  await expect(current(page)).toHaveAttribute('aria-label', 'Введение');
  await wheelRun(page, [20,40,60], 'y');
  await expect(page.locator('.reader-edge-cue')).toBeVisible();
  await expect(current(page)).toHaveAttribute('aria-label', 'Введение');
});

test('усиленное продолжение скролла у края перелистывает без отпускания пальцев', async ({page}) => {
  await wheelRun(page, [80,100,130], 'y');
  await bottom(page);
  await wheelRun(page, [140,190,250], 'y');
  await expect(current(page)).toHaveAttribute('aria-label', 'Линейность ожидания');
  await wheelRun(page, [200,160,120,80,40,20,8], 'y');
  await expect(current(page)).toHaveAttribute('aria-label', 'Линейность ожидания');
  await expect.poll(() => page.evaluate(() => scrollY)).toBe(0);
});

test('формулы, таблицы, оглавление и лаборатория сохраняют собственное управление', async ({page}) => {
  await next(page);
  const formula = current(page).locator('.katex-display');
  expect(await formula.evaluate(el => el.scrollWidth > el.clientWidth)).toBeTruthy();
  expect(await formula.evaluate(el => el.dispatchEvent(new WheelEvent('wheel', {deltaX: 200, bubbles: true, cancelable: true})))).toBe(true);
  await expect(current(page)).toHaveAttribute('aria-label', 'Линейность ожидания');
  await page.locator('.reader-contents').dispatchEvent('wheel', {deltaX: 200, bubbles: true, cancelable: true});
  await expect(current(page)).toHaveAttribute('aria-label', 'Линейность ожидания');
  await page.setViewportSize({width: 390, height: 844});
  const table = page.getByRole('region', {name: 'Таблица конспекта'});
  expect(await table.evaluate(el => el.scrollWidth > el.clientWidth)).toBeTruthy();
  await table.dispatchEvent('wheel', {deltaX: 200, bubbles: true, cancelable: true});
  await table.focus();
  await page.keyboard.press('ArrowRight');
  // Стрелки прокручивают сфокусированную таблицу.
  await expect(current(page)).toHaveAttribute('aria-label', 'Линейность ожидания');
  await page.getByRole('tab', {name: 'Лаборатория', exact: true}).click();
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('ArrowDown');
  await page.locator('.theory-lab').dispatchEvent('wheel', {deltaX: 300, bubbles: true, cancelable: true});
  await expect(page.locator('.theory-lab')).toBeVisible();
  await page.getByRole('tab', {name: 'Конспект', exact: true}).click();
  await expect(current(page)).toHaveAttribute('aria-label', 'Линейность ожидания');
});

test('переходы анимируются с учётом reduced motion; вёрстка адаптируется без переполнения', async ({page}) => {
  await page.emulateMedia({reducedMotion: 'no-preference'});
  await next(page);
  expect(await current(page).evaluate(el => el.getAnimations().length)).toBeGreaterThan(0);
  await page.emulateMedia({reducedMotion: 'reduce'});
  await next(page);
  expect(await current(page).evaluate(el => el.getAnimations().length)).toBe(0);
  mkdirSync('../../.private/evidence/screenshots', {recursive: true});
  for (const width of [1920,1440,1280,1100,980,768,390]) {
    await page.setViewportSize({width, height: 1000});
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    await expect(page.locator('select')).toHaveCount(0);
    await expect(page.getByRole('button', {name: 'Следующий раздел', exact: true})).toBeVisible();
    if (width === 1440 || width === 390) await page.screenshot({path: `../../.private/evidence/screenshots/reader-gestures-${width}.png`});
  }
  await page.setViewportSize({width: 1440, height: 1000});
  await page.getByRole('button', {name: 'К материалам', exact: false}).first().click();
  await page.screenshot({path: '../../.private/evidence/screenshots/reader-library.png'});
  await page.getByRole('button', {name: 'Сегодня', exact: true}).click();
  await page.screenshot({path: '../../.private/evidence/screenshots/reader-today.png'});
});

test('адрес раздела переживает обновление, а Назад и Вперёд восстанавливают историю чтения', async ({page}) => {
  await expect(page).toHaveURL(/\/materials\/reader-0\?/);
  await next(page);
  await expect(page).toHaveURL(/chapter=2/);
  const address = page.url();
  await page.reload();
  await expect(current(page)).toHaveAttribute('aria-label', 'Линейность ожидания');
  expect(page.url()).toBe(address);
  await page.goBack();
  await expect(current(page)).toHaveAttribute('aria-label', 'Введение');
  await page.goForward();
  await expect(current(page)).toHaveAttribute('aria-label', 'Линейность ожидания');
  await page.getByRole('button', {name: 'Сегодня', exact: true}).click();
  await expect(page).toHaveURL(/\/$/);
  await page.goBack();
  await expect(current(page)).toHaveAttribute('aria-label', 'Линейность ожидания');
});

test('прямые ссылки на раздел и лабораторию открываются после новой загрузки приложения', async ({page}) => {
  await page.goto('/materials/reader-0?part=core&release=synthetic&chapter=3');
  await expect(current(page)).toHaveAttribute('aria-label', 'Пары индикаторов');
  await page.getByRole('tab', {name: 'Лаборатория', exact: true}).click();
  await expect(page).toHaveURL(/view=lab/);
  await page.reload();
  await expect(page.locator('.theory-lab')).toBeVisible();
  await page.getByRole('tab', {name: 'Конспект', exact: true}).click();
  await expect(current(page)).toHaveAttribute('aria-label', 'Пары индикаторов');
  await page.getByRole('button', {name: 'К материалам', exact: false}).first().click();
  await expect(page).toHaveURL(/\/materials$/);
});

test('список материалов, поиск и экран вопросов сохраняются после обновления', async ({page}) => {
  await page.getByRole('button', {name: 'К материалам', exact: false}).first().click();
  await page.getByLabel('Поиск по задачам').fill('fixed points');
  await page.reload();
  await expect(page.getByRole('heading', {name: 'Материалы', exact: true})).toBeVisible();
  await expect(page.getByLabel('Поиск по задачам')).toHaveValue('fixed points');
  await page.getByRole('button', {name: 'Вопросы и разбор', exact: true}).click();
  await expect(page).toHaveURL(/\/questions$/);
  await page.reload();
  await expect(page.getByRole('heading', {name: 'Вопросы и разбор', exact: true})).toBeVisible();
});

test('обновление попытки и её конспекта восстанавливает серверный черновик без изменяющих команд', async ({page}) => {
  await page.goto('/practice/reader-attempt');
  const editor = page.getByRole('textbox', {name: 'Черновик решения'});
  await expect(editor).toHaveText(restoredAttempt.draft);
  await page.reload();
  await expect(editor).toHaveText(restoredAttempt.draft);
  await page.goto('/practice/reader-attempt?material=core&topic=reader-0&release=synthetic&chapter=3');
  await expect(current(page)).toHaveAttribute('aria-label', 'Пары индикаторов');
  await page.reload();
  await expect(current(page)).toHaveAttribute('aria-label', 'Пары индикаторов');
  await page.goBack();
  await expect(page).toHaveURL(/\/practice\/reader-attempt$/);
  await expect(editor).toHaveText(restoredAttempt.draft);
});

test('раскрытая подсказка восстанавливается без повторной команды помощи или сохранения', async ({page}) => {
  let saved={...restoredAttempt},helpCommands=0,patches=0;
  await page.route('**/api/v1/practice/attempts/reader-attempt**',async route=>{
    const request=route.request();
    if(request.method()==='GET'){await route.fulfill({json:saved});return;}
    const body=request.postDataJSON();
    expect(body.command_id).toBeTruthy();
    expect(body.expected_revision).toBe(saved.revision);
    saved={...saved,revision:saved.revision+1};
    if(request.method()==='PATCH'){
      patches++;saved={...saved,draft:body.draft};await route.fulfill({json:saved});
    }else{
      expect(request.method()).toBe('POST');expect(body.kind).toBe('h1');helpCommands++;
      await route.fulfill({json:{attempt:saved,material:{text:'# First hint\n\nWrite the count as a sum of indicators.'}}});
    }
  });
  await page.goto('/practice/reader-attempt');
  await expect(page.getByRole('textbox',{name:'Черновик решения'})).toHaveText(restoredAttempt.draft);
  await page.getByRole('button',{name:'Подсказка 1',exact:true}).click();
  await expect(page.getByRole('heading',{name:'First hint',exact:true})).toBeVisible();
  await expect(page).toHaveURL(/material=h1/);
  const before={helpCommands,patches};
  await page.reload();
  await expect(page.getByRole('heading',{name:'First hint',exact:true})).toBeVisible();
  expect({helpCommands,patches}).toEqual(before);
  expect(helpCommands).toBe(1);
});

test('восстановление адреса не заменяет серверный черновик аварийной копией без выбора владельца', async ({page}) => {
  await page.evaluate(()=>localStorage.setItem('crucible-emergency-reader-attempt',JSON.stringify({draft:'Unconfirmed local solution.',revision:4})));
  await page.goto('/practice/reader-attempt');
  await expect(page.getByRole('textbox',{name:'Черновик решения'})).toHaveText(restoredAttempt.draft);
  await expect(page.getByText('Есть локальный черновик, который отличается от серверного.',{exact:false})).toBeVisible();
  await expect(page.getByRole('button',{name:'Восстановить в редактор',exact:true})).toBeVisible();
  await page.reload();
  await expect(page.getByRole('textbox',{name:'Черновик решения'})).toHaveText(restoredAttempt.draft);
  await expect(page.getByRole('button',{name:'Восстановить в редактор',exact:true})).toBeVisible();
});
