import {test, expect} from '@playwright/test';
import {readFileSync, mkdirSync, writeFileSync} from 'node:fs';

let sessionCookies: any[] | undefined;
async function login(page: any) {
  if (sessionCookies) await page.context().addCookies(sessionCookies);
  await page.goto('/');
  if (!sessionCookies) {
    await page.getByLabel('Пароль владельца').fill(readFileSync((process.env.CRUCIBLE_TEST_SECRETS||'../../.secrets')+'/owner-password', 'utf8'));
    const [response] = await Promise.all([
      page.waitForResponse((response: any) => response.url().endsWith('/api/v1/practice/auth/login')),
      page.getByRole('button', {name: 'Войти', exact: true}).click(),
    ]);
    if (!response.ok()) {
      await page.getByLabel('Пароль владельца').fill('');
      throw new Error('Owner login returned HTTP ' + response.status());
    }
    // Reuse the authenticated session in this worker; repeated UX checks need no new logins.
    sessionCookies = await page.context().cookies();
  }
  await expect(page.getByRole('heading', {name: 'Сегодня', exact: true})).toBeVisible();
  await expect(page.locator('.task-list article')).not.toHaveCount(0);
  // Tests own synthetic attempts; leave the profile ready even after a previous failed run.
  const current = (await (await page.request.get('/api/v1/practice/current')).json()).attempt;
  if (current && ['running', 'paused'].includes(current.state)) {
    const session = await (await page.request.get('/api/v1/practice/auth/session')).json();
    const response = await page.request.patch('/api/v1/practice/attempts/' + current.id, {
      headers: {'X-CSRF-Token': session.csrf, 'Origin': process.env.CRUCIBLE_TEST_ORIGIN||'http://localhost:18080'},
      data: {command_id: crypto.randomUUID(), expected_revision: current.revision, state: 'abandoned'},
    });
    expect(response.ok()).toBeTruthy();
    await page.reload();
  }
  await expect(page.locator('.task-list article')).not.toHaveCount(0);
  await expect(page.locator('.sync-state')).toContainText(/Учтены факты до|Повторения пересчитываются/);
}
async function start(page: any, id: string) {
  await page.getByRole('button', {name: 'Материалы', exact: true}).click();
  await page.locator('article').filter({hasText: id}).getByRole('button').click();
  await expect(page.getByRole('textbox', {name: 'Черновик решения'})).toBeVisible();
}
async function savedDraft(page: any, draft: string) {
  await expect.poll(async () => (await (await page.request.get('/api/v1/practice/current')).json()).attempt?.draft).toBe(draft);
}
async function noOverflow(page: any) {
  await expect.poll(()=>page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
}

async function editorText(page:any) {return (await page.locator('.cm-content .cm-line').allTextContents()).join('\n');}
async function chapter(page:any,name:string) {
  const toggle=page.getByRole('button',{name:'Содержание',exact:true});
  if(await toggle.isVisible()&&await toggle.getAttribute('aria-expanded')==='false')await toggle.click();
  await page.getByRole('navigation',{name:'Разделы теории'}).getByRole('button',{name,exact:true}).click();
}
async function assisted(page:any,parts:number) {
  await expect(page.locator('.completion > .choice-buttons [role=radiogroup]')).toHaveCount(parts);
  for(const radio of await page.locator('.completion').getByRole('radio',{name:'С помощью',exact:true}).all())await expect(radio).toHaveAttribute('aria-checked','true');
  for(const radio of await page.locator('.completion').getByRole('radio',{name:'Самостоятельно',exact:true}).all())await expect(radio).toBeDisabled();
}

test('saved workspace, readable theory, side-by-side editing, lab and completion', async ({page}) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  mkdirSync('../../.private/evidence/screenshots', {recursive: true});
  await login(page);
  await expect(page).toHaveTitle("Crucible · Математика");
  await expect(page.locator('body')).not.toContainText(/skoltech|сколтех/i);
  await page.screenshot({path: '../../.private/evidence/screenshots/today.png', fullPage: true});
  await start(page, 'P-004');
  await expect(page.locator('.completion')).not.toBeVisible();
  const draft = 'Write $X=\\sum_{k=1}^n I_k$.\n\nEach indicator marks a fixed point.';
  await page.getByRole('textbox', {name: 'Черновик решения'}).fill(draft);
  await page.getByRole('textbox', {name: 'Черновик решения'}).press(process.platform === 'darwin' ? 'Meta+s' : 'Control+s');
  await savedDraft(page, draft);
  await expect(page.getByText('Ответ на предыдущую команду не получен.', {exact:false})).not.toBeVisible();
  await page.getByRole('tab', {name: 'Предпросмотр', exact: true}).click();
  await expect(page.locator('.draft-preview .katex')).not.toHaveCount(0);
  await page.getByRole('tab', {name: 'Редактор', exact: true}).click();
  await page.screenshot({path: '../../.private/evidence/screenshots/workspace.png', fullPage: true});
  await noOverflow(page);

  await page.locator('.resource-links').getByRole('button', {name: 'Конспект темы', exact: false}).click();
  await expect(page.getByRole('heading', {name: 'Матожидание, дисперсия и индикаторы'})).toBeVisible();
  await expect(page.getByRole('textbox', {name: 'Черновик решения'})).not.toBeVisible();
  expect(await page.locator('.reading-paper').evaluate(element => element.getBoundingClientRect().width)).toBeGreaterThan(650);
  await chapter(page,'Нужно уметь');
  const before = await page.locator('.reader-chapter:not([hidden]) > .markdown').evaluate(element => parseFloat(getComputedStyle(element).fontSize));
  await page.getByRole('button', {name: 'Увеличить текст'}).click();
  expect(await page.locator('.reader-chapter:not([hidden]) > .markdown').evaluate(element => parseFloat(getComputedStyle(element).fontSize))).toBeGreaterThan(before);
  const firstExercise=page.getByRole('region',{name:'pre-die',exact:true});
  await expect(firstExercise.locator('.exercise-answer')).not.toBeVisible();
  await firstExercise.getByLabel('Ответ',{exact:true}).fill('7/2');
  await page.waitForTimeout(1200); // A timer update must preserve a learner's unfinished answer.
  await expect(firstExercise.getByLabel('Ответ',{exact:true})).toHaveValue('7/2');
  await firstExercise.getByRole('button',{name:'Проверить',exact:true}).click();
  await expect(firstExercise.getByRole('status')).toContainText('Верно');
  await page.evaluate(()=>window.scrollTo(0,0));
  await page.screenshot({path: '../../.private/evidence/screenshots/theory.png', fullPage: false});
  await page.getByRole('navigation', {name: 'Разделы теории'}).getByRole('button', {name: 'Приём 4 · Дисперсия суммы: диагональ + пары'}).click();
  await expect(page.locator('#theory-приём-4-дисперсия-суммы-диагональ-пары')).toBeInViewport();
  await page.getByRole('button', {name: 'Черновик рядом', exact: true}).click();
  await expect.poll(()=>editorText(page)).toBe(draft);
  expect(await page.locator('.reading-paper').evaluate(element => element.getBoundingClientRect().width)).toBeGreaterThan(850);
  await expect(page.getByRole('button', {name: 'Содержание', exact: true})).toHaveAttribute('aria-expanded', 'false');
  await page.evaluate(()=>window.scrollTo(0,0));
  await page.screenshot({path:'../../.private/evidence/screenshots/theory-with-draft.png',fullPage:false});
  const revised = draft + '\n\nUse joint probabilities for the variance.';
  await page.getByRole('textbox', {name: 'Черновик решения'}).fill(revised);
  await savedDraft(page, revised);
  await noOverflow(page);
  await page.getByRole('button', {name: 'Скрыть черновик', exact: true}).click();
  await page.getByRole('tab', {name: 'Лаборатория', exact: true}).click();
  await page.getByLabel('Мой прогноз E X', {exact:true}).fill('2.25');
  await page.getByRole('button', {name: 'Провести 20 000 опытов', exact:true}).click();
  await expect(page.getByRole('img', {name: /Число наблюдений/})).toBeVisible();
  await expect(page.locator('.lab-results')).toContainText('2.688');
  await page.screenshot({path: '../../.private/evidence/screenshots/laboratory.png', fullPage: true});
  await page.getByRole('tab', {name: 'Конспект', exact: true}).click();
  await page.getByRole('button', {name: 'Вернуться к задаче', exact: false}).first().click();
  await expect.poll(()=>editorText(page)).toBe(revised);

  // An unknown network outcome must remain explicit and recover using the same command.
  await page.route('**/api/v1/practice/attempts/*', async route => {
    if(route.request().method() === 'PATCH') await route.abort('failed');
    else await route.continue();
  });
  const interrupted = revised + '\nPending network save.';
  await page.getByRole('textbox', {name: 'Черновик решения'}).fill(interrupted);
  await expect(page.getByRole('button', {name: 'Проверить повтором прежней команды', exact:true})).toBeVisible();
  await expect(page.locator('.save-state')).toContainText('Сохранение не подтверждено');
  await page.unroute('**/api/v1/practice/attempts/*');
  await page.getByRole('button', {name: 'Проверить повтором прежней команды', exact:true}).click();
  await savedDraft(page, interrupted);
  await expect(page.locator('.save-state')).toContainText('Сохранено сервером');

  await page.getByRole('textbox', {name: 'Черновик решения'}).fill(revised + '<img src=x onerror="window.xss=1">');
  await savedDraft(page, revised + '<img src=x onerror="window.xss=1">');
  await page.getByRole('tab', {name: 'Предпросмотр', exact: true}).click();
  await expect(page.locator('.draft img')).toHaveCount(0);
  await page.getByRole('tab', {name: 'Редактор', exact: true}).click();
  await page.getByRole('textbox', {name: 'Черновик решения'}).fill(revised);
  await page.getByRole('button', {name: 'К результату', exact: false}).click();
  await assisted(page,2);
  await page.getByRole('button', {name: 'Завершить попытку', exact: true}).click();
  await expect(page.getByRole('heading', {name: 'Попытка сохранена', exact: true})).toBeVisible();
  await page.getByRole('textbox', {name: 'Вопрос по попытке'}).fill('Why are joint probabilities needed for the variance?');
  await page.getByRole('button', {name: 'Сохранить вопрос', exact: true}).click();
  await expect(page.locator('.question').filter({hasText: 'Why are joint probabilities'})).toBeVisible();
  expect(errors).toEqual([]);
});

test('chapter reading, preserved answers and responsive layout', async ({page}) => {
  await login(page);
  await page.getByRole('button',{name:'Материалы',exact:true}).click();
  await page.locator('.topic-grid .card').filter({hasText:'Матожидание, дисперсия и индикаторы'}).getByRole('button').click();
  await expect(page.getByRole('heading',{name:'Введение',exact:true})).toBeVisible();
  await page.getByRole('navigation',{name:'Переходы по конспекту'}).getByRole('button',{name:/Далее/}).click();
  await expect(page.getByRole('heading',{name:'Нужно уметь',exact:true})).toBeVisible();
  const exercise=page.getByRole('region',{name:'pre-die',exact:true});
  await exercise.getByLabel('Ответ',{exact:true}).fill('7/2');
  await exercise.getByRole('button',{name:'Проверить',exact:true}).click();
  await chapter(page,'Приём 1 · Линейность работает всегда');
  await expect(page.getByRole('region',{name:'pre-die',exact:true})).not.toBeVisible();
  await chapter(page,'Нужно уметь');
  await expect(exercise.getByRole('status')).toContainText('Верно');
  const prose=page.locator('.reader-chapter:not([hidden]) > .markdown > p').first();
  const measurements=[];
  for(const width of [1920,1440,1280,1100,980,768,390]) {
    await page.setViewportSize({width,height:1000});
    await noOverflow(page);
    await expect(page.locator('select')).toHaveCount(0);
    measurements.push({viewport:width,sheet:await page.locator('.reading-paper').evaluate(el=>el.getBoundingClientRect().width),prose:await prose.evaluate(el=>el.getBoundingClientRect().width)});
    if(width>=1280)expect(await prose.evaluate(el=>el.getBoundingClientRect().width)).toBeGreaterThan(740);
    if(width<=1100){await chapter(page,'Задача-мотиватор');await expect(page.getByRole('button',{name:'Содержание',exact:true})).toHaveAttribute('aria-expanded','false');await chapter(page,'Нужно уметь');}
  }
  writeFileSync('../../.private/evidence/reading-chapters-width.json',JSON.stringify(measurements,null,2));
  await page.setViewportSize({width:1440,height:1000});
  await page.evaluate(()=>window.scrollTo(0,0));
  await page.screenshot({path:'../../.private/evidence/screenshots/reading-chapters.png',fullPage:false});
});

test('mobile workspace and reading, two-part assisted outcome and safe solution disclosure', async ({page}) => {
  await page.setViewportSize({width: 390, height: 844});
  await login(page);
  await noOverflow(page);
  await page.screenshot({path: '../../.private/evidence/screenshots/mobile.png', fullPage: true});
  await start(page, 'P-004');
  const draft = 'Use one indicator for each fixed point.';
  await page.getByRole('textbox', {name: 'Черновик решения'}).fill(draft);
  await savedDraft(page, draft);
  await noOverflow(page);
  expect(await page.locator('.notebook').evaluate(element => element.getBoundingClientRect().top)).toBeLessThan(await page.locator('.study-resources').evaluate(element => element.getBoundingClientRect().top));
  await page.screenshot({path: '../../.private/evidence/screenshots/mobile-workspace.png', fullPage: true});
  await page.getByText('Разбор решения', {exact: true}).click();
  await page.getByRole('button', {name: 'Открыть решение', exact: true}).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await expect(page.locator('.help-badge')).not.toBeVisible();
  await page.locator('.resource-links').getByRole('button', {name: 'Конспект темы', exact: false}).click();
  await expect(page.getByRole('region', {name: 'Чтение материала'})).toBeVisible();
  await noOverflow(page);
  await page.screenshot({path: '../../.private/evidence/screenshots/mobile-theory.png', fullPage: false});
  await page.getByRole('tab', {name: 'Лаборатория', exact: true}).click();
  await page.getByLabel('Мой прогноз E X', {exact:true}).fill('2.25');
  await page.getByRole('button', {name: 'Провести 20 000 опытов', exact: true}).click();
  await expect(page.getByRole('img', {name: /Число наблюдений/})).toBeVisible();
  await page.getByRole('button', {name: 'Вернуться к задаче', exact: false}).first().click();
  await expect.poll(()=>editorText(page)).toBe(draft);
  await page.getByRole('button', {name: 'К результату', exact: false}).click();
  await assisted(page,2);
  await page.getByRole('button', {name: 'Завершить попытку', exact: true}).click();
  await expect(page.getByRole('heading', {name: 'Попытка сохранена', exact: true})).toBeVisible();
  await noOverflow(page);
});

test('complete vault catalog, missing theory, source hints and preserved Obsidian callouts', async ({page}) => {
  await login(page);
  await page.getByRole('button',{name:'Материалы',exact:true}).click();
  await expect(page.locator('.task-list article')).toHaveCount(57);
  await expect(page.locator('.topic-grid .card')).toHaveCount(4);
  await page.screenshot({path:'../../.private/evidence/screenshots/materials.png',fullPage:false});
  await page.getByLabel('Поиск по задачам').fill('P-022');
  await expect(page.locator('.task-list article')).toHaveCount(1);
  await page.locator('.task-list article').getByRole('button').click();
  await expect(page.getByText('Для этого типа в исходном vault нет конспекта.',{exact:false})).toBeVisible();
  await expect(page.locator('.resource-links').getByRole('button',{name:'Конспект темы',exact:false})).toHaveCount(0);
  const response=await page.request.get('/api/v1/practice/current');
  const attempt=(await response.json()).attempt;
  expect(attempt.problem.provenance.kind).toBe('obsidian_vault');
  expect(attempt.problem.primary_skill_id).toBe('LA-02');
  expect(attempt.problem.materials.core).toBe(false);
  expect(attempt.problem).not.toHaveProperty('hints');
  await page.locator('.hint-buttons button').nth(2).click();
  await expect(page.locator('.reading-paper')).toContainText('Axler');
  await page.getByRole('button',{name:'Вернуться к задаче',exact:false}).first().click();
  await page.getByRole('button',{name:'К результату',exact:false}).click();
  await assisted(page,3);
  await page.getByRole('button',{name:'Завершить попытку',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Попытка сохранена',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Материалы',exact:true}).click();
  await page.locator('.topic-grid .card').filter({hasText:'Уравнения первого порядка'}).getByRole('button').click();
  await expect(page.getByRole('heading',{name:'Уравнения первого порядка',exact:true})).toBeVisible();
  await chapter(page,'Как узнать тип');
  await expect(page.locator('.source-flow')).toBeVisible();
  await chapter(page,'Самопроверка');
  await page.locator('.source-callout.quiz > summary').click();
  await expect(page.locator('.source-callout.quiz')).toHaveAttribute('open','');
  await expect(page.locator('.source-callout.success')).not.toHaveAttribute('open','');
  await page.locator('.source-callout.success > summary').click();
  await expect(page.locator('.source-callout.success')).toHaveAttribute('open','');
  await page.waitForTimeout(1200); // The app's one-second clock must not close nested source callouts.
  await expect(page.locator('.source-callout.quiz')).toHaveAttribute('open','');
  await expect(page.locator('.source-callout.success')).toHaveAttribute('open','');
  await expect(page.locator('body')).not.toContainText('await dv.view');
  await page.evaluate(()=>window.scrollTo(0,0));
  await page.screenshot({path:'../../.private/evidence/screenshots/source-ode.png',fullPage:false});
  await noOverflow(page);
});

test('live equation preview, paired symbols, undo and source tables',async({page})=>{
  await login(page);
  await expect(page.locator('.progress-card')).not.toContainText('$I+uv');
  await expect(page.locator('.skill strong').filter({hasText:'Матрицы ранга'}).locator('.katex')).not.toHaveCount(0);
  await start(page,'P-004');
  const editor=page.getByRole('textbox',{name:'Черновик решения'});
  await editor.fill('');await editor.press('$');
  await expect.poll(()=>editorText(page)).toBe('$$');
  await editor.pressSequentially('x^2');
  await expect.poll(()=>editorText(page)).toBe('$x^2$');
  await expect(page.getByRole('region',{name:'Предпросмотр формулы'}).locator('.katex')).toBeVisible();
  await editor.press('$');
  await expect.poll(()=>editorText(page)).toBe('$x^2$');
  await editor.press('End');await editor.press(' ');await editor.press('*');await editor.press('*');
  await expect.poll(()=>editorText(page)).toBe('$x^2$ ****');
  await editor.pressSequentially('bold');await editor.press('*');await editor.press('*');
  await expect.poll(()=>editorText(page)).toBe('$x^2$ **bold**');
  await editor.press('End');await editor.press(' ');await editor.press('(');await editor.press('Backspace');
  await expect.poll(()=>editorText(page)).toBe('$x^2$ **bold** ');
  await editor.press(process.platform==='darwin'?'Meta+z':'Control+z');
  await expect.poll(()=>editorText(page)).toContain('()');
  await editor.fill('');await editor.press('$');await editor.press('$');
  await expect.poll(()=>editorText(page)).toBe('$$$$');
  await editor.pressSequentially('x_');await editor.press('{');await expect.poll(()=>editorText(page)).toBe('$$x_{}$$');await editor.pressSequentially('n');await editor.press('}');
  await expect.poll(()=>editorText(page)).toBe('$$x_{n}$$');
  await expect(page.locator('.formula-render .katex')).toBeVisible();
  await page.screenshot({path:'../../.private/evidence/screenshots/live-equation.png',fullPage:false});
  await savedDraft(page,'$$x_{n}$$');
  for(const [open,close] of [['[',']'],['{','}'],['`','`'],['_','_'],['"','"']]) {
    await editor.fill('');await editor.press(open);
    await expect.poll(()=>editorText(page)).toBe(open+close);
    await editor.pressSequentially('a');await editor.press(close);
    await expect.poll(()=>editorText(page)).toBe(open+'a'+close);
  }
  await editor.fill('xyz');await editor.press(process.platform==='darwin'?'Meta+a':'Control+a');await editor.press('$');
  await expect.poll(()=>editorText(page)).toBe('$xyz$');
  await savedDraft(page,'$xyz$');
  await page.getByRole('button',{name:'Материалы',exact:true}).click();
  const section=page.locator('.section-choices').getByRole('radio',{name:'Все разделы',exact:true});
  await section.focus();await section.press('ArrowRight');
  await expect(section).toHaveAttribute('aria-checked','false');
  await page.locator('.section-choices').getByRole('radio',{name:'Вероятности',exact:true}).click();
  await expect(page.locator('.task-list article')).toHaveCount(25);
  await section.click();await expect(page.locator('.task-list article')).toHaveCount(57);
  await page.locator('.topic-grid .card').filter({hasText:'Карта приёмов'}).getByRole('button').click();
  await chapter(page,'Вероятность');
  const table=page.getByRole('table');
  await expect(table.getByRole('row')).toHaveCount(8);
  await expect(table.getByRole('columnheader')).toHaveCount(3);
  await expect(table.locator('.katex')).not.toHaveCount(0);
  await expect(table.getByRole('link',{name:'Байес',exact:true})).toHaveCount(3);
  await expect(page.locator('select')).toHaveCount(0);
  await page.screenshot({path:'../../.private/evidence/screenshots/source-table.png',fullPage:false});
  await page.setViewportSize({width:390,height:844});await noOverflow(page);
  await page.screenshot({path:'../../.private/evidence/screenshots/source-table-mobile.png',fullPage:false});
  await table.getByRole('link',{name:'Байес',exact:true}).first().click();
  await expect(page.getByRole('heading',{name:'Условная вероятность и формула Байеса',exact:true})).toBeVisible();
});
