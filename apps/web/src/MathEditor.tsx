import {forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState} from 'react';
import {Compartment, EditorSelection, EditorState, StateEffect, StateField} from '@codemirror/state';
import {EditorView, keymap, placeholder, highlightActiveLine} from '@codemirror/view';
import {defaultKeymap, history, historyKeymap, isolateHistory} from '@codemirror/commands';
import {closeBrackets, closeBracketsKeymap} from '@codemirror/autocomplete';
import {markdown} from '@codemirror/lang-markdown';
import {defaultHighlightStyle, syntaxHighlighting} from '@codemirror/language';
import katex from 'katex';

type Formula={source:string;display:boolean};
function escaped(text:string,at:number){let count=0;while(at>0&&text[--at]==='\\')count++;return count%2===1;}
export function formulaAt(text:string,cursor:number):Formula|null {
  for(let i=0;i<text.length;i++){
    if(text.startsWith('```',i)){const end=text.indexOf('```',i+3);if(end<0||cursor<=end+3)return null;i=end+2;continue;}
    if(text[i]==='`'&&!escaped(text,i)){const end=text.indexOf('`',i+1);if(end>=0){if(cursor>=i&&cursor<=end)return null;i=end;continue;}}
    if(escaped(text,i))continue;
    const token=text.startsWith('$$',i)?'$$':text[i]==='$'?'$':text.startsWith('\\(',i)?'\\(':text.startsWith('\\[',i)?'\\[':'';
    if(!token)continue;
    const closer=token==='\\('? '\\)':token==='\\['?'\\]':token,display=token==='$$'||token==='\\[';
    let end=i+token.length;
    while(end<text.length&&!(text.startsWith(closer,end)&&!escaped(text,end))&&(display||text[end]!=='\n'))end++;
    if(cursor>=i+token.length&&cursor<=end)return {source:text.slice(i+token.length,end),display};
    i=end+(text.startsWith(closer,end)?closer.length:0)-1;
  }
  return null;
}

const insertedPair=StateEffect.define<{at:number;mark:string}>();
const freshPair=StateField.define<{at:number;mark:string}|null>({create:()=>null,update(value,transaction){let next=transaction.docChanged||transaction.selection?null:value;for(const effect of transaction.effects)if(effect.is(insertedPair))next=effect.value;return next;}});
const pairedMarks=EditorView.inputHandler.of((view,from,to,text)=>{
  if(view.state.readOnly||view.composing||!['$','*','_','`'].includes(text))return false;
  const doc=view.state.doc.toString();
  if(escaped(doc,from)||(text!=='$'&&formulaAt(doc,from)))return false;
  const selected=doc.slice(from,to);
  if(selected){view.dispatch({changes:{from,to,insert:text+selected+text},selection:EditorSelection.range(from+1,to+1),userEvent:'input.type'});return true;}
  const before=doc.slice(from-1,from),after=doc.slice(from,from+1);
  const fresh=view.state.field(freshPair);
  if(text!=='`'&&fresh?.at===from&&fresh.mark===text&&before===text&&after===text){view.dispatch({changes:{from:from-1,to:from+1,insert:text.repeat(4)},selection:{anchor:from+1},userEvent:'input.type'});return true;}
  if(after===text){view.dispatch({selection:{anchor:from+1},userEvent:'select'});return true;}
  // Stars and underscores inside words are literal; math and code can start anywhere.
  if(text!=='$'&&text!=='`'&&/[\p{L}\p{N}]/u.test(before))return false;
  view.dispatch({changes:{from,to,insert:text+text},selection:{anchor:from+1},effects:insertedPair.of({at:from+1,mark:text}),userEvent:'input.type'});return true;
});

export type MathEditorHandle={formula:()=>void};
export const MathEditor=forwardRef<MathEditorHandle,{value:string;onChange:(text:string)=>void;readOnly:boolean}>(function MathEditor({value,onChange,readOnly},ref){
  const host=useRef<HTMLDivElement>(null),view=useRef<EditorView|null>(null),callback=useRef(onChange),editable=useRef(new Compartment());
  const [formula,setFormula]=useState<Formula|null>(null);
  callback.current=onChange;
  useEffect(()=>{
    if(!host.current)return;
    const editor=new EditorView({parent:host.current,state:EditorState.create({doc:value,extensions:[
      editable.current.of([EditorState.readOnly.of(readOnly),EditorView.editable.of(!readOnly)]),
      EditorState.languageData.of(()=>[{closeBrackets:{brackets:['(','[','{','"',"'"],before:')]}:;>$*_`'}}]),
      history(),markdown(),syntaxHighlighting(defaultHighlightStyle),EditorView.lineWrapping,highlightActiveLine(),freshPair,pairedMarks,closeBrackets(),
      keymap.of([{key:'Backspace',run:editor=>{
        const {from,to,empty}=editor.state.selection.main;if(!empty||editor.state.readOnly)return false;
        const text=editor.state.doc.toString();
        for(const [open,close] of [['$','$'],['*','*'],['_','_'],['`','`'],['(',')'],['[',']'],['{','}'],['"','"'],["'","'"]]){const count=open===close&&text.slice(from-2,from+2)===open.repeat(4)?2:text[from-1]===open&&text[from]===close?1:0;
          if(count){editor.dispatch({changes:{from:from-count,to:to+count,insert:''},selection:{anchor:from-count},annotations:isolateHistory.of('full'),userEvent:'delete.backward'});return true;}}
        return false;
      }},{key:'Tab',run:editor=>{const pos=editor.state.selection.main.head,next=editor.state.doc.sliceString(pos,pos+1);if(!editor.state.selection.main.empty||!next||!')]}$*_`'.includes(next))return false;editor.dispatch({selection:{anchor:pos+1}});return true;}},...closeBracketsKeymap,...defaultKeymap,...historyKeymap]),
      placeholder('Запишите идею, промежуточные вычисления или решение…'),
      EditorView.contentAttributes.of({'aria-label':'Черновик решения','aria-multiline':'true','spellcheck':'false'}),
      EditorView.updateListener.of(update=>{
        if(update.docChanged)callback.current(update.state.doc.toString());
        if(update.docChanged||update.selectionSet||update.focusChanged)setFormula(update.view.hasFocus?formulaAt(update.state.doc.toString(),update.state.selection.main.head):null);
      }),
    ]})});view.current=editor;
    return()=>{editor.destroy();view.current=null;};
  },[]);
  useEffect(()=>{const editor=view.current;if(editor&&editor.state.doc.toString()!==value)editor.dispatch({changes:{from:0,to:editor.state.doc.length,insert:value}});},[value]);
  useEffect(()=>{view.current?.dispatch({effects:editable.current.reconfigure([EditorState.readOnly.of(readOnly),EditorView.editable.of(!readOnly)])});},[readOnly]);
  useImperativeHandle(ref,()=>({formula(){const editor=view.current;if(!editor||editor.state.readOnly)return;const {from,to}=editor.state.selection.main;const selected=editor.state.sliceDoc(from,to);editor.dispatch({changes:{from,to,insert:'$'+selected+'$'},selection:EditorSelection.range(from+1,to+1),userEvent:'input.type'});editor.focus();}}),[]);
  const rendered=useMemo(()=>{if(!formula?.source.trim())return null;try{return katex.renderToString(formula.source,{displayMode:formula.display,throwOnError:true,trust:false,strict:'ignore'});}catch{return null;}},[formula?.source,formula?.display]);
  return <div className="math-editor"><div ref={host} className="cm-host"/><div className={'formula-peek'+(formula?' formula-active':'')} role="region" aria-label="Предпросмотр формулы"><span className="formula-peek-label">{formula?'Формула под курсором':'Формулы во время ввода'}</span>{rendered?<div className="formula-render" dangerouslySetInnerHTML={{__html:rendered}}/>:<p>{formula?.source.trim()?'Допишите выражение — предпросмотр обновится.':'Начните формулу с $. Парные символы добавляются автоматически.'}</p>}</div></div>;
});
