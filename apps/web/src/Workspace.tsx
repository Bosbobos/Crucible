import {useEffect, useRef, useState} from 'react';
import {MathText} from './MarkdownView';
import {TheoryReader} from './TheoryReader';
import {MathEditor} from './MathEditor';
import type {MathEditorHandle} from './MathEditor';
import {ChoiceButtons} from './Choice';

type Obj = Record<string, any>;
const labels: Record<string, string> = {independent: 'Самостоятельно', assisted: 'С помощью', reviewed: 'Разобрал решение', unfinished: 'Не закончил'};
const saveLabels: Record<string, string> = {saved: 'Сохранено сервером', saving: 'Сохраняем…', unsaved: 'Есть несохранённый текст', error: 'Сохранение не подтверждено'};

function DraftEditor({draft, onChange, saveState, active, onSave, mode, setMode}: {
  draft: string; onChange: (text: string) => void; saveState: string; active: boolean;
  onSave: () => void; mode: string; setMode: (mode: string) => void;
}) {
  const field = useRef<MathEditorHandle>(null);
  return <section className="draft notebook" aria-label="Редактор решения">
    <div className="notebook-header"><h2>Моё решение</h2><span className={'save-state ' + saveState} role="status">{saveState === 'saved' ? '✓ ' : ''}{saveLabels[saveState]}</span></div>
    <div className="editor-toolbar">
      <div className="segmented" role="tablist" aria-label="Режим редактора">
        <button role="tab" aria-selected={mode === 'edit'} onClick={() => setMode('edit')}>Редактор</button>
        <button role="tab" aria-selected={mode === 'preview'} onClick={() => setMode('preview')}>Предпросмотр</button>
      </div>
      {active && mode === 'edit' && <button className="formula-button" title="Обернуть выделение в LaTeX" onMouseDown={event=>event.preventDefault()} onClick={()=>field.current?.formula()}>∑ Формула</button>}
    </div>
    {mode === 'edit' ? <MathEditor ref={field} value={draft} onChange={onChange} readOnly={!active}/> : <div className="draft-preview">{draft ? <MathText text={draft}/> : <p>Здесь появится текст решения с формулами.</p>}</div>}
    <div className="editor-footnote"><span>Markdown · LaTeX: <code>$x^2$</code></span>{active && <button onClick={onSave}>Сохранить <kbd>⌘ / Ctrl S</kbd></button>}</div>
  </section>;
}

export function Workspace({attempt, draft, saveState, active, seconds, busy, panel, readerLocation, pending, outcomes, reflection, question, restore,
  onDraft, onSave, onPause, onHelp, onCloseMaterial, onFinish, onAbandon, onToday, onOutcome, onReflection, onQuestion,
  onAddQuestion, onResolve, onApprove, onRestore, onKeepServer}: Obj) {
  const [editorMode, setEditorMode] = useState('edit');
  const [finishing, setFinishing] = useState(false);
  const [confirmSolution, setConfirmSolution] = useState(false);
  const returnScroll = useRef(0);
  const helped = attempt.help?.some((item: Obj) => item.mathematical && !item.retracted);
  const materials=attempt.problem.materials||{core:!!attempt.problem.topic_id,theory:!!attempt.problem.topic_id};
  const hasMaterial=materials.core||materials.theory;
  const sectionNames:Record<string,string>={probability:'Вероятности',calculus:'Матанализ',linalg:'Линейная алгебра',ode:'Дифференциальные уравнения'};
  const completion = useRef<HTMLDivElement>(null);
  const resources = useRef<HTMLElement>(null);
  const solutionDialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {setFinishing(false); setEditorMode('edit');}, [attempt.id]);
  useEffect(() => {
    if (!active) return;
    function shortcut(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's') {event.preventDefault(); onSave();}
    }
    window.addEventListener('keydown', shortcut);
    return () => window.removeEventListener('keydown', shortcut);
  }, [active, onSave]);
  useEffect(() => {
    if (confirmSolution) solutionDialog.current?.showModal();
    else solutionDialog.current?.close();
  }, [confirmSolution]);

  function openHelp(kind: string) {returnScroll.current = window.scrollY; onHelp(kind); window.scrollTo({top: 0});}
  function closeMaterial() {onCloseMaterial(); requestAnimationFrame(() => window.scrollTo({top: returnScroll.current}));}
  const editor = <DraftEditor draft={draft} onChange={onDraft} saveState={saveState} active={active} onSave={onSave} mode={editorMode} setMode={setEditorMode}/>;

  if (panel) return <TheoryReader material={panel} {...readerLocation} editor={editor} onClose={closeMaterial} assistance={active && helped}/>;

  return <div className="study-workspace">
    <div className="workspace-heading">
      <div><button className="back-button" onClick={onToday}>← К плану</button><div className="workspace-meta"><span>{attempt.problem.id}</span><span>{sectionNames[attempt.problem.section]||attempt.problem.section}</span><span>{attempt.problem.primary_skill_id} · Уровень {attempt.problem.level}</span></div><h1><MathText text={attempt.problem.title} inline/></h1></div>
      <div className="timer"><span>{String(Math.floor(seconds / 60)).padStart(2, '0')}:{String(seconds % 60).padStart(2, '0')}</span>{active && <button aria-label={attempt.state === 'running' ? 'Пауза' : 'Продолжить таймер'} onClick={onPause}>{attempt.state === 'running' ? 'Ⅱ' : '▶'}</button>}<small>{attempt.state === 'completed' ? 'Завершена' : attempt.state === 'paused' ? 'На паузе' : 'Время попытки'}</small></div>
    </div>
    {attempt.unconfirmed_seconds > 1 && <div className="alert">После перерыва {Math.round(attempt.unconfirmed_seconds)} с остались неподтверждёнными и не включены во время.</div>}
    {restore && <div className="alert">Есть локальный черновик, который отличается от серверного.<button onClick={onRestore}>Восстановить в редактор</button><button onClick={onKeepServer}>Оставить серверную запись</button></div>}
    <div className="workspace-grid">
      <div className="problem-column">
        <section className="statement problem-paper"><div className="paper-heading"><h2>Условие</h2><span>EN</span></div><MathText text={attempt.problem.statement}/>{attempt.problem.provenance?.kind==='obsidian_vault'&&<p className="source-file">Из Obsidian · {attempt.problem.provenance.source_file}</p>}</section>
        <section ref={resources} className="study-resources" aria-label="Помощь и материалы">
          <div className="resource-heading"><h2>Помощь и материалы</h2>{helped && <span className="help-badge">Помощь использована</span>}</div>
          <p>При затруднении можно открыть подсказку или нужный раздел теории.</p>
          <div className="hint-buttons">{[['h1', '1'], ['h2', '2'], ['h3', '3']].map(([kind, number]) => <button key={kind} disabled={busy} onClick={() => openHelp(kind)}><span>Подсказка</span><b>{number}</b></button>)}</div>
          <div className="resource-links">{hasMaterial?<button disabled={busy} onClick={() => openHelp(materials.core?'core':'theory')}><span>Конспект темы<small>Из исходного Obsidian-vault{materials.widget?' · есть лаборатория':''}</small></span><span>↗</span></button>:<p className="missing-material">Для этого типа в исходном vault нет конспекта. Ссылки на справочники сохранены в третьей подсказке.</p>}<button disabled={busy} onClick={() => openHelp('tutoring')}><span>Внешний агент<small>Разбор сохранённого решения</small></span><span>↗</span></button></div>
          <details className="solution-disclosure"><summary>Разбор решения</summary><p>Открытие готового решения будет отмечено как помощь.</p><button disabled={busy} onClick={() => setConfirmSolution(true)}>Открыть решение</button></details>
          <p className="resource-note">Подсказки и чтение теории учитываются при оценке самостоятельности.</p>
        </section>
      </div>
      <div className="solution-column">
        <div className="mobile-resource-shortcuts">{hasMaterial&&<button disabled={busy} onClick={() => openHelp(materials.core?'core':'theory')}>Конспект темы ↗</button>}<button onClick={() => resources.current?.scrollIntoView({behavior:'smooth',block:'start'})}>Подсказки ↓</button></div>
        {editor}
        {active && !finishing && <div className="attempt-actions"><span>{helped ? 'Результат будет отмечен с учётом помощи' : 'Закончите решение и оцените результат'}</span><button className="primary" disabled={busy} onClick={() => {setFinishing(true); requestAnimationFrame(() => completion.current?.scrollIntoView({behavior: 'smooth', block: 'center'}));}}>К результату →</button></div>}
        {active && finishing && <div ref={completion} className="card completion"><div className="section-heading"><h2>Результат попытки</h2><button className="text-button" onClick={() => setFinishing(false)}>Вернуться к решению</button></div>{helped && <p className="completion-note">Вы открывали математическую помощь. Вариант «Самостоятельно» для этой попытки недоступен.</p>}{attempt.problem.parts.map((part: Obj) => <ChoiceButtons key={part.id} label={<MathText text={part.title} inline/>} value={outcomes[part.id] || (helped ? 'assisted' : 'independent')} onChange={value=>onOutcome(part.id,value)} options={Object.entries(labels).map(([value,label])=>({value,label,disabled:value==='independent'&&helped}))}/>)}<label>Что стоит запомнить?<input value={reflection} onChange={event => onReflection(event.target.value)} placeholder="Метод, первый шаг или причина ошибки"/></label><button className="primary" disabled={busy} onClick={onFinish}>Завершить попытку</button></div>}
        {attempt.state === 'completed' && <section className="card success"><h2>Попытка сохранена</h2><p>{attempt.part_outcomes.map((part: Obj) => labels[part.outcome]).join(' · ')}</p><p>{pending ? 'Повторения пересчитываются.' : 'Результат учтён в расчёте повторений.'}</p><button onClick={onToday}>Вернуться к плану</button></section>}
        {active && <details className="abandon"><summary>Прервать попытку</summary><p>Черновик сохранится. Результат не попадёт в оценку навыка.</p><button disabled={busy} onClick={onAbandon}>Прервать без оценки</button></details>}
      </div>
    </div>
    <details className="discussion" open={attempt.state === 'completed' ? true : undefined}><summary><span>Вопросы и разбор</span><small>{attempt.questions?.length || 0} вопросов · {attempt.reviews?.length || 0} комментариев</small></summary><div className="discussion-body">
      <div className="question-compose"><h2>Вопрос к этой попытке</h2><label>Что осталось непонятно?<textarea aria-label="Вопрос по попытке" value={question} onChange={event => onQuestion(event.target.value)} placeholder="Укажите шаг или утверждение, которое хотите разобрать"/></label><button disabled={busy || !question.trim()} onClick={onAddQuestion}>Сохранить вопрос</button></div>
      <div className="discussion-history">{attempt.questions?.map((item: Obj) => <div key={item.id} className="question"><MathText text={item.text}/><small>{item.status === 'resolved' ? 'Закрыт' : 'Открыт'}</small>{item.status !== 'resolved' && <button onClick={() => onResolve(item)}>Понял, закрыть вопрос</button>}</div>)}{attempt.reviews?.map((review: Obj) => <article className="review" key={review.id}><small>{review.actor} · редакция {review.attempt_revision}{review.stale ? ' · относится к прошлой редакции' : ''}</small><MathText text={review.text}/></article>)}{attempt.proposals?.filter((proposal: Obj) => proposal.status === 'pending').map((proposal: Obj) => <div className="proposal" key={proposal.id}><strong>Предложение: {labels[proposal.outcome]}</strong><MathText text={proposal.reason}/><button disabled={busy} onClick={() => onApprove(proposal.id)}>Подтвердить исправление</button></div>)}</div>
    </div></details>
    <dialog ref={solutionDialog} aria-labelledby="solution-title" className="confirm-dialog" onCancel={() => setConfirmSolution(false)} onClick={event => {if(event.target === event.currentTarget)setConfirmSolution(false);}}><h2 id="solution-title">Открыть готовое решение?</h2><p>Для активной попытки это будет отмечено как математическая помощь. Самостоятельный результат после этого выбрать нельзя.</p><div><button autoFocus onClick={() => setConfirmSolution(false)}>Вернуться к задаче</button><button className="primary" onClick={() => {setConfirmSolution(false); openHelp('solution');}}>Открыть</button></div></dialog>
  </div>;
}
