import {useEffect,useRef,useState} from 'react';
import {Emblem} from './Emblem';
type Obj=Record<string,any>;
export const slotLabels:Record<string,string>={chest:'Нагрудник',shoulders:'Наплечники',bracers:'Наручи',legs:'Нижняя экипировка',sword:'Меч',shield:'Щит',cloak:'Мантия',back_ornament:'Задний орнамент',insignia:'Инсигния'};

export async function decoded(path:string):Promise<HTMLImageElement>{
 if(!path.startsWith('/character/')||path.includes('..'))throw new Error('Недоверенный asset path');
 const img=new Image();img.src=path;await img.decode();return img;
}

export async function composeCharacter(canvas:HTMLCanvasElement,manifest:Obj,slots:Obj,items:Obj[],current:()=>boolean){
 const width=1024,height=1536;
 if(manifest.base?.status!=='runtime_ready')throw new Error('База проходит подготовку');
 const base=await decoded(manifest.base.path);
 const candidates=await Promise.all(Object.entries(slots).map(async([slot,id])=>{
  if(!id)return null;
  const item=items.find(i=>i.id===id),part=manifest.assets[item?.asset_id]?.parts[item?.render_part];
  if(!part||part.status!=='runtime_ready'||part.rig_id!==manifest.rig_id)return {slot,id,missing:true};
  try{
   const image=await decoded(part.path),hide=part.hide_base_path?await decoded(part.hide_base_path):null;
   const regions=await Promise.all((part.allowed_base_regions||[]).map(async(name:string)=>decoded(manifest.base.region_masks[name])));
   if(hide&&!regions.length)throw new Error('Нет допустимых анатомических областей');
   const dependencies=await Promise.all((part.dependencies||[]).map(async(d:Obj)=>({...d,image:await decoded(d.path)})));
   const handRegion=dependencies.some((d:Obj)=>d.pass==='hide_neutral_hand')?await decoded(manifest.base.region_masks.hand_right_neutral):null;
   return {slot,id,part,image,hide,regions,handRegion,dependencies,missing:false};
  }catch{return {slot,id,missing:true};}
 }));
 if(!current())return null;
 const ready=candidates.filter((p):p is NonNullable<typeof p>=>!!p&&!p.missing);
 const scratch=document.createElement('canvas');scratch.width=width;scratch.height=height;
 const sc=scratch.getContext('2d',{willReadFrequently:true})!;
 const union=new Uint8ClampedArray(width*height);
 for(const p of ready){
  const allowed=new Uint8ClampedArray(width*height);
  for(const region of p.regions||[]){sc.clearRect(0,0,width,height);sc.drawImage(region,0,0,width,height);const values=sc.getImageData(0,0,width,height).data;for(let i=0;i<allowed.length;i++)allowed[i]=Math.max(allowed[i],values[i*4]);}
  for(const hide of [p.hide].filter(Boolean)){
   sc.clearRect(0,0,width,height);sc.drawImage(hide!,0,0,width,height);const data=sc.getImageData(0,0,width,height).data;
   for(let i=0;i<union.length;i++)union[i]=Math.max(union[i],Math.round(data[i*4]*data[i*4+3]*allowed[i]/(255*255)));
  }
  for(const d of (p.dependencies||[]).filter((d:Obj)=>d.pass==='hide_neutral_hand')){
   const region=p.handRegion!;
   sc.clearRect(0,0,width,height);sc.drawImage(region,0,0,width,height);const r=sc.getImageData(0,0,width,height).data;
   sc.clearRect(0,0,width,height);sc.drawImage(d.image,0,0,width,height);const h=sc.getImageData(0,0,width,height).data;
   for(let i=0;i<union.length;i++)union[i]=Math.max(union[i],Math.round(h[i*4]*r[i*4]/255));
  }
 }
 sc.clearRect(0,0,width,height);sc.drawImage(base,0,0,width,height);
 const body=sc.getImageData(0,0,width,height);
 for(let i=0;i<union.length;i++)body.data[i*4+3]=Math.round(body.data[i*4+3]*(1-union[i]/255));
 sc.putImageData(body,0,0);
 const frame=document.createElement('canvas');frame.width=width;frame.height=height;const ctx=frame.getContext('2d')!;
 const draw=(slot:string)=>{const p=ready.find(p=>p.slot===slot);if(p?.image)ctx.drawImage(p.image,0,0,width,height);};
 const grip=(pass:string)=>{for(const p of ready)for(const d of p.dependencies||[])if(d.pass===pass)ctx.drawImage(d.image,0,0,width,height);};
 draw('back_ornament');draw('cloak');ctx.drawImage(scratch,0,0);grip('grip_back');
 for(const slot of ['chest','legs','shoulders','bracers','insignia','sword'])draw(slot);
 grip('grip_front');draw('shield');
 if(!current())return null;
 canvas.width=width;canvas.height=height;canvas.getContext('2d')!.drawImage(frame,0,0);
 return {rendered:ready.map(p=>p.id),missing:candidates.filter(p=>p?.missing).map(p=>p!.id)};
}

export function CharacterScene({slots,items,compact=false,preview=false,manifestOverride}:{slots:Obj;items:Obj[];compact?:boolean;preview?:boolean;manifestOverride?:Obj}){
 const canvas=useRef<HTMLCanvasElement>(null),generation=useRef(0);
 const [state,setState]=useState<Obj>({loading:true});
 const key=JSON.stringify(slots);
 useEffect(()=>{const token=++generation.current;let cancelled=false;setState(previous=>({...previous,loading:true}));
  (manifestOverride?Promise.resolve(manifestOverride):fetch('/character/manifest.json',{cache:'no-cache'}).then(r=>{if(!r.ok)throw new Error();return r.json();})).then(m=>composeCharacter(canvas.current!,m,slots,items,()=>!cancelled&&token===generation.current))
   .then(result=>{if(result&&!cancelled)setState({...result,loading:false});}).catch(()=>{if(!cancelled)setState({unavailable:true,loading:false});});
  return()=>{cancelled=true;};
 },[key,items,manifestOverride]);
 const description=Object.entries(slots).filter(([,id])=>id).map(([slot,id])=>slotLabels[slot]+': '+(items.find(i=>i.id===id)?.name||id)).join('. ');
 return <figure className={'character-scene'+(compact?' compact':'')}>
  <div className="scene-art"><span className="scene-seal"><Emblem/></span><canvas ref={canvas} role="img" aria-label={'Образ персонажа. '+description} style={{visibility:state.unavailable?'hidden':'visible'}}/>
   {state.unavailable&&<div className="scene-placeholder"><Emblem name="character"/><p>Образ готовится</p></div>}
   {preview&&<span className="preview-tag">Примерка · без сохранения</span>}
  </div>
  <figcaption>{state.loading?(state.rendered?'Обновляем · показан предыдущий образ':'Подготавливаем образ…'):state.unavailable?'Изображение временно недоступно':state.missing?.length?'Выбор сохранён; часть изображений готовится':'Подтверждённый образ'}{!compact&&<span className="sr-only">{description}</span>}</figcaption>
 </figure>;
}
