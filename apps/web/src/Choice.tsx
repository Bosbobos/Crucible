import {useId} from 'react';
import type {ReactNode, KeyboardEvent} from 'react';

export type ChoiceOption={value:string;label:ReactNode;disabled?:boolean};

export function ChoiceButtons({label,value,options,onChange,className=''}:{label:ReactNode;value:string;options:ChoiceOption[];onChange:(value:string)=>void;className?:string}){
  const id=useId();
  function keyboard(event:KeyboardEvent,index:number){
    const direction=['ArrowRight','ArrowDown'].includes(event.key)?1:['ArrowLeft','ArrowUp'].includes(event.key)?-1:0;
    if(!direction)return;
    event.preventDefault();
    for(let i=1;i<=options.length;i++){const next=(index+direction*i+options.length)%options.length;if(!options[next].disabled){onChange(options[next].value);document.getElementById(id+'-'+next)?.focus();break;}}
  }
  return <fieldset className={'choice-buttons '+className}><legend>{label}</legend><div role="radiogroup" aria-labelledby={id+'-label'}><span id={id+'-label'} className="sr-only">{label}</span>{options.map((option,index)=><button id={id+'-'+index} key={option.value} type="button" role="radio" aria-checked={option.value===value} tabIndex={option.value===value||(!options.some(item=>item.value===value)&&index===0)?0:-1} disabled={option.disabled} onKeyDown={event=>keyboard(event,index)} onClick={()=>onChange(option.value)}>{option.label}</button>)}</div></fieldset>;
}
