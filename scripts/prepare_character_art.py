"""Воспроизводимая нарезка принятых источников. Генератор изображений не используется.

Контуры/QA: Assets/Character. Raw остаются в пакете неизменными.
Без явного per-part QA candidate не становится runtime_ready.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFilter,ImageFont

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'Task/Crucible_Implementation_Pack_v3'
EDIT=ROOT/'Assets/Character'
OUT=ROOT/'apps/web/public/character'
QA=ROOT/'.private/evidence/crucible-v3/art'
W,H=1024,1536


def mask(polygons):
    im=Image.new('L',(W,H));draw=ImageDraw.Draw(im)
    for p in polygons:draw.polygon([tuple(v) for v in p],fill=255)
    return im


def cut_background(im,protected_white=None,white_threshold=235):
    arr=np.asarray(im.convert('RGBA')).copy()
    if arr[:,:,3].min()==255:
        rgb=arr[:,:,:3].astype(float)
        white=(rgb.min(2)>white_threshold)&((rgb.max(2)-rgb.min(2))<25)
        if protected_white is not None:
            white &= ~protected_white
        connected=Image.fromarray((white*255).astype('uint8')).copy()
        for seed in ((0,0),(W-1,0),(0,H-1),(W-1,H-1)):
            if connected.getpixel(seed)==255:ImageDraw.floodfill(connected,seed,128)
        background=np.asarray(connected)==128
        foreground=~background
        # Unmatte only the two-pixel exterior boundary against its measured white
        # backdrop. Interior white wrap/highlights remain unchanged.
        core=np.asarray(Image.fromarray((foreground*255).astype('uint8')).filter(ImageFilter.MinFilter(5)))>0
        known=core.copy();nearest=rgb.copy()
        for _ in range(4):
            old=known.copy()
            for dy,dx in ((0,1),(0,-1),(1,0),(-1,0)):
                neighbor=np.roll(old,(dy,dx),(0,1));choose=~known&foreground&neighbor
                nearest[choose]=np.roll(nearest,(dy,dx),(0,1))[choose];known|=choose
        direction=255-nearest
        estimate=np.clip(np.sum((255-rgb)*direction,axis=2)/np.maximum(1,np.sum(direction*direction,axis=2)),.02,1)
        boundary=foreground&~core
        restored=np.clip((rgb-255*(1-estimate[:,:,None]))/estimate[:,:,None],0,255)
        arr[boundary,:3]=restored[boundary].astype('uint8')
        alpha=foreground.astype(float);alpha[boundary]=estimate[boundary]
        arr[:,:,3]=(alpha*255).round().astype('uint8')
    else:
        # Sources have alpha≈253 on the subject and low-alpha colored residue outside.
        a=arr[:,:,3].astype(float)
        arr[:,:,3]=np.where(a<24,0,np.minimum(255,a*255/253)).astype('uint8')
    arr[arr[:,:,3]==0,:3]=0
    return Image.fromarray(arr)


def write_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');temporary.replace(path)


def export(image,relative,webp=True):
    path=OUT/relative;path.parent.mkdir(parents=True,exist_ok=True)
    if webp:image.save(path,format='WEBP',quality=88,method=6)
    else:image.save(path)
    data=path.read_bytes();digest=hashlib.sha256(data).hexdigest()
    immutable=OUT/'files'/(digest+path.suffix);immutable.parent.mkdir(exist_ok=True)
    if not immutable.exists():immutable.write_bytes(data)
    return {'path':'/character/files/'+immutable.name,'sha256':digest,'bytes':len(data)}


def composite(base,layers):
    if not layers:return base.copy()
    union=np.maximum.reduce([np.asarray(hide) for _,hide in layers])
    arr=np.asarray(base).copy();arr[:,:,3]=(arr[:,:,3].astype(float)*(1-union/255)).round().astype('uint8')
    result=Image.fromarray(arr)
    for paint,_ in layers:result=Image.alpha_composite(result,paint)
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--proof',action='store_true');args=parser.parse_args()
    contours=json.loads((EDIT/'contours.json').read_text())
    decisions=json.loads((EDIT/'qa.json').read_text()) if (EDIT/'qa.json').exists() else {}
    sources=json.loads((SOURCE/'data/source_assets.json').read_text())['assets']
    for a in sources:
        assert hashlib.sha256((SOURCE/a['package_path']).read_bytes()).hexdigest()==a['sha256'],a['asset_id']
    QA.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
    base=cut_background(Image.open(SOURCE/'references/BASE-00.png'))
    base_info=export(base,'base.webp');base.save(QA/'base.png')
    # One owner per BASE pixel. No double-alpha seams on reassembly.
    occupied=np.zeros((H,W),dtype=bool);regions={};region_files={};reassembled=np.zeros((H,W,4),dtype='uint8');base_arr=np.asarray(base)
    for region,polygons in contours['base_regions'].items():
        owned=(np.asarray(mask(polygons))>0)&~occupied&(base_arr[:,:,3]>0);occupied|=owned
        regions[region]=owned
        region_files[region]=export(Image.fromarray(owned.astype('uint8')*255),'regions/'+region+'.png',False)['path']
        pixels=np.zeros_like(base_arr);pixels[owned]=base_arr[owned];reassembled[owned]=pixels[owned]
        p=QA/'base-regions'/f'{region}.png';p.parent.mkdir(exist_ok=True);Image.fromarray(pixels).save(p)
    assert np.array_equal(reassembled,base_arr),'BASE reconstruction changed pixels'
    Image.fromarray(reassembled).save(QA/'base-reassembled.png')
    allowed={'chest':['neck','torso'],'shoulders':['upper_arms'],'bracers':['forearms'],
             'legs':['pelvis','modesty_wrap','lower_body']}
    entries={};layers={};reports=[]
    for sid,plate in contours['plates'].items():
        if args.proof and sid not in ('ARM-00','ARM-04'):continue
        # Enamel has a different measured white range from the BASE backdrop.
        # Flood-fill is restricted to connected near-white backdrop; enclosed
        # enamel highlights are retained rather than globally keyed out.
        source=cut_background(Image.open(SOURCE/'references'/f'{sid}.png'),white_threshold=248 if sid=='ARM-03' else 235)
        assert plate['transform']==[1,0,0,0,1,0],'Неподдержанный неявный transform'
        export(source.resize((320,480),Image.Resampling.LANCZOS),'gallery/'+sid+'.webp')
        entries[sid]={'status':'reference_available','parts':{}}
        for part in ('chest','legs','shoulders','bracers'):
            c=plate[part];paint_mask=np.asarray(mask(c['include'])).copy()
            if c.get('exclude'):paint_mask[np.asarray(mask(c['exclude']))>0]=0
            paint_mask=np.asarray(Image.fromarray(paint_mask).filter(ImageFilter.GaussianBlur(.35)))
            paint_mask=paint_mask.copy()
            for protected in ('head_face_horns','hand_right_neutral','hand_left_neutral','tail_back'):
                paint_mask[regions[protected]]=0
            pixels=np.asarray(source).copy();pixels[:,:,3]=(pixels[:,:,3].astype(float)*paint_mask/255).round().astype('uint8')
            if sid in ('ARM-02','ARM-04'):
                rgb=pixels[:,:,:3].astype(float)
                skin=(rgb[:,:,0]>1.7*rgb[:,:,1])&(rgb[:,:,1]>1.3*rgb[:,:,2])&(rgb[:,:,0]>120)
                pixels[skin,3]=0
            paint=Image.fromarray(pixels)
            permitted=np.logical_or.reduce([regions[r] for r in allowed[part]])
            hide=permitted.astype('uint8')*255
            if part=='chest':hide[:213]=0;hide[650:]=0
            if part=='shoulders':hide[470:]=0
            if part=='bracers':hide[:548]=0
            if part=='legs':hide[1448:]=0
            else:
                # Garment does not replace the open neckline / bare upper arm.
                # Anatomical ownership bounds the mask; paint bounds coverage.
                hide=np.minimum(hide,pixels[:,:,3])
            # Only replace real subject pixels, never the transparent surroundings.
            hide[base_arr[:,:,3]==0]=0
            hide=Image.fromarray(hide)
            name=sid+'/'+part
            paint_info=export(paint,name+'.webp');hide_info=export(hide,name+'-hide.png',False)
            edit=EDIT/'masks'/sid;edit.mkdir(parents=True,exist_ok=True)
            Image.fromarray(paint_mask).save(edit/(part+'-paint.png'));hide.save(edit/(part+'-hide-base.png'))
            layers[(sid,part)]=(paint,hide)
            choice=decisions.get(name,{})
            status=choice.get('status','processing')
            if status=='runtime_ready' and (choice.get('paint_sha256')!=paint_info['sha256'] or choice.get('mask_sha256')!=hide_info['sha256'] or choice.get('rig_id')!=contours['rig_id']):
                status='processing'
            bbox=paint.getbbox();icon_info=None
            if bbox:
                icon=Image.new('RGBA',(320,400));crop=paint.crop(bbox);crop.thumbnail((256,336),Image.Resampling.LANCZOS)
                icon.alpha_composite(crop,((320-crop.width)//2,(400-crop.height)//2));icon_info=export(icon,name+'-icon.webp')
            entries[sid]['parts'][part]={'status':status,'path':paint_info['path'],'hide_base_path':hide_info['path'],
                'allowed_base_regions':allowed[part],'rig_id':contours['rig_id'],'sha256':paint_info['sha256'],
                'mask_sha256':hide_info['sha256'],'bytes':paint_info['bytes']+hide_info['bytes'],
                'qa_report':choice.get('report'),'source_transform':plate['transform'],
                'icon_path':icon_info['path'] if icon_info else None}
            candidate=composite(base,[(paint,hide)]);candidate.save(QA/(sid+'-'+part+'.png'))
            reports.append({'part':name,'status':status,'bytes':paint_info['bytes']+hide_info['bytes']})
    cases=[]
    for (sid,part),layer in layers.items():cases.append((sid+' '+part,[layer]))
    for sid in entries:cases.append((sid+' full',[layers[(sid,p)] for p in ('chest','legs','shoulders','bracers')]))
    visual=json.loads((SOURCE/'data/visual_test_cases.json').read_text())
    for mixed in visual['mixed_outfits']:
        outfit=[]
        for slot,item in mixed['slots'].items():
            sid='ARM-0'+item.split('-')[1]
            if (sid,slot) in layers:outfit.append(layers[(sid,slot)])
        if len(outfit)==4:cases.append((mixed['id'],[outfit[list(mixed['slots']).index(p)] for p in ('chest','legs','shoulders','bracers')]))
    sword_data=contours.get('sword')
    if sword_data:
        source=cut_background(Image.open(SOURCE/'references/SWORD-POSE-REF.png'))
        pixels=np.asarray(source).copy();m=np.asarray(mask(sword_data['include']))
        pixels[:,:,3]=(pixels[:,:,3].astype(float)*m/255).round().astype('uint8')
        sword=Image.fromarray(pixels);sword_info=export(sword,'SWD-03/main.webp')
        rgb=np.asarray(source)[:,:,:3].astype(float)
        skin=(rgb[:,:,0]>1.25*rgb[:,:,1])&(rgb[:,:,1]>1.1*rgb[:,:,2])
        front=(np.asarray(mask(sword_data['grip_front']))>0)&skin
        back=(np.asarray(mask(sword_data['grip_back']))>0)&skin&~front
        grip_images=[];dependencies=[]
        for pass_,region in (('grip_back',back),('grip_front',front)):
            rgba=np.asarray(source).copy();rgba[~region,3]=0
            im=Image.fromarray(rgba);info=export(im,'HAND-R-GRIP-01/'+pass_+'.webp')
            dependencies.append({'pass':pass_,'path':info['path'],'sha256':info['sha256']});grip_images.append(im)
            p=EDIT/'masks/HAND-R-GRIP-01';p.mkdir(exist_ok=True,parents=True);Image.fromarray(region.astype('uint8')*255).save(p/(pass_+'.png'))
        neutral=regions['hand_right_neutral']&(base_arr[:,:,3]>0)
        hide=Image.fromarray(neutral.astype('uint8')*255);info=export(hide,'HAND-R-GRIP-01/hide-neutral.png',False)
        dependencies.append({'pass':'hide_neutral_hand','path':info['path'],'sha256':info['sha256']})
        choice=decisions.get('SWD-03/main',{})
        entries['SWD-03']={'status':'reference_available','parts':{'main':{'status':choice.get('status','processing'),
            **sword_info,'rig_id':contours['rig_id'],'hide_base_path':None,'dependencies':dependencies,'qa_report':choice.get('report')}}}
        # Explicit render order for QC, independently of production readiness.
        for sid in entries:
            if (sid,'chest') not in layers:continue
            anatomy=composite(base,[(Image.new('RGBA',(W,H)),hide)])
            anatomy=Image.alpha_composite(anatomy,grip_images[0])
            worn=composite(anatomy,[layers[(sid,p)] for p in ('chest','legs','shoulders','bracers')])
            worn=Image.alpha_composite(worn,sword);worn=Image.alpha_composite(worn,grip_images[1])
            worn.save(QA/(sid+'-sword.png'))
    # Three QC backgrounds; individual full-size composites and compact contact sheets.
    for bg in ('#FFFFFF','#252B31','#00BCD4'):
        thumb=240;cell_h=390;columns=5
        sheet=Image.new('RGB',(thumb*columns,cell_h*((len(cases)+columns-1)//columns)),bg);draw=ImageDraw.Draw(sheet)
        for index,(label,parts_) in enumerate(cases):
            comp=composite(base,parts_);back=Image.new('RGBA',(W,H),bg);back=Image.alpha_composite(back,comp)
            x=(index%columns)*thumb;y=(index//columns)*cell_h
            sheet.paste(back.convert('RGB').resize((thumb,360),Image.Resampling.LANCZOS),(x,y+24))
            draw.text((x+5,y+5),label,fill='white' if bg=='#252B31' else '#222B32')
        sheet.save(QA/('contact-'+bg[1:]+'.jpg'),quality=92)
    manifest={'schema_version':1,'rig_id':contours['rig_id'],'canvas':[W,H],
        'base':{**base_info,'region_masks':region_files,'status':decisions.get('BASE-00',{}).get('status','processing')
                if decisions.get('BASE-00',{}).get('sha256')==base_info['sha256'] else 'processing'},'assets':entries,
        'anchors':contours['anchors'],'source_hashes':{a['asset_id']:a['sha256'] for a in sources}}
    manifest['manifest_version']=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()[:20]
    write_json(OUT/'manifest.json',manifest)
    write_json(ROOT/'apps/character_service/asset-manifest.json',manifest)
    write_json(QA/'report.json',{'base_reassembly':'passed','parts':reports,'cases':len(cases),'backgrounds':3,
        'max_layer_bytes':max(r['bytes'] for r in reports),'visual_qa':'per-part decisions in Assets/Character/qa.json'})
    write_json(EDIT/'rig.json',{'rig_id':contours['rig_id'],'canvas':[W,H],'anchors':contours['anchors'],
        'measurement':contours['measurement'],'base_source_sha256':sources[0]['sha256']})
    print(json.dumps({'parts':len(reports),'cases':len(cases),'base_reassembly':'passed','max_layer_bytes':max(r['bytes'] for r in reports)}))


if __name__=='__main__':main()
