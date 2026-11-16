// Только просмотр основного профиля: синтетические попытки/XP не создаются.
import {chromium} from '../apps/web/node_modules/playwright-core/index.mjs';
import {readFileSync,mkdirSync} from 'node:fs';
const browser=await chromium.launch({headless:true});
try{
 const page=await browser.newPage({viewport:{width:1280,height:800}});await page.goto('http://127.0.0.1:28080');await page.getByLabel('Пароль владельца').fill(readFileSync('.secrets/owner-password','utf8'));await page.getByRole('button',{name:'Войти',exact:true}).click();await page.locator('.character-dashboard canvas').waitFor();await page.waitForFunction(()=>document.querySelector('.character-dashboard figcaption')?.textContent==='Подтверждённый образ');
 mkdirSync('.private/evidence/crucible-v3/main',{recursive:true});await page.screenshot({path:'.private/evidence/crucible-v3/main/today-1280.png'});await page.locator('.sidebar nav').getByRole('button',{name:'Персонаж',exact:true}).click();await page.waitForFunction(()=>document.querySelector('.character-portrait figcaption')?.textContent.includes('Подтверждённый образ'));await page.screenshot({path:'.private/evidence/crucible-v3/main/character-initial.png'});console.log('Основной профиль: Today и initial outfit сохранены; попытки не создавались.');
}finally{await browser.close();}
