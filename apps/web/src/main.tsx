import React, {useEffect,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import 'katex/dist/katex.min.css';
import './style.css';
import './study.css';
import './atmosphere.css';
import {MathText} from './MarkdownView';
import {Workspace} from './Workspace';
import {TheoryReader} from './TheoryReader';
import {StudyNavigation} from './StudyNavigation';
import {ChoiceButtons} from './Choice';
import {migrateBrowserStorage} from './BrowserStorage';
import {materialRouteKey, openedMaterial, rememberOpenedMaterial, useBrowserNavigation} from './BrowserNavigation';
import type {Page, Route} from './BrowserNavigation';

migrateBrowserStorage(localStorage);

type Obj=Record<string,any>;
const uid=()=>crypto.randomUUID();
let csrf='';
let commandInFlight=false;
const unknownCommand=()=>!commandInFlight&&!!localStorage.getItem('crucible-pending-command');
async function api(path:string,method='GET',body?:Obj):Promise<any>{
  const response=await fetch('/api/v1/'+path,{method,headers:{'Content-Type':'application/json',...(csrf?{'X-CSRF-Token':csrf}:{})},body:body?JSON.stringify(body):undefined});
  if(!response.ok){let data;try{data=await response.json();}catch{data={detail:'Сервис временно недоступен'};}const e=new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));Object.assign(e,{status:response.status});throw e;}
  return response.json();
}
async function send(path:string,method:string,body:Obj){
  if(localStorage.getItem('crucible-pending-command'))throw new Error('Есть команда с неизвестным исходом. Повторите её через уведомление о неподтверждённой команде.');
  const payload={command_id:uid(),...body};
  localStorage.setItem('crucible-pending-command',JSON.stringify({path,method,payload}));
  commandInFlight=true;
  try{for(let retry=0;retry<2;retry++){
      try{const result=await api(path,method,payload);localStorage.removeItem('crucible-pending-command');return result;}
      catch(e){const status=(e as any).status;if(status>=400&&status<500){localStorage.removeItem('crucible-pending-command');throw e;}if(retry===1)throw e;}
  }}finally{commandInFlight=false;}
}

const sections:Obj={probability:'Вероятности',statistics:'Статистика',calculus:'Математический анализ',multivariable:'Многомерный анализ',linalg:'Линейная алгебра',ode:'Дифференциальные уравнения',combinatorics:'Комбинаторика'};
const skillLabels:Obj={not_seen:'Нет завершённых попыток',learning:'Требует разбора',practicing:'В работе',transfer_confirmed:'Перенос подтверждён',review_due:'Пора повторить',insufficient_bank:'Мало размеченных семейств'};

function App(){
 const {route,go}=useBrowserNavigation(),page=route.page,locationKey=materialRouteKey(route);
 const routeRef=useRef(route);routeRef.current=route;
 const libraryQuery=route.query||'',librarySection=route.section||'';
 const setLibraryQuery=(query:string)=>go({...route,query},true),setLibrarySection=(section:string)=>go({...route,section},true);
 const [attemptLoading,setAttemptLoading]=useState(false),[materialLoading,setMaterialLoading]=useState(false),[materialRetry,setMaterialRetry]=useState(0);
 const [attemptError,setAttemptError]=useState(false);
 const [dataLoading,setDataLoading]=useState(false);
 const [logged,setLogged]=useState(false),[loading,setLoading]=useState(true),[password,setPassword]=useState(''),[error,setError]=useState('');
 const [catalog,setCatalog]=useState<Obj|null>(null),[today,setToday]=useState<Obj|null>(null),[progress,setProgress]=useState<Obj|null>(null),[history,setHistory]=useState<Obj[]>([]),[questions,setQuestions]=useState<Obj[]>([]);
 const [attempt,setAttempt]=useState<Obj|null>(null),[draft,setDraft]=useState(''),[saveState,setSaveState]=useState('saved'),[busy,setBusy]=useState(false),[panel,setPanel]=useState<Obj|null>(null),[outcomes,setOutcomes]=useState<Obj>({}),[reflection,setReflection]=useState(''),[question,setQuestion]=useState(''),[job,setJob]=useState<Obj|null>(null),[tick,setTick]=useState(0),[pendingCommand,setPendingCommand]=useState(false);
 const [restore,setRestore]=useState<Obj|null>(null),[editSettings,setEditSettings]=useState(false),[dailyCount,setDailyCount]=useState(3),[zone,setZone]=useState(Intl.DateTimeFormat().resolvedOptions().timeZone);
 const aRef=useRef<Obj|null>(null),draftAttempt=useRef<string|null>(null),savedDraft=useRef(''),draftRef=useRef(''),chain=useRef(Promise.resolve(true)),seqRef=useRef(0);
 function receive(a:Obj|null,open=false){aRef.current=a;setAttempt(a);if(a){seqRef.current=Math.max(seqRef.current,a.learning_input_seq||0);}if(open&&a){draftAttempt.current=a.id;setDraft(a.draft);draftRef.current=a.draft;savedDraft.current=a.draft;setOutcomes(Object.fromEntries(a.problem.parts.map((p:Obj)=>[p.id,a.part_outcomes?.find((x:Obj)=>x.part_id===p.id)?.outcome||(a.help?.some((h:Obj)=>h.mathematical&&!h.retracted)?'assisted':'independent')])));setReflection(a.reflection||'');setSaveState('saved');setRestore(null);const old=localStorage.getItem('crucible-emergency-'+a.id);if(old){const d=JSON.parse(old);if(d.draft!==a.draft)setRestore(d);}}}
 function enqueue(work:()=>Promise<void>){chain.current=chain.current.then(async()=>{try{await work();return true;}catch(e){setError((e as Error).message);setSaveState('error');setPendingCommand(unknownCommand());return false;}});return chain.current;}

 async function load(){
  setDataLoading(true);
  const results=await Promise.allSettled([api('practice/current'),api('learning/today?at_least_practice_seq='+seqRef.current),api('learning/progress?at_least_practice_seq='+seqRef.current),api('content/catalog'),api('practice/attempts'),api('practice/review-queue')]);
  if(results[0].status==='fulfilled'){seqRef.current=Math.max(seqRef.current,results[0].value.learning_input_seq);const current=results[0].value.attempt,wanted=routeRef.current;if((wanted.page!=='practice'||!wanted.attemptId||wanted.attemptId===current?.id)&&(!aRef.current||aRef.current.state!=='completed'))receive(current);}
  if(results[1].status==='fulfilled'){let t=results[1].value;if(!t.plan&&t.catalog_available){try{await send('learning/daily-plans','POST',{});t=await api('learning/today?at_least_practice_seq='+seqRef.current);}catch{}}setToday(t);setDailyCount(t.settings.daily_count);setZone(t.settings.timezone);}
  if(results[2].status==='fulfilled')setProgress(results[2].value);
  if(results[3].status==='fulfilled')setCatalog(results[3].value);
  if(results[4].status==='fulfilled')setHistory(results[4].value.attempts);
  if(results[5].status==='fulfilled')setQuestions(results[5].value.questions);
  const missing=results.map((r,i)=>r.status==='rejected'?['попытки','план','прогресс','материалы','история','вопросы'][i]:null).filter(Boolean);
  setDataLoading(false);
  if(missing.length)setError('Временно недоступны: '+missing.join(', ')+'. Сохранение текущей попытки не требует планировщика.');
 }
 useEffect(()=>{api('practice/auth/session').then(s=>{csrf=s.csrf;setLogged(true);setPendingCommand(unknownCommand());}).catch(()=>{}).finally(()=>setLoading(false));},[]);
 useEffect(()=>{if(logged)load();},[logged]);
 useEffect(()=>{
  if(!logged||page!=='practice'||!route.attemptId)return;
  if(aRef.current?.id===route.attemptId&&draftAttempt.current===route.attemptId)return;
  let cancelled=false;setAttemptLoading(true);setAttemptError(false);
  api('practice/attempts/'+encodeURIComponent(route.attemptId)).then(a=>{if(!cancelled)receive(a,true);}).catch(e=>{if(!cancelled){setError(e.message);setAttemptError(true);}}).finally(()=>{if(!cancelled)setAttemptLoading(false);});
  return()=>{cancelled=true;setAttemptLoading(false);};
 },[logged,page,route.attemptId]);
 useEffect(()=>{if(logged&&page==='practice'&&!route.attemptId&&attempt)go({...route,attemptId:attempt.id},true);},[logged,page,route.attemptId,attempt?.id]);
 useEffect(()=>{
  if(!logged)return;
  if(!locationKey){setPanel(null);setMaterialLoading(false);return;}
  const current=routeRef.current;
  if(current.page==='practice'&&(!attempt||attempt.id!==current.attemptId||draftAttempt.current!==current.attemptId))return;
  let cancelled=false;
  const cached=current.page==='practice'?openedMaterial(locationKey):null;
  if(cached){setPanel({...cached,locationKey});setMaterialLoading(false);return;}
  const publicMaterial=current.material==='core'||current.material==='theory';
  if(!publicMaterial){setPanel({kind:'help',title:'Материал к попытке',text:'Этот материал нужно открыть из рабочего места задачи.',locationKey});setMaterialLoading(false);return;}
  const release=current.releaseId||(current.page==='practice'?attempt?.problem.content_release_id:catalog?.content_release_id),topic=current.topicId||attempt?.problem.topic_id;
  if(!release||!topic)return;
  if(current.page==='practice'&&attempt?.state!=='completed'&&!attempt?.help?.some((h:Obj)=>h.kind===current.material&&!h.retracted)){
   setPanel({kind:'help',title:'Материал к попытке',text:'Откройте конспект через «Помощь и материалы», чтобы чтение было учтено в попытке.',locationKey});return;
  }
  setMaterialLoading(true);setPanel(null);
  api('content/topics/'+encodeURIComponent(topic)+'/'+current.material+'?release_id='+encodeURIComponent(release)).then(result=>{
   if(cancelled)return;
   setPanel({...result,kind:current.material,locationKey});
   if(!current.releaseId)go({...routeRef.current,releaseId:release},true);
  }).catch(e=>{if(!cancelled)setError(e.message);}).finally(()=>{if(!cancelled)setMaterialLoading(false);});
  return()=>{cancelled=true;};
 },[logged,locationKey,catalog?.content_release_id,attempt?.id,attemptLoading,materialRetry]);
 useEffect(()=>{const id=setInterval(()=>setTick(t=>t+1),1000);return()=>clearInterval(id);},[]);
 useEffect(()=>{if(!logged)return;const id=setInterval(()=>{api('learning/progress?at_least_practice_seq='+seqRef.current).then(setProgress).catch(()=>{});},2500);return()=>clearInterval(id);},[logged]);
 async function persist(extra:Obj={}){const a=aRef.current;if(!a||draftAttempt.current!==a.id||!['running','paused'].includes(a.state))return;setSaveState('saving');const text=draftRef.current;const result=await send('practice/attempts/'+a.id,'PATCH',{expected_revision:a.revision,draft:text,...extra});receive(result);setPendingCommand(unknownCommand());savedDraft.current=text;setSaveState(draftRef.current===text?'saved':'unsaved');if(draftRef.current===text)localStorage.removeItem('crucible-emergency-'+a.id);}
 useEffect(()=>{if(!attempt||draft===savedDraft.current)return;setSaveState('unsaved');const id=setTimeout(()=>enqueue(()=>persist()),1200);return()=>clearTimeout(id);},[draft]);
 useEffect(()=>{if(!logged)return;const id=setInterval(()=>{if(aRef.current?.state==='running'&&document.visibilityState==='visible'&&document.hasFocus())enqueue(()=>persist());},20000);return()=>clearInterval(id);},[logged]);
 async function login(e:React.FormEvent){e.preventDefault();setError('');try{const s=await api('practice/auth/login','POST',{password});csrf=s.csrf;setPassword('');setLogged(true);setPendingCommand(unknownCommand());}catch(e){setError((e as Error).message);}}
 async function run(work:()=>Promise<void>){setError('');setBusy(true);try{await work();}catch(e){setError((e as Error).message);}finally{setBusy(false);setPendingCommand(unknownCommand());}}
 async function start(p:Obj){await run(async()=>{await chain.current;if(aRef.current&&['running','paused'].includes(aRef.current.state)){if(!await enqueue(()=>persist()))return;receive(aRef.current,true);go({page:'practice',attemptId:aRef.current.id});return;}const a=await send('practice/attempts','POST',{problem_id:p.id,content_release_id:p.content_release_id||today?.plan?.content_release_id||catalog?.content_release_id});receive(a,true);go({page:'practice',attemptId:a.id});await load();});}
 function openAttempt(id:string){go({page:'practice',attemptId:id});window.scrollTo({top:0});}
 async function help(kind:string,topicId?:string,anchor?:string){await run(async()=>{
  if(!await enqueue(()=>persist()))throw new Error('Сохранение не подтверждено. Разрешите конфликт или повторите прежнюю команду.');
  const a=aRef.current!,result=await send('practice/attempts/'+a.id+'/help','POST',{expected_revision:a.revision,kind,...(topicId?{topic_id:topicId}:{})});receive(result.attempt);
  if(result.attempt.help?.some((h:Obj)=>h.mathematical&&!h.retracted))setOutcomes(previous=>Object.fromEntries(Object.entries(previous).map(([key,value])=>[key,value==='independent'?'assisted':value])));
  const next:Route={page:'practice',attemptId:a.id,material:kind,topicId:topicId||a.problem.topic_id,releaseId:a.problem.content_release_id,anchor};
  const t=result.material,material=kind==='core'||kind==='theory'?{...t,kind}:t?{kind:'help',text:t.text,title:kind==='solution'?'Разбор решения':'Подсказка '+kind.slice(1)}:{kind:'help',title:'Разбор с внешним агентом',text:'Сохранённый контекст доступен через study-mcp. Откройте внешний агент и вызовите get_study_context. Встроенного чата и вызовов LLM в приложении нет.'};
  const key=materialRouteKey(next);rememberOpenedMaterial(key,material);setPanel({...material,locationKey:key});go(next);
 });}
 async function finish(){await run(async()=>{if(!await enqueue(()=>persist()))throw new Error('Сохранение не подтверждено. Разрешите конфликт или повторите прежнюю команду.');const a=aRef.current!;const result=await send('practice/attempts/'+a.id+'/complete','POST',{expected_revision:a.revision,part_outcomes:a.problem.parts.map((p:Obj)=>({part_id:p.id,outcome:outcomes[p.id]})),reflection});receive(result);setSaveState('saved');go({page:'practice',attemptId:result.id});await load();});}
 async function addQuestion(){await run(async()=>{if(!await enqueue(()=>persist()))throw new Error('Сохранение не подтверждено. Разрешите конфликт или повторите прежнюю команду.');const a=aRef.current!;await send('practice/attempts/'+a.id+'/questions','POST',{expected_revision:a.revision,text:question});setQuestion('');receive(await api('practice/attempts/'+a.id));await load();});}
 const completedIds=new Set(history.filter(h=>h.state==='completed'&&today?.plan&&h.completed_at>=today.plan.generated_at).map(h=>h.problem_id));
 const plan=today?.plan;
 const currentSkills=(progress?.skills||[]).filter((skill:Obj)=>skill.attempt_count>0&&catalog?.problems.some((problem:Obj)=>problem.primary_skill_id===skill.skill_id));
 const pending=!!progress&&(progress.pending||progress.applied_practice_seq<seqRef.current);
 const active=attempt&&['running','paused'].includes(attempt.state);
 const seconds=attempt?Math.floor(attempt.active_seconds+(attempt.state==='running'?Math.min(45,Math.max(0,(Date.now()-Date.parse(attempt.heartbeat_at))/1000)):0)):0;
 void tick;

 async function retryPendingCommand(){const pending=JSON.parse(localStorage.getItem('crucible-pending-command')!);const result=await api(pending.path,pending.method,pending.payload);localStorage.removeItem('crucible-pending-command');setPendingCommand(false);const updated=result.attempt||(result.problem?result:null);if(updated&&updated.id===aRef.current?.id){receive(updated);if(updated.draft===draftRef.current){savedDraft.current=updated.draft;setSaveState('saved');localStorage.removeItem('crucible-emergency-'+updated.id);}else setSaveState('unsaved');}await load();}
 function readMaterial(id:string,anchor?:string){if(page==='practice'&&attempt){help('core',id,anchor);return;}const topic=catalog?.topics.find((t:Obj)=>t.id===id);go({page:'library',topicId:id,material:topic?.materials?.core?'core':'theory',releaseId:catalog?.content_release_id,anchor});window.scrollTo({top:0});}
 function navigate(next:Page){go({page:next,...(next==='practice'&&attempt?{attemptId:attempt.id}:{})});window.scrollTo({top:0});}
 function changeDraft(text:string){setDraft(text);draftRef.current=text;const a=aRef.current;if(a)localStorage.setItem('crucible-emergency-'+a.id,JSON.stringify({draft:text,revision:a.revision}));}
 function closeMaterial(){go({page,attemptId:route.attemptId});if(page==='practice'&&active)enqueue(()=>persist({timer_mode:'solving'}));}
 const visiblePanel=panel?.locationKey===locationKey?{...panel,anchor:route.anchor}:null;
 const readerLocation={chapter:route.chapter??(route.anchor?undefined:0),laboratory:route.laboratory,onLocationChange:(location:{chapter:number;laboratory:boolean})=>go({...route,...location,anchor:undefined})};
 const attemptUnavailable=page==='practice'&&!!route.attemptId&&attempt?.id!==route.attemptId;
 const routePending=attemptLoading||attemptUnavailable&&!attemptError;
 const materialPlaceholder=<section className="empty card"><p>{materialLoading?'Загрузка материала…':'Не удалось открыть материал.'}</p>{!materialLoading&&<button onClick={()=>setMaterialRetry(value=>value+1)}>Повторить загрузку</button>}<button onClick={closeMaterial}>Вернуться</button></section>;
 if(loading)return <div className="loading">Crucible · загрузка…</div>;
 if(!logged)return <main className="login">
   <div className="brandmark" aria-hidden="true">C</div><span className="eyebrow">Подготовка к магистратуре</span>
   <h1>Crucible</h1><p>Задачи по математике, теория и повторение<br/>по результатам вашей работы.</p>
   <form onSubmit={login}><label>Пароль владельца<input type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} required autoFocus/></label><button className="primary" type="submit">Войти</button></form>
   {error&&<p role="alert" className="error">{error}</p>}<small>Локальный учебный профиль</small>
 </main>;
 return <StudyNavigation.Provider value={{material:readMaterial,problem:(id:string)=>{go({page:'library',query:id});window.scrollTo({top:0});},lab:()=>{}}}><div className={'shell' + (visiblePanel && ['practice','library'].includes(page) ? ' shell-reading' : '')}>
   <aside className="sidebar">
     <a className="brand" href="#" aria-label="Crucible — на главную" onClick={e=>{e.preventDefault();navigate('today');}}><div className="brandmark small" aria-hidden="true">C</div><strong>Crucible<span>Математика</span></strong></a>
     <div className="nav-caption">Учебный профиль</div>
     <nav aria-label="Основная навигация">{[['today','◷','Сегодня'],['practice','✎','Рабочее место'],['library','▤','Материалы'],['questions','☷','Вопросы и разбор']].map(([id,icon,label])=><button key={id} aria-label={label} aria-current={page===id?'page':undefined} className={page===id?'selected':''} onClick={()=>navigate(id as Page)}><span className="nav-icon" aria-hidden="true">{icon}</span><span className="nav-label">{label}</span>{id==='questions'&&questions.length>0&&<small>{questions.length}</small>}</button>)}</nav>
     <div className="sidebar-note"><span className="status-dot"/>Тестовые данные<p>Личная история ещё<br/>не импортирована.</p></div>
     <button className="logout" onClick={()=>run(async()=>{await api('practice/auth/logout','POST',{});setLogged(false);csrf='';})}>Выйти</button>
   </aside>
   <div className="body"><header className="topbar"><span>{page==='practice'?'Рабочее место':page==='library'?'Учебные материалы':page==='questions'?'Вопросы и история':'План и повторения'}</span><span className="profile">Владелец · локальный профиль</span></header>
   <main className={'main '+(page==='practice'?'practice-main':'')}>
     {error&&<div className="alert" role="alert">{error}<button onClick={()=>setError('')} aria-label="Закрыть ошибку">×</button></div>}
     {pendingCommand&&<div className="alert">Ответ на предыдущую команду не получен.<button onClick={()=>run(retryPendingCommand)}>Проверить повтором прежней команды</button></div>}
     {page==='today'&&<>
       <div className="page-heading"><div><span className="eyebrow">{new Date().toLocaleDateString('ru-RU',{weekday:'long',day:'numeric',month:'long'})}</span><h1>Сегодня</h1><p>Задачи и повторения по текущему плану.</p></div><button className="quiet" onClick={()=>setEditSettings(!editSettings)}>Настроить занятие</button></div>
       {editSettings&&today&&<section className="card settings"><label>Задач в день<input type="number" min="1" max="10" value={dailyCount} onChange={e=>setDailyCount(+e.target.value)}/></label><label>Учебный часовой пояс<input value={zone} onChange={e=>setZone(e.target.value)}/></label><button onClick={()=>run(async()=>{await send('learning/settings','PATCH',{expected_revision:today.settings.revision,timezone:zone,daily_count:dailyCount});setEditSettings(false);await load();})}>Сохранить настройки</button><p className="muted">Чтобы изменить сохранённый план, обновите его отдельно.</p></section>}
       <div className="dashboard"><section>
         <div className="session-banner"><div><span className="eyebrow light">{active?'Текущая попытка':'Занятие'}</span><h2><MathText text={active?attempt.problem.title:'План на сегодня'} inline/></h2><p>{active?`${attempt.problem.id} · ${attempt.state==='paused'?'на паузе':'в работе'}`:`${plan?.items?.length||0} задач · условия, теория и сохранённое решение`}</p></div><button className="cream" disabled={busy||(!active&&!plan?.items?.length)} onClick={()=>active?start(attempt.problem):start(plan.items.find((p:Obj)=>!completedIds.has(p.id))||plan.items[0])}>{active?'Продолжить задачу':'Начать занятие'} →</button></div>
         <div className="section-heading"><h2>Задачи <span>{plan?.items?.length||0}</span></h2><button className="text-button" disabled={busy||!plan} onClick={()=>run(async()=>{await send('learning/daily-plans','POST',{refresh:true,expected_revision:plan.revision});await load();})}>Обновить план</button></div>
         {!plan&&<div className="card empty">{dataLoading?'Загрузка плана…':today?.catalog_available?'План создаётся…':'План недоступен. Задачу можно выбрать в материалах.'}<button onClick={()=>run(load)}>Повторить загрузку</button></div>}
         <div className="task-list">{plan?.items.map((p:Obj,i:number)=><article className="task-card" key={p.id}><span className="task-number">{String(i+1).padStart(2,'0')}</span><div><div className="task-meta">{sections[p.section]||p.section}<span> · {p.id} · {p.level}</span></div><h3><MathText text={p.title} inline/></h3><p>{p.reason}</p></div><div className="task-end"><small>{p.estimated_minutes?p.estimated_minutes.join('–')+' мин':''}</small>{completedIds.has(p.id)?<span className="done">✓ Выполнено</span>:<button aria-label={'Решать '+p.id} disabled={busy} onClick={()=>start(p)}>→</button>}</div></article>)}</div>
         {plan?.shortfall_reason&&<p className="muted">{plan.shortfall_reason}</p>}
         {plan?.items?.length>0&&plan.items.every((p:Obj)=>completedIds.has(p.id))&&<div className="card success"><h3>План выполнен</h3><p>Можно закончить занятие. Другие задачи доступны в материалах.</p></div>}
         <p className="footnote">План на {plan?.date||'сегодня'} · {plan?.timezone||'Europe/Moscow'}. Сохраняется при обновлении страницы.</p>
       </section><aside className="right-column">
         <section className="card progress-card"><span className="eyebrow">По завершённым попыткам</span><h2>Результаты</h2><div className="big-stat">{history.filter(h=>h.state==='completed').length}<small>попыток в истории</small></div><div className="divider"/>{currentSkills.map((s:Obj)=><div className="skill" key={s.skill_id}><div><strong><MathText text={s.skill_title||s.skill_id} inline/></strong><span>{skillLabels[s.state]}</span></div><small>{s.distinct_families} сем.</small></div>)}{!progress?<p className="muted">Расчёт временно недоступен.</p>:currentSkills.length===0&&<p className="muted">По текущему банку ещё нет результатов.</p>}<div className={'sync-state '+(pending?'pending':'')}>{pending?'Повторения пересчитываются':progress?'Учтены факты до № '+progress.applied_practice_seq:'Нет связи с планировщиком'}</div></section>
         <section className="note-card"><h3>Как назначаются повторения</h3><p>Учитываются результат, использованная помощь и разные семейства задач. Повтор одной карточки не подтверждает перенос навыка.</p></section>
         <button className="export-button" disabled={busy} onClick={()=>run(async()=>{const j=await send('reports/jobs','POST',{});setJob(j);})}>Выгрузить историю</button>
         {job&&<div className="card"><p>Экспорт: {job.status==='ready'?'готов':job.status==='queued'?'в очереди':job.status}</p><button onClick={()=>run(async()=>{const j=await api('reports/jobs/'+(job.job_id||job.id));setJob({...j,job_id:job.job_id||job.id});if(j.status==='ready'){const data=await api('reports/jobs/'+(job.job_id||job.id)+'/artifact');const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='study-export.json';a.click();URL.revokeObjectURL(url);}})}>Проверить и скачать</button></div>}
       </aside></div>
     </>}
     {page==='practice'&&(routePending?<div className="loading">Загрузка попытки…</div>:route.material&&!visiblePanel?materialPlaceholder:!attempt||attemptUnavailable?<section className="empty card"><h1>Нет текущей попытки</h1><p>Выберите задачу из плана или материалов.</p><button className="primary" onClick={()=>navigate('today')}>Открыть план</button></section>:<Workspace
       attempt={attempt} draft={draft} saveState={saveState} active={active} seconds={seconds} busy={busy} panel={visiblePanel} readerLocation={readerLocation} pending={pending} outcomes={outcomes} reflection={reflection} question={question} restore={restore}
       onDraft={changeDraft} onSave={()=>enqueue(()=>persist())} onPause={()=>enqueue(()=>persist({state:attempt.state==='running'?'paused':'running'}))} onHelp={help} onCloseMaterial={closeMaterial} onFinish={finish}
       onAbandon={()=>enqueue(async()=>{await persist({state:'abandoned'});await load();navigate('today');})} onToday={()=>navigate('today')}
       onOutcome={(id:string,value:string)=>setOutcomes({...outcomes,[id]:value})} onReflection={setReflection} onQuestion={setQuestion} onAddQuestion={addQuestion}
       onResolve={(q:Obj)=>run(async()=>{await send('practice/questions/'+q.id,'PATCH',{expected_revision:q.revision,status:'resolved'});receive(await api('practice/attempts/'+attempt.id));await load();})}
       onApprove={(id:string)=>run(async()=>{receive(await send('practice/proposals/'+id+'/approve','POST',{}));await load();})}
       onRestore={()=>{changeDraft(restore!.draft);setRestore(null);}} onKeepServer={()=>{localStorage.removeItem('crucible-emergency-'+attempt.id);setRestore(null);}}
     />)}
     {page==='library'&&(route.material?(visiblePanel?<TheoryReader material={visiblePanel as any} {...readerLocation} onClose={closeMaterial} closeLabel="К материалам"/>:materialPlaceholder):<>
       <div className="page-heading"><div><span className="eyebrow">Учебный банк</span><h1>Материалы</h1><p>{catalog?.problems.length||0} задач · {catalog?.topics.length||0} заметки из Obsidian</p></div></div>
       <div className="topic-grid">{catalog?.topics.map((t:Obj)=><section className="card" key={t.id}><span className="eyebrow">Из Obsidian</span><h2><MathText text={t.title} inline/></h2><button onClick={()=>readMaterial(t.id)}>Читать конспект →</button></section>)}</div>
       <div className="library-filters"><label>Поиск по задачам<input type="search" value={libraryQuery} onChange={event=>setLibraryQuery(event.target.value)} placeholder="ID, название или тип"/></label><ChoiceButtons label="Раздел" className="section-choices" value={librarySection} onChange={setLibrarySection} options={[{value:"",label:"Все разделы"},...[...new Set<string>((catalog?.problems||[]).map((p:Obj)=>p.section))].map(section=>({value:section,label:sections[section]||section}))]}/></div>
       <h2>Задачи</h2><div className="task-list">{catalog?.problems.filter((p:Obj)=>(!librarySection||p.section===librarySection)&&[p.id,p.title,p.skill_title,p.primary_skill_id].join(' ').toLowerCase().includes(libraryQuery.toLowerCase())).map((p:Obj)=><article className="task-card" key={p.id}><span className="task-number">{p.level}</span><div><small>{p.id} · {p.primary_skill_id} · {sections[p.section]||p.section}</small><h3><MathText text={p.title} inline/></h3></div><button disabled={busy} onClick={()=>start({...p,content_release_id:catalog.content_release_id})}>Начать →</button></article>)}</div>

     </>)}
     {page==='questions'&&<>
       <div className="page-heading"><div><h1>Вопросы и разбор</h1><p>Вопросы связаны с попытками. После разбора их можно закрыть вручную.</p></div></div>
       {questions.length===0?<section className="card empty">Открытых вопросов нет.</section>:questions.map(q=><section className="card question" key={q.id}><MathText text={q.text}/><button onClick={()=>openAttempt(q.attempt_id)}>Открыть попытку →</button></section>)}
       <h2>Завершённые попытки</h2>{history.filter(h=>h.state==='completed').map(h=><button className="history-row" key={h.id} onClick={()=>openAttempt(h.id)}><span>{h.problem_id} · <MathText text={h.title} inline/></span><small>{new Date(h.completed_at).toLocaleDateString('ru-RU')} →</small></button>)}
     </>}
     <footer><span>Crucible</span><span>Математика · подготовка к магистратуре</span></footer>
   </main></div>
 </div></StudyNavigation.Provider>;
}
createRoot(document.getElementById('root')!).render(<App/>);
