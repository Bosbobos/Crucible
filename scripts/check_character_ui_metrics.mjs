// Реальные локальные замеры Chromium; это не production load test.
import {chromium} from '../apps/web/node_modules/playwright-core/index.mjs';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true});
try{
 const context=await browser.newContext({viewport:{width:1280,height:800},reducedMotion:'reduce'}),page=await context.newPage();
 await page.goto('http://127.0.0.1:28083');await page.getByLabel('Пароль владельца').fill(readFileSync('.secrets/character-test/owner-password','utf8'));await page.getByRole('button',{name:'Войти',exact:true}).click();await page.locator('.character-dashboard canvas').waitFor();await page.waitForFunction(()=>document.querySelector('.character-dashboard figcaption')?.textContent==='Подтверждённый образ');
 const resources=await page.evaluate(()=>performance.getEntriesByType('resource').map(r=>({path:new URL(r.name).pathname,encoded_body_bytes:r.encodedBodySize,transfer_bytes:r.transferSize,duration_ms:r.duration})));
 assert.ok(!resources.some(r=>r.path.includes('/references/')||r.path.endsWith('.png')&&!r.path.includes('/character/files/')));
 const summary=[];for(let i=0;i<20;i++){const t=performance.now();const response=await page.request.get('http://127.0.0.1:28083/api/character/v1/me/summary');assert.ok(response.ok());summary.push(performance.now()-t);}
 await page.locator('.sidebar nav').getByRole('button',{name:'Персонаж',exact:true}).click();await page.locator('.item-card').first().waitFor();await page.locator('.item-card').first().evaluate(el=>el.style.width='160px');await page.locator('.item-card').first().screenshot({path:'.private/evidence/crucible-v3/ui/item-160.png'});
 const wardrobeResources=await page.evaluate(()=>performance.getEntriesByType('resource').map(r=>({path:new URL(r.name).pathname,transfer_bytes:r.transferSize})));
 const contrast=await page.evaluate(()=>{
  const style=getComputedStyle(document.documentElement);const hex=n=>style.getPropertyValue(n).trim();
  const luminance=h=>{const rgb=h.replace('#','').match(/../g).map(x=>parseInt(x,16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);return rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722;};
  return [['--cr-ink','--cr-surface'],['--cr-muted','--cr-bg'],['--cr-gold-text','--cr-surface'],['--cr-surface','--cr-primary']].map(([a,b])=>{const x=luminance(hex(a)),y=luminance(hex(b));return {foreground:hex(a),background:hex(b),ratio:(Math.max(x,y)+.05)/(Math.min(x,y)+.05)};});
 });assert.ok(contrast.every(x=>x.ratio>=4.5));
 const motion=await page.getByRole('button',{name:'Обновить состояние',exact:true}).evaluate(el=>getComputedStyle(el).transitionDuration);assert.equal(motion,'0s');
 summary.sort((a,b)=>a-b);const report={environment:'local Docker Desktop + Chromium; one synthetic profile; cold browser cache',status:'passed',today_resources:resources,total_transfer_bytes:resources.reduce((n,r)=>n+r.transfer_bytes,0),character_transfer_bytes:resources.filter(r=>r.path.startsWith('/character/')).reduce((n,r)=>n+r.transfer_bytes,0),first_inventory_cumulative_transfer_bytes:wardrobeResources.reduce((n,r)=>n+r.transfer_bytes,0),inventory_scope:'first visible chest inventory after Today; same browser cache',summary_http_ms:{samples:20,p50:summary[10],p95:summary[18],max:summary[19]},contrast_pairs:contrast,reduced_motion_transition:motion};
 mkdirSync('.private/evidence/crucible-v3',{recursive:true});writeFileSync('.private/evidence/crucible-v3/ui-metrics.json',JSON.stringify(report,null,2));console.log(JSON.stringify({...report,today_resources:resources.length}));
}finally{await browser.close();}
