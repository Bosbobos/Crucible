import {useEffect,useMemo,useState} from 'react';
import {CharacterScene,slotLabels} from './CharacterScene';
import {ChoiceButtons} from './Choice';
type Obj=Record<string,any>;
export function PaperDollLab({items}:{items:Obj[]}){
 const [manifest,setManifest]=useState<Obj|null>(null),[width,setWidth]=useState('360'),[background,setBackground]=useState('#FFFFFF'),[slot,setSlot]=useState('chest'),[overlay,setOverlay]=useState(false),[ornament,setOrnament]=useState(false);
 const [slots,setSlots]=useState<Obj>(Object.fromEntries(Object.keys(slotLabels).map(s=>[s,['chest','shoulders','bracers','legs'].includes(s)?'armor-0-'+s:null])));
 useEffect(()=>{fetch('/character/manifest.json',{cache:'no-cache'}).then(r=>r.json()).then(setManifest);},[]);
 const candidate=useMemo(()=>{if(!manifest)return undefined;const m=structuredClone(manifest);m.base.status='runtime_ready';for(const a of Object.values<Obj>(m.assets))for(const p of Object.values<Obj>(a.parts||{}))p.status='runtime_ready';
  if(ornament)m.assets['ORN-01']={parts:{main:{status:'runtime_ready',rig_id:m.rig_id,path:'/character/qa-fixtures/ornament.svg',hide_base_path:null}}};return m;
 },[manifest,ornament]);
 const currentItem=items.find(i=>i.id===slots[slot]),part=manifest?.assets[currentItem?.asset_id]?.parts[currentItem?.render_part];
 return <section className="paper-doll-lab"><h1>Paper-doll lab</h1><p>Только development · проверка кандидатов, без записи loadout и выдачи предметов.</p><p>{manifest?.rig_id} · {manifest?.manifest_version}</p>
  <div className="lab-toolbar"><ChoiceButtons label="Ширина сцены" value={width} onChange={setWidth} options={['240','360','480'].map(value=>({value,label:value+' px'}))}/><ChoiceButtons label="Фон QA" value={background} onChange={setBackground} options={['#FFFFFF','#252B31','#00BCD4'].map(value=>({value,label:value}))}/><label><input type="checkbox" checked={ornament} onChange={e=>{setOrnament(e.target.checked);setSlots({...slots,back_ornament:e.target.checked?'ornament-1':null});}}/>Тестовый SVG орнамента · не финальный арт</label><label><input type="checkbox" checked={overlay} onChange={e=>setOverlay(e.target.checked)}/>Показать hide-base выбранной части</label></div>
  <div className="lab-scene" style={{width:Number(width),background}}>{candidate&&<CharacterScene slots={slots} items={items} manifestOverride={candidate} preview/>}{overlay&&part?.hide_base_path&&<img className="mask-overlay" src={part.hide_base_path} alt="Hide-base mask"/>}</div>
  <button onClick={()=>{const canvas=document.querySelector<HTMLCanvasElement>('.lab-scene canvas');if(!canvas)return;const link=document.createElement('a');link.download='paper-doll-qa.png';link.href=canvas.toDataURL('image/png');link.click();}}>Экспорт прозрачного PNG</button>
  <ChoiceButtons label="Проверяемый слот" value={slot} onChange={setSlot} options={Object.entries(slotLabels).map(([value,label])=>({value,label}))}/><div className="button-row"><button onClick={()=>setSlots({...slots,[slot]:null})}>Без предмета</button>{items.filter(i=>i.slot===slot).map(i=><button key={i.id} aria-pressed={slots[slot]===i.id} onClick={()=>setSlots({...slots,[slot]:i.id})}>{i.name}</button>)}</div>
 </section>;
}
