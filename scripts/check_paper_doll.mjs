// Проверка настоящего compositor в локальном dev server; никаких equip/grant команд.
import {chromium} from '../apps/web/node_modules/playwright-core/index.mjs';
import {readFileSync,mkdirSync,writeFileSync} from 'node:fs';
import assert from 'node:assert/strict';
const output='.private/evidence/crucible-v3/lab';mkdirSync(output,{recursive:true});
const browser=await chromium.launch({headless:true});
try {
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:5174/#paper-doll-lab');
 await page.getByLabel('Пароль владельца').fill(readFileSync('.secrets/character-test/owner-password','utf8'));
 await page.getByRole('button',{name:'Войти',exact:true}).click();
 await page.getByRole('heading',{name:'Paper-doll lab',exact:true}).waitFor();
 const initialized=await page.evaluate(async()=>{
  const {composeCharacter}=await import('/src/CharacterScene.tsx');
  const manifest=await(await fetch('/character/manifest.json',{cache:'no-cache'})).json();
  const catalog=await(await fetch('/api/character/v1/catalog')).json();
  const m=structuredClone(manifest);
  const canvas=document.createElement('canvas');canvas.id='qa-canvas';canvas.style.width='360px';canvas.style.height='540px';
  document.querySelector('.lab-scene').replaceChildren(canvas);
  const none=Object.fromEntries(catalog.slots.map(s=>[s,null]));
  const baseline=await composeCharacter(canvas,m,none,catalog.items,()=>true);
  const original=canvas.getContext('2d').getImageData(0,0,1024,1536).data;
  async function bytes(path){const img=new Image();img.src=path;await img.decode();const tmp=document.createElement('canvas');tmp.width=1024;tmp.height=1536;const c=tmp.getContext('2d');c.drawImage(img,0,0);return c.getImageData(0,0,1024,1536).data;}
  const head=await bytes(m.base.region_masks.head_face_horns),tail=await bytes(m.base.region_masks.tail_back),hand=await bytes(m.base.region_masks.hand_right_neutral);
  window.qa={manifest:m,items:catalog.items,none,canvas,composeCharacter,original,head,tail,hand};
  window.drawQA=async(slots,manifestOverride)=>{
   const start=performance.now(),result=await composeCharacter(canvas,manifestOverride||m,{...none,...slots},catalog.items,()=>true);
   const actual=canvas.getContext('2d').getImageData(0,0,1024,1536).data;
   let headChanges=0,tailChanges=0,handChanges=0;
   for(let i=0;i<1024*1536;i++){
    const different=[0,1,2,3].some(k=>actual[i*4+k]!==original[i*4+k]);
    if(different&&head[i*4]>250&&original[i*4+3]===255)headChanges++;
    if(different&&tail[i*4]>250&&original[i*4+3]===255)tailChanges++;
    if(different&&hand[i*4]>250&&original[i*4+3]===255)handChanges++;
   }
   return {...result,ms:performance.now()-start,headChanges,tailChanges,handChanges};
  };
  return {manifest_version:m.manifest_version,baseline};
 });
 const cases=[];
 for(let tier=0;tier<5;tier++)for(const slot of ['chest','legs','shoulders','bracers'])cases.push({id:`ARM-0${tier}-${slot}`,slots:{[slot]:`armor-${tier}-${slot}`}});
 for(let tier=0;tier<5;tier++)cases.push({id:`ARM-0${tier}-full`,slots:Object.fromEntries(['chest','legs','shoulders','bracers'].map(s=>[s,`armor-${tier}-${s}`]))});
 const mixed=JSON.parse(readFileSync('Task/Crucible_Implementation_Pack_v3/data/visual_test_cases.json')).mixed_outfits;cases.push(...mixed);
 const results=[];
 for(const scenario of cases){
  const result=await page.evaluate(s=>window.drawQA(s),scenario.slots);
  assert.equal(result.missing.length,0,scenario.id);assert.equal(result.headChanges,0,scenario.id+' head');assert.equal(result.tailChanges,0,scenario.id+' tail');assert.equal(result.handChanges,0,scenario.id+' hand');
  if(scenario.id==='mixed-01'||scenario.id==='ARM-00-full'){
   const encoded=await page.locator('#qa-canvas').evaluate(c=>c.toDataURL('image/png'));writeFileSync(output+'/'+scenario.id+'.png',Buffer.from(encoded.split(',')[1],'base64'));
  }
  results.push({id:scenario.id,...result});
 }
 const restore=await page.evaluate(()=>window.drawQA({}));assert.equal(restore.headChanges+restore.tailChanges+restore.handChanges,0);
 // A failed paint must omit its hide mask and restore the complete neutral BASE.
 const failed=await page.evaluate(async()=>{const q=window.qa,m=structuredClone(q.manifest);m.assets['ARM-00'].parts.legs.path='/character/intentionally-missing.webp';const result=await window.drawQA({legs:'armor-0-legs'},m);const actual=q.canvas.getContext('2d').getImageData(0,0,1024,1536).data;return {...result,restored:actual.every((v,i)=>v===q.original[i])};});
 assert.equal(failed.restored,true);assert.deepEqual(failed.missing,['armor-0-legs']);
 // Missing grip dependency omits the entire weapon, including its hand hide.
 const missingGrip=await page.evaluate(async()=>{const q=window.qa,m=structuredClone(q.manifest);m.assets['SWD-03'].parts.main.status='runtime_ready';m.assets['SWD-03'].parts.main.dependencies=[{pass:'grip_front',path:'/character/intentionally-missing-grip.webp'}];const result=await window.drawQA({sword:'sword-3'},m);const actual=q.canvas.getContext('2d').getImageData(0,0,1024,1536).data;return {...result,restored:actual.every((v,i)=>v===q.original[i])};});
 assert.equal(missingGrip.restored,true);assert.deepEqual(missingGrip.missing,['sword-3']);
 // Latest generation wins, regardless of an old request finishing afterwards.
 const stale=await page.evaluate(async()=>{const q=window.qa;await window.drawQA({chest:'armor-0-chest'});const before=q.canvas.toDataURL();const result=await q.composeCharacter(q.canvas,q.manifest,{...q.none,legs:'armor-4-legs'},q.items,()=>false);return {cancelled:result===null,unchanged:q.canvas.toDataURL()===before};});
 assert.ok(stale.cancelled&&stale.unchanged);
 const ornament=await page.evaluate(async()=>{const m=structuredClone(window.qa.manifest);m.assets['ORN-01']={parts:{main:{status:'runtime_ready',rig_id:m.rig_id,path:'/character/qa-fixtures/ornament.svg',hide_base_path:null}}};return window.drawQA({back_ornament:'ornament-1'},m);});
 assert.equal(ornament.headChanges,0);assert.equal(ornament.tailChanges,0);assert.equal(ornament.handChanges,0);assert.deepEqual(ornament.rendered,['ornament-1']);
 for(const width of [240,360,480])for(const background of ['#FFFFFF','#252B31','#00BCD4']){
  await page.evaluate(async({width,background})=>{await window.drawQA({chest:'armor-2-chest',shoulders:'armor-4-shoulders',bracers:'armor-0-bracers',legs:'armor-1-legs'});const c=window.qa.canvas;c.style.width=width+'px';c.style.height=width*1.5+'px';const parent=c.parentElement;parent.style.width=width+'px';parent.style.background=background;},{width,background});
  await page.locator('.lab-scene').screenshot({path:output+`/mixed-${width}-${background.slice(1)}.png`});
 }
 assert.deepEqual(errors,[]);
 const report={status:'passed',...initialized,cases:results,failed_paint:failed,missing_grip:missingGrip,stale_generation:stale,synthetic_ornament:ornament,errors};
 writeFileSync(output+'/renderer-report.json',JSON.stringify(report,null,2));console.log(JSON.stringify({status:'passed',cases:results.length,backgrounds:3,widths:3,failed_paint:'restored BASE',stale_generation:'ignored',synthetic_ornament:'passed',evidence:output+'/renderer-report.json'}));
} finally {await browser.close();}
