import {useContext, useEffect, useMemo, useRef, useState} from 'react';
import type {CSSProperties, ReactNode} from 'react';
import {MathText, headingId} from './MarkdownView';
import {VaultLab} from './VaultLab';
import {StudyNavigation} from './StudyNavigation';

type Material={kind?:string;title?:string;text:string;widget?:string;anchor?:string;provenance?:Record<string,any>};
type Chapter={title:string;text:string};
function chaptersOf(body:string):Chapter[]{
  const chapters:Chapter[]=[];let title='Введение',lines:string[]=[],fence='';
  for(const line of body.split('\n')){
    const marker=line.match(/^\s*(`{3,}|~{3,})/);
    if(marker){if(!fence)fence=marker[1][0];else if(marker[1][0]===fence)fence='';}
    const heading=!fence&&line.match(/^## (.+)$/);
    if(heading){if(lines.join('\n').trim())chapters.push({title,text:lines.join('\n').trim()});title=heading[1];lines=[];}
    lines.push(line);
  }
  if(lines.join('\n').trim())chapters.push({title,text:lines.join('\n').trim()});
  return chapters.length?chapters:[{title:'Материал',text:body}];
}
export function TheoryReader({material,onClose,editor,assistance=false,closeLabel='Вернуться к задаче'}:{material:Material;onClose:()=>void;editor?:ReactNode;assistance?:boolean;closeLabel?:string}){
  const navigation=useContext(StudyNavigation),toolbar=useRef<HTMLElement>(null),textPosition=useRef(0);
  const [fontSize,setFontSize]=useState(19),[alongside,setAlongside]=useState(false),[contentsOpen,setContentsOpen]=useState(false),[lab,setLab]=useState(false);
  const [wideScreen,setWideScreen]=useState(()=>window.matchMedia('(min-width: 1120px)').matches);
  const [reading,setReading]=useState({text:material.text,index:0,seen:[0]});
  const title=material.text.match(/^# (.+)$/m)?.[1]||material.title||'Материал';
  const body=material.text.replace(/^# .+\n?/,'').trim(),chapters=useMemo(()=>chaptersOf(body),[body]);
  const index=reading.text===material.text?Math.min(reading.index,chapters.length-1):0;
  const seen=reading.text===material.text?reading.seen:[0],contentsInRail=wideScreen&&!alongside;
  useEffect(()=>{const query=window.matchMedia('(min-width: 1120px)');const change=()=>setWideScreen(query.matches);query.addEventListener('change',change);return()=>query.removeEventListener('change',change);},[]);
  useEffect(()=>{
    const anchor=material.anchor?.replace(/^\^/,'');
    const target=anchor?chapters.findIndex(chapter=>chapter.text.includes('```vault-anchor\n'+anchor+'\n```')||headingId(chapter.title)===headingId(anchor)):0;
    const next=Math.max(0,target);setReading({text:material.text,index:next,seen:[next]});setLab(false);setContentsOpen(false);
    requestAnimationFrame(()=>{
      const block=anchor&&document.getElementById('theory-block-'+anchor);
      window.scrollTo({top:block?Math.max(0,window.scrollY+block.getBoundingClientRect().top-(toolbar.current?.offsetHeight||80)-24):0,behavior:'instant'});
    });
  },[material.text,material.anchor]);
  function visit(next:number){setReading(current=>({text:material.text,index:next,seen:[...new Set([...(current.text===material.text?current.seen:[]),next])]}));setLab(false);setContentsOpen(false);requestAnimationFrame(()=>window.scrollTo({top:0,behavior:'instant'}));}
  function selectLab(next:boolean){if(next===lab)return;if(next)textPosition.current=window.scrollY;setLab(next);requestAnimationFrame(()=>window.scrollTo({top:next?0:textPosition.current,behavior:'instant'}));}
  return <StudyNavigation.Provider value={{...navigation,lab:()=>selectLab(true)}}><section className={'theory-view chapter-reader'+(alongside?' theory-with-draft':'')+(!contentsInRail?' theory-compact-contents':'')} aria-label="Чтение материала" style={{'--reading-size':fontSize+'px','--prose-measure':'78ch'} as CSSProperties}>
    <header className="reader-toolbar" ref={toolbar}><button className="back-button" onClick={onClose}>← {closeLabel}</button><div className="reader-actions">{editor&&<button aria-pressed={alongside} className={alongside?'selected-control':''} onClick={()=>setAlongside(!alongside)}>{alongside?'Скрыть черновик':'Черновик рядом'}</button>}<div className="text-size" aria-label="Размер текста"><button aria-label="Уменьшить текст" disabled={fontSize<=17} onClick={()=>setFontSize(fontSize-1)}>A−</button><button aria-label="Увеличить текст" disabled={fontSize>=23} onClick={()=>setFontSize(fontSize+1)}>A+</button></div></div></header>
    <div className="reader-layout"><aside className="reader-contents">
      {contentsInRail?<span className="eyebrow">В этом конспекте</span>:<button className="outline-toggle" aria-label="Содержание" aria-expanded={contentsOpen} aria-controls="reader-outline" onClick={()=>setContentsOpen(!contentsOpen)}>Содержание <span aria-hidden="true">{contentsOpen?'−':'+'}</span></button>}
      <div id="reader-outline" hidden={!contentsInRail&&!contentsOpen}><nav aria-label="Разделы теории">{chapters.map((chapter,i)=><button key={i} aria-label={chapter.title} className={i===index&&!lab?'current':''} aria-current={i===index&&!lab?'step':undefined} onClick={()=>visit(i)}><span className="chapter-number" aria-hidden="true">{String(i+1).padStart(2,'0')}</span><MathText text={chapter.title} inline/></button>)}</nav>{material.widget&&<button className={'lab-link'+(lab?' current':'')} onClick={()=>selectLab(true)}>Лаборатория <span>↗</span></button>}{assistance&&<p className="assistance-note">Чтение учтено как помощь в текущей попытке.</p>}</div>
    </aside><article className="reading-paper">
      <header className="reading-heading"><span className="eyebrow">{material.kind==='help'?'Помощь к задаче':material.provenance?.kind==='obsidian_vault'?'Конспект из Obsidian':'Теория'}</span><h1><MathText text={title} inline/></h1><div className="reader-location"><span>{lab?'Лаборатория':`Раздел ${index+1} из ${chapters.length}`}</span>{material.widget&&<div className="reader-tabs" role="tablist" aria-label="Содержание материала"><button role="tab" aria-selected={!lab} onClick={()=>selectLab(false)}>Конспект</button><button role="tab" aria-selected={lab} onClick={()=>selectLab(true)}>Лаборатория</button></div>}</div><progress className="chapter-progress" aria-label="Положение в конспекте" max={chapters.length} value={index+1}/></header>
      <div hidden={lab} className="theory-text">{chapters.map((chapter,i)=>seen.includes(i)&&<div key={material.text+':'+i} hidden={index!==i} className="reader-chapter" aria-label={chapter.title}>{!chapter.text.startsWith('## ')&&<h2 className="chapter-intro-title">{chapter.title}</h2>}<MathText text={chapter.text} anchors/></div>)}</div>
      {material.widget==='vault-indicators'&&<div hidden={!lab} className="theory-lab"><VaultLab/></div>}
      {!lab&&<nav className="chapter-navigation" aria-label="Переходы по конспекту"><button disabled={index===0} onClick={()=>visit(index-1)}>← Назад<span>{index>0?<MathText text={chapters[index-1].title} inline/>:'Начало конспекта'}</span></button><span>{index+1} / {chapters.length}</span><button disabled={index===chapters.length-1} onClick={()=>visit(index+1)}>Далее →<span>{index<chapters.length-1?<MathText text={chapters[index+1].title} inline/>:'Конец конспекта'}</span></button></nav>}
      {material.provenance?.source_file&&<p className="source-file">Источник: {material.provenance.source_file}</p>}
      <div className="reading-end"><button onClick={onClose}>← {closeLabel}</button></div>
    </article>{editor&&alongside&&<aside className="reader-draft" aria-label="Черновик рядом с теорией">{editor}</aside>}</div>
  </section></StudyNavigation.Provider>;
}
