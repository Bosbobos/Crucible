import {useEffect,useRef,useState} from 'react';
import {CharacterScene,slotLabels} from './CharacterScene';
import {Emblem} from './Emblem';
import {ChoiceButtons} from './Choice';
type Obj=Record<string,any>;
type API=(path:string,method?:string,body?:Obj)=>Promise<any>;
const prefix='/api/character/v1/';
const artLabels:Record<string,string>={runtime_ready:'Изображение готово',missing:'Изображение готовится',reference_available:'Есть образец · слой готовится',processing:'Обработка изображения',qa_failed:'Изображение на доработке'};

export function useCharacter(logged:boolean,api:API){
 const [data,setData]=useState<Obj>({}),[status,setStatus]=useState('loading'),[message,setMessage]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const generation=useRef(0),notified=useRef(new Set<string>());
 async function refresh(full=false){
  const token=++generation.current;
  const paths=['me/summary','catalog','me/loadout','me/preferences',...(full?['me/inventory','me/path','me/collection','me/journal']:[])];
  const keys=['summary','catalog','loadout','preferences',...(full?['inventory','path','collection','journal']:[])];
  const results=await Promise.allSettled(paths.map(p=>api(prefix+p)));
  if(token!==generation.current)return;
  setData(previous=>({...previous,...Object.fromEntries(results.flatMap((r,i)=>r.status==='fulfilled'?[[keys[i],r.value]]:[]))}));
  setStatus(results[0].status==='fulfilled'?'current':'stale');
 }
 useEffect(()=>{if(logged)refresh();else{generation.current++;setData({});setStatus('loading');}return()=>{generation.current++;};},[logged]);
 async function mutate(path:string,method:string,body:Obj){
  // Separate receipt/retry channel: unavailable RPG must never block draft saving.
  if(localStorage.getItem('crucible-character-command'))throw new Error('Повторите неподтверждённую команду образа.');
  const request={path:prefix+path,method,body:{command_id:crypto.randomUUID(),...body}};
  localStorage.setItem('crucible-character-command',JSON.stringify(request));
  try{const result=await api(request.path,method,request.body);localStorage.removeItem('crucible-character-command');return result;}
  catch(e){const status=(e as any).status;if(status>=400&&status<500)localStorage.removeItem('crucible-character-command');throw e;}
 }
 async function run(work:()=>Promise<void>){setBusy(true);setError('');try{await work();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 async function retry(){await run(async()=>{const saved=localStorage.getItem('crucible-character-command');if(!saved)return;const request=JSON.parse(saved);try{await api(request.path,request.method,request.body);localStorage.removeItem('crucible-character-command');await refresh(true);}catch(e){if((e as any).status>=400&&(e as any).status<500)localStorage.removeItem('crucible-character-command');throw e;}});}
 async function wait(correlation:string){
  if(!correlation||notified.current.has(correlation))return;
  setMessage('Попытка сохранена. Обновляем путь персонажа…');
  for(const delay of [500,1000,2000,4000,8000]){
   await new Promise(resolve=>setTimeout(resolve,delay));
   try{const op=await api(prefix+'me/operations/'+correlation);if(op.status!=='pending'){
    notified.current.add(correlation);await refresh();setMessage(op.delta>0?'Путь обновлён · +'+op.delta+' XP':op.delta<0?'Путь уточнён · '+op.delta+' XP':'Путь обновлён');return;
   }}catch{setStatus('stale');}
  }
  setMessage('Попытка сохранена. Путь обновится после восстановления связи.');
 }
 return {data,status,message,error,busy,refresh,mutate,run,retry,wait,api};
}
export type CharacterState=ReturnType<typeof useCharacter>;

export function CharacterDashboard({character,onOpen}:{character:CharacterState;onOpen:()=>void}){
 const {data,status}=character,s=data.summary;
 if(data.preferences?.preferences?.rpg_visible===false||data.preferences?.preferences?.focus_mode)return null;
 return <section className="card character-dashboard" aria-label="Путь персонажа"><div className="section-heading"><span className="eyebrow">Белый Атлас</span><button className="text-button" onClick={onOpen}>Персонаж ↗</button></div>
  {s?<><h2>{s.rank.name}</h2><div className="xp-label"><strong>Уровень {s.level}</strong><span>{s.xp.toLocaleString('ru-RU')} XP</span></div><progress className="xp-bar" value={s.xp} max={s.next_level?.total_xp||s.xp||1} aria-label="Опыт до следующего уровня"/>
   {data.loadout&&data.catalog&&<CharacterScene compact slots={data.loadout.slots} items={data.catalog.items}/>}
   {s.level===60&&<p className="rhythm">Хроники · {s.chronicles}</p>}<p className="rhythm">Ритм · {s.rhythm.days_per_7} из 7 учебных дней</p><div className="next-reward"><Emblem/><div><small>Следующий рубеж</small><strong>{s.next_reward?.name||'Хроники Белого Атласа'}</strong><p>{s.next_reward?.requirement_text}</p></div></div>
   {status==='stale'&&<p className="pending-text">Показано последнее подтверждённое состояние</p>}</>:<p className="muted">{status==='loading'?'Загружаем путь…':'Путь временно недоступен'}</p>}
 </section>;
}

export function CharacterScreen({character,page}:{character:CharacterState;page:string}){
 const {data,status,error,busy,run,refresh,mutate}=character;
 const [slot,setSlot]=useState('chest'),[filter,setFilter]=useState('all'),[selected,setSelected]=useState<Obj|null>(null),[preview,setPreview]=useState<Obj|null>(null),[position,setPosition]=useState(0);
 useEffect(()=>{refresh(true);},[page]);
 const items:Obj[]=data.inventory?.items||data.catalog?.items||[];
 const slots=data.loadout?.slots||{};
 const pending=!!localStorage.getItem('crucible-character-command');
 async function equip(item:Obj|null){await run(async()=>{await mutate('me/loadout','PUT',{expected_revision:data.loadout.revision,slots:{...slots,[slot]:item?.id||null}});setPreview(null);await refresh(true);});}
 if(!data.summary&&!data.catalog)return <section className="card empty"><h1>Путь персонажа</h1><p>{status==='loading'?'Загрузка…':'Путь временно недоступен. Учебные материалы и попытки доступны.'}</p><button onClick={()=>refresh(true)}>Обновить</button></section>;
 return <>
  <div className="page-heading"><div><span className="eyebrow">Белый Атлас · {data.summary?.rank.name}</span><h1>{page==='path'?'Путь':page==='collection'?'Коллекция':'Персонаж'}</h1><p>{page==='character'?'Ваш облик и история освоения.':page==='path'?'Пять залов, двадцать пять томов.':'Девять мест для свидетельств пути.'}</p></div><button className="quiet" onClick={()=>refresh(true)}>Обновить состояние</button></div>
  {error&&<div className="alert" role="alert">{error}{error.includes('вкладке')||error.includes('409')?<button onClick={()=>refresh(true)}>Загрузить актуальный образ</button>:null}</div>}
  {pending&&<div className="alert">Надевание не подтверждено.<button disabled={busy} onClick={character.retry}>Повторить прежнюю команду образа</button></div>}
  {status==='stale'&&<p className="pending-text">Связь с путём временно недоступна. Сохранено последнее подтверждённое состояние.</p>}
  {page==='character'&&<>
   <div className="character-layout"><section className="card character-portrait"><span className="eyebrow">{preview?'Примерка':'Сохранённый образ'}</span><CharacterScene slots={preview||slots} items={items} preview={!!preview}/>{preview&&<button onClick={()=>setPreview(null)}>Завершить примерку</button>}<p className="muted">Уровень {data.summary?.level} · {data.summary?.xp.toLocaleString('ru-RU')} XP</p></section>
    <section className="wardrobe"><ChoiceButtons label="Слот экипировки" value={slot} onChange={v=>{setSlot(v);setSelected(null);}} options={Object.entries(slotLabels).map(([value,label])=>({value,label}))}/>
     <div className="slot-current"><span>{slotLabels[slot]}: <strong>{items.find(i=>i.id===slots[slot])?.name||'Без предмета'}</strong></span><button disabled={busy||!slots[slot]} onClick={()=>equip(null)}>Снять</button></div>
     <ChoiceButtons label="Показывать" value={filter} onChange={setFilter} options={[{value:'all',label:'Все'},{value:'owned',label:'Получено'},{value:'locked',label:'Пока закрыто'}]}/>
     <div className="item-grid">{items.filter(i=>i.slot===slot&&(filter==='all'||(filter==='owned'?i.owned:!i.owned))).sort((a,b)=>Number(b.equipped)-Number(a.equipped)||Number(b.owned)-Number(a.owned)||(a.tier||0)-(b.tier||0)).map(i=><button className={'item-card'+(selected?.id===i.id?' item-selected':'')} key={i.id} onClick={()=>setSelected(i)} aria-label={i.name}>
      <span className="item-art"><Emblem name={slot==='sword'?'practice':slot==='back_ornament'?'star':'character'}/>{i.icon_path&&<img loading="lazy" src={i.icon_path} alt=""/>}</span><strong>{i.name}</strong><span className="item-status">{i.equipped?'Надето':i.owned?'Получено':'Пока закрыто'}</span><small>{i.requirement_text}</small><small>{artLabels[i.art_status]||'Изображение готовится'}</small></button>)}</div>
     {selected&&<section className="card item-detail" aria-label="Описание предмета"><span className="eyebrow">{slotLabels[slot]}</span><h2>{selected.name}</h2><p>{selected.requirement_text}</p><p>{selected.evidence_recheck?'Предмет остаётся у вас; основание требует перепроверки.':selected.owned?'Получено по подтверждённым условиям.':'Условия ещё не подтверждены.'}</p><p>{artLabels[selected.art_status]}</p><div className="button-row"><button onClick={()=>setPreview({...slots,[slot]:selected.id})}>Примерить</button><button className="primary" disabled={busy||!selected.owned} onClick={()=>equip(selected)}>Надеть</button><button disabled={busy||selected.owned} onClick={()=>run(async()=>{await mutate('me/preferences','PATCH',{expected_revision:data.preferences.revision,...data.preferences.preferences,pinned_reward:selected.id});await refresh(true);})}>Следующая награда</button></div></section>}
    </section></div>
   <section className="card rpg-preferences"><h2>Показ пути</h2><p>Режим учёбы скрывает декоративные блоки.</p><div className="button-row">{[['rpg_visible','Показывать персонажа'],['focus_mode','Режим учёбы']].map(([key,label])=><label key={key}><input type="checkbox" checked={!!data.preferences?.preferences[key]} disabled={busy} onChange={e=>run(async()=>{await mutate('me/preferences','PATCH',{expected_revision:data.preferences.revision,...data.preferences.preferences,[key]:e.target.checked});await refresh(true);})}/>{label}</label>)}</div></section>
   <details className="card set-gallery"><summary>Образы комплектов · полные исходные иллюстрации</summary><p>Эта галерея показывает художественные образцы. Выбор частей сохраняется в экипировке выше.</p><div>{data.catalog?.sets.filter((s:Obj)=>s.tier<5).map((s:Obj)=><figure key={s.id}><img loading="lazy" src={'/character/gallery/'+s.id+'.webp'} alt={s.name}/><figcaption>{s.name} · образец</figcaption></figure>)}</div></details>
  </>}
  {page==='path'&&data.path&&<>
   <div className="rank-track">{data.path.ranks.map((r:Obj)=><section className="card" key={r.id}><Emblem name="path"/><h2>{r.name}</h2><p>{r.requirement_text}</p><strong>{data.summary?.rank.id===r.id?'Текущий ранг':''}</strong></section>)}</div>
   <div className="hall-list">{data.path.disciplines.map((d:Obj)=><section className="card" key={d.id} style={{borderTopColor:d.color}}><span className="eyebrow">{d.hall}</span><h2>{d.name}</h2>{data.path.volumes.filter((v:Obj)=>v.discipline_id===d.id).map((v:Obj)=><article className="volume-row" key={v.id}><strong>{v.name}</strong><div>{[['V','Трактат'],['E','Испытание'],['R','Закалка']].map(([kind,label])=>{const seal=data.path.seals[kind+'-'+v.id];return <span className={seal?.current_qualified?'qualified':'unbound'} key={kind} title={seal?.status==='BLOCKED_CONTENT'?'Нет подготовленного испытания':seal?.current_qualified?'Подтверждено':'Условия ещё не выполнены'}>{label} · {seal?.current_qualified?'✓':seal?.status==='BLOCKED_CONTENT'?'нет испытания':'ожидает'}</span>;})}</div></article>)}</section>)}</div>
   <p className="muted">Испытания без опубликованных условий отмечены отдельно. Учебный банк доступен независимо от печатей.</p>
   <h2>Проверки дисциплин и пробники</h2><div className="rank-track">{data.path.trials?.map((trial:Obj)=><section className="card trial-card" key={trial.id}><h3>{trial.seal==='K'?'Печать дисциплины · '+data.path.disciplines.find((d:Obj)=>d.id===trial.discipline_id)?.name:'Пробник · '+trial.id}</h3><p>{trial.problem_count} задач · результат ≥ {trial.min_score}% · задача C ≥ {trial.min_C_fraction*100}%</p>{trial.requires_E&&<p>Печати испытаний: {trial.requires_E}. Закалки: {trial.requires_R}.</p>}<p>Новые условия, самостоятельное решение. Ориентир: {trial.suggested_minutes} мин, без обязательного ограничения времени.</p><strong>{data.path.seals[trial.id]?.current_qualified?'Подтверждено':data.path.seals[trial.id]?.status==='BLOCKED_CONTENT'?'Испытание ещё не опубликовано':'Условия ещё не подтверждены'}</strong></section>)}</div>
  </>}
  {page==='collection'&&<><div className="collection-grid" aria-label="Девять мест коллекции">{Array.from({length:9},(_,i)=>{const id=data.collection?.positions[i],item=items.find(x=>x.id===id);return <button className={position===i?'selected':''} key={i} onClick={()=>setPosition(i)} aria-pressed={position===i}><Emblem name="collection"/><span>Место {i+1}</span><strong>{item?.name||'Свободно'}</strong></button>;})}</div><section className="card"><h2>Место {position+1}</h2><div className="button-row"><button disabled={busy} onClick={()=>run(async()=>{const positions=[...data.collection.positions];positions[position]=null;await mutate('me/collection','PUT',{expected_revision:data.collection.revision,positions});await refresh(true);})}>Освободить</button>{items.filter(i=>i.kind==='relic'&&i.owned).map(i=><button key={i.id} disabled={busy} onClick={()=>run(async()=>{const positions=data.collection.positions.map((x:string|null)=>x===i.id?null:x);positions[position]=i.id;await mutate('me/collection','PUT',{expected_revision:data.collection.revision,positions});await refresh(true);})}>{i.name}</button>)}</div><p className="muted">Реликвии открываются по достижениям. Одна реликвия занимает одно место.</p></section></>}
  <details className="card reward-history"><summary>Журнал пути</summary>{data.journal?.chapters?.map((chapter:Obj)=><details key={chapter.id}><summary>{chapter.title} · {chapter.text.split('. ')[0]}.</summary><p>{chapter.text}</p></details>)}{data.journal?.entries.length?data.journal.entries.map((e:Obj)=><p key={e.id}>{new Date(e.created_at).toLocaleDateString('ru-RU')} · {e.delta>0?'+':''}{e.delta} XP{e.items.length?' · новые предметы: '+e.items.map((id:string)=>items.find(i=>i.id===id)?.name||id).join(', '):''}</p>):<p>Новые подтверждённые результаты появятся здесь.</p>}</details>
 </>;
}
