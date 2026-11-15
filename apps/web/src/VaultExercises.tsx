import {useState} from 'react';
import {MathText} from './MarkdownView';
import {ChoiceButtons} from './Choice';

type Data=Record<string,any>;

// A small arithmetic grammar, not JavaScript evaluation.
export function arithmetic(raw:string):number {
  const input=raw.replace(/,/g,'.').replace(/\s+/g,'');let at=0;
  if(input.length>100)return NaN;
  function atom():number {if(input[at]==='-'){at++;return -atom();}if(input[at]==='+'){at++;return atom();}if(input.startsWith('sqrt(',at)){at+=5;const x=add();if(input[at++]!==')')throw Error();return Math.sqrt(x);}if(input.startsWith('pi',at)){at+=2;return Math.PI;}if(input[at]==='('){at++;const x=add();if(input[at++]!==')')throw Error();return x;}const match=input.slice(at).match(/^(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?/);if(!match)throw Error();at+=match[0].length;return Number(match[0]);}
  function power():number {const x=atom();if(input[at]==='^'){at++;return x**power();}return x;}
  function multiply():number {let x=power();while(input[at]==='*'||input[at]==='/'){const op=input[at++],y=power();x=op==='*'?x*y:x/y;}return x;}
  function add():number {let x=multiply();while(input[at]==='+'||input[at]==='-'){const op=input[at++],y=multiply();x=op==='+'?x+y:x-y;}return x;}
  try{const value=add();return at===input.length&&Number.isFinite(value)?value:NaN;}catch{return NaN;}
}

function Ask({data}:{data:Data}) {
  const [answer,setAnswer]=useState(''),[picked,setPicked]=useState(-1),[result,setResult]=useState<boolean|null>(null),[reveal,setReveal]=useState(false);
  function check(){const actual=arithmetic(answer),expected=arithmetic(String(data.ans));const ok=data.choices?(Array.isArray(data.ans)?data.ans.includes(picked):picked===data.ans):Number.isFinite(actual)&&Math.abs(actual-expected)<=1e-6+1e-3*Math.abs(expected);setResult(ok);setReveal(ok);}
  return <section className="vault-exercise" aria-label={data.id}><span className="eyebrow">{data.tag||'Самопроверка из конспекта'}</span><MathText text={data.q}/>{data.choices?<div className="exercise-choices">{data.choices.map((choice:string,i:number)=><button key={i} aria-pressed={picked===i} onClick={()=>setPicked(i)}><MathText text={choice}/></button>)}</div>:<label>Ответ<input value={answer} onChange={event=>setAnswer(event.target.value)} placeholder="Число или дробь" onKeyDown={event=>{if(event.key==='Enter')check();}}/></label>}<div className="exercise-actions"><button onClick={check} disabled={data.choices?picked<0:!answer.trim()}>Проверить</button>{result===false&&<button onClick={()=>setReveal(true)}>Показать ответ</button>}</div>{result!==null&&<p className={result?'exercise-ok':'exercise-wrong'} role="status">{result?'Верно.':'Ответ отличается от указанного в исходном конспекте. Можно попробовать ещё раз.'}</p>}{reveal&&<div className="exercise-answer"><MathText text={'**Ответ:** '+(data.choices?data.choices[Array.isArray(data.ans)?data.ans[0]:data.ans]:(data.show||String(data.ans)))+'\n\n'+(data.explain||'')}/></div>}</section>;
}

function TryRecall({data}:{data:Data}) {
  const key='crucible-vault-try:'+data.primer+':'+(data.from||data.id);
  const [text,setText]=useState(()=>localStorage.getItem(key)||''),[reveal,setReveal]=useState(false);
  return <section className="vault-exercise"><label>{data.kind==='try'?'Моя попытка':'Мой ход при первом чтении'}<textarea value={text} readOnly={data.kind==='recall'} onChange={event=>{setText(event.target.value);localStorage.setItem(key,event.target.value);}} placeholder="Запишите рассуждение. Текст сохраняется в этом браузере."/></label>{data.explain&&<><button onClick={()=>setReveal(!reveal)}>{reveal?'Скрыть разбор':'Сравнить с разбором'}</button>{reveal&&<MathText text={data.explain}/>}</>}<small>Локальная самопроверка; оценку навыка не меняет.</small></section>;
}

function Moves({data}:{data:Data}) {
  const [answers,setAnswers]=useState<Record<number,number>>({}),[show,setShow]=useState(false);
  return <section className="vault-exercise"><h3>Какой ход?</h3>{data.items.map((item:Data,i:number)=><div className="move-question" key={i}><MathText text={item.t}/><ChoiceButtons label="Приём" className="move-choices" value={String(answers[i]??-1)} onChange={value=>setAnswers({...answers,[i]:Number(value)})} options={data.options.map((option:string,j:number)=>({value:String(j),label:<MathText text={option} inline/>}))}/>{show&&<><p className={answers[i]===item.ans?'exercise-ok':'exercise-wrong'}>{answers[i]===item.ans?'Верно.':'В исходном конспекте: '+data.options[item.ans]}</p><MathText text={item.why}/></>}</div>)}<button disabled={Object.keys(answers).length!==data.items.length||Object.values(answers).some(value=>value<0)} onClick={()=>setShow(true)}>Проверить приёмы</button></section>;
}

export function VaultExercise({data}:{data:Data}) {
  if(data.kind==='ask')return <Ask data={data}/>;
  if(data.kind==='try'||data.kind==='recall')return <TryRecall data={data}/>;
  if(data.kind==='moves')return <Moves data={data}/>;
  return <p>Блок не поддерживается.</p>;
}
