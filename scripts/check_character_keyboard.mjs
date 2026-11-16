// Учебный маршрут только Tab/Enter/keyboard; отдельный синтетический профиль.
import {chromium} from '../apps/web/node_modules/playwright-core/index.mjs';
import {readFileSync,writeFileSync} from 'node:fs';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true});
try{
 const page=await browser.newPage({viewport:{width:1280,height:800},reducedMotion:'reduce'});
 async function tabTo(kind,name){for(let n=0;n<180;n++){const found=await page.evaluate(({kind,name})=>{const e=document.activeElement;if(!e)return false;return (kind==='textbox'?(e.getAttribute('role')==='textbox'||e.tagName==='INPUT'):e.tagName==='BUTTON')&&new RegExp(name).test(e.getAttribute('aria-label')||Array.from(e.labels||[]).map(x=>x.textContent).join(' ')||e.textContent||'');},{kind,name});if(found)return;await page.keyboard.press('Tab');}throw new Error('Keyboard focus did not reach '+name);}
 await page.goto('http://127.0.0.1:28083');await page.getByLabel('Пароль владельца').waitFor();await tabTo('textbox','Пароль владельца');await page.keyboard.insertText(readFileSync('.secrets/character-test/owner-password','utf8'));await tabTo('button','^Войти$');await page.keyboard.press('Enter');await page.getByRole('heading',{name:'Сегодня',exact:true}).waitFor();
 await tabTo('button','^(Продолжить задачу|Начать занятие)');await page.keyboard.press('Enter');await page.getByRole('textbox',{name:'Черновик решения'}).waitFor();await tabTo('textbox','Черновик решения');await page.keyboard.press(process.platform==='darwin'?'Meta+a':'Control+a');const draft='Keyboard route: $x^2+y^2=1$';await page.keyboard.insertText(draft);await page.keyboard.press(process.platform==='darwin'?'Meta+s':'Control+s');
 for(let n=0;n<40;n++){const a=(await(await page.request.get('http://127.0.0.1:28083/api/v1/practice/current')).json()).attempt;if(a?.draft===draft)break;if(n===39)throw new Error('Keyboard save unconfirmed');await page.waitForTimeout(100);}
 await tabTo('button','^Сегодня$');await page.keyboard.press('Enter');await page.getByRole('heading',{name:'Сегодня',exact:true}).waitFor();await tabTo('button','^Продолжить задачу');await page.keyboard.press('Enter');await page.getByRole('textbox',{name:'Черновик решения'}).waitFor();assert.equal((await page.locator('.cm-content .cm-line').allTextContents()).join('\n'),draft);
 writeFileSync('.private/evidence/crucible-v3/keyboard.json',JSON.stringify({status:'passed',project:'crucible-character-test',route:'Tab → owner login → Today CTA → editor → keyboard save → Today → resume',pointer_actions:0,reduced_motion:true},null,2));console.log('passed: keyboard-only login → task → save → Today → resume; no pointer actions');
}finally{await browser.close();}
