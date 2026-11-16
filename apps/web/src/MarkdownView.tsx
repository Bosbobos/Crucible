import Markdown, {defaultUrlTransform} from 'react-markdown';
import type {Components} from 'react-markdown';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import {Children, cloneElement, isValidElement, useContext, useMemo, useRef} from 'react';
import type {ReactNode, ReactElement} from 'react';
import {StudyNavigation} from './StudyNavigation';
import {VaultExercise} from './VaultExercises';

function Callout({children}:{children:ReactNode}){
  const nodes=Children.toArray(children),index=nodes.findIndex(child=>isValidElement(child));
  const first=nodes[index] as ReactElement<{children:ReactNode}>|undefined;
  if(!first)return <blockquote>{children}</blockquote>;
  const contents=Children.toArray(first.props.children),start=String(contents[0]||'');
  const marker=start.match(/^\[!([\w-]+)\]([+-]?)\s*([^\n]*)\n?/);
  if(!marker)return <blockquote>{children}</blockquote>;
  const rest=start.slice(marker[0].length);
  const body=[...nodes];body[index]=cloneElement(first,{},rest,...contents.slice(1));
  const title=marker[3]||marker[1];
  // Вопросы — содержимое страницы; отдельно скрываются только вложенные ответы.
  const collapsible=marker[2]&&marker[1].toLowerCase()!=='quiz';
  return collapsible?<details className={'source-callout '+marker[1]} open={marker[2]==='+'}><summary>{title}</summary>{body}</details>:<aside className={'source-callout '+marker[1]}><strong>{title}</strong>{body}</aside>;
}

function SourceFlow({text}:{text:string}){
  const nodes=new Map([...text.matchAll(/([A-Za-z]\w*)[\[{]"([^"]+)"[\]}]/g)].map(match=>[match[1],match[2].replace(/<br\s*\/?\s*>/g,'\n')]));
  const edges=text.split('\n').filter(line=>line.includes('-->')).map(line=>{const [left,right]=line.split('-->');return {from:left.match(/^\s*(\w+)/)?.[1]||'',to:right.replace(/^\s*\|[^|]*\|/,'').match(/^\s*(\w+)/)?.[1]||'',label:right.match(/\|([^|]+)\|/)?.[1]||'→'};});
  return <div className="source-flow" aria-label="Схема выбора типа уравнения">{[...nodes].filter(([id])=>edges.some(edge=>edge.from===id)).map(([id,label])=><section key={id}><strong>{label}</strong><ul>{edges.filter(edge=>edge.from===id).map((edge,i)=><li key={i}><b>{edge.label}</b> {nodes.get(edge.to)}</li>)}</ul></section>)}</div>;
}

function plainText(value: ReactNode): string {
  if (typeof value === 'string' || typeof value === 'number') return String(value);
  if (Array.isArray(value)) return value.map(plainText).join('');
  if (value && typeof value === 'object' && 'props' in value) return plainText((value.props as {children?: ReactNode}).children);
  return '';
}

export function headingId(text: string) {
  return 'theory-' + text.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, '-').replace(/^-|-$/g, '');
}

export function MathText({text, anchors = false, inline = false}: {text: string; anchors?: boolean; inline?:boolean}) {
  const navigation=useContext(StudyNavigation);
  const navigationRef=useRef(navigation);
  navigationRef.current=navigation;
  // Stable renderer types preserve open callouts and exercise input during timer updates.
  const components=useMemo<Components>(()=>({
      ...(inline?{p:({children})=><span>{children}</span>}:{}),
      table:({children})=><div className="table-scroll" role="region" aria-label="Таблица конспекта" tabIndex={0}><table>{children}</table></div>,
      blockquote:({children})=><Callout>{children}</Callout>,
      a:({href,children})=>{
        if(href?.startsWith('study-material:'))return <a href="#" onClick={event=>{event.preventDefault();const [id,anchor]=href.slice(15).split('#');navigationRef.current.material(id,anchor);}}>{children}</a>;
        if(href?.startsWith('study-problem:'))return <a href="#" onClick={event=>{event.preventDefault();navigationRef.current.problem(href.slice(14));}}>{children}</a>;
        if(href?.startsWith('study-lab:'))return <a href="#" onClick={event=>{event.preventDefault();navigationRef.current.lab();}}>{children}</a>;
        return <a href={href} rel="noreferrer">{children}</a>;
      },
      pre:({children})=>{
        const code=Children.toArray(children).find(isValidElement) as ReactElement<{className?:string;children?:ReactNode}>|undefined;
        const language=code?.props.className,raw=plainText(code?.props.children);
        if(language==='language-vault-exercise'){try{return <VaultExercise key={raw} data={JSON.parse(raw)}/>;}catch{return <p>Не удалось прочитать блок конспекта.</p>;}}
        if(language==='language-vault-anchor')return <span id={'theory-block-'+raw.trim()} aria-hidden="true"/>;
        if(language==='language-mermaid')return <SourceFlow text={raw}/>;
        return <pre>{children}</pre>;
      },
      ...(anchors ? {
      h2: ({children}) => <h2 id={headingId(plainText(children))}>{children}</h2>,
      h3: ({children}) => <h3 id={headingId(plainText(children))}>{children}</h3>,
    } : {}),
    }),[anchors,inline]);
  const rendered=useMemo(()=><Markdown
    remarkPlugins={[remarkMath,remarkGfm]}
    rehypePlugins={[[rehypeKatex, {trust: false, throwOnError: false}]]}
    skipHtml
    urlTransform={url=>/^study-(material|problem|lab):/.test(url)?url:defaultUrlTransform(url)}
    components={components}
  >{text}</Markdown>,[text,components]);
  return inline?<span className="inline-markdown">{rendered}</span>:<div className="markdown">{rendered}</div>;
}
