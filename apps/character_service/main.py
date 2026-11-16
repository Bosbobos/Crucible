"""Authenticated API косметического пути. Нет endpoint для выдачи XP."""
import uuid
import json
from pathlib import Path
from typing import Literal
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import Field
from psycopg.types.json import Jsonb
from platformkit.runtime import app_factory, config, db, identity, command, RevisionCommand, now,emit
from .definitions import DATA, ITEMS, SLOTS, CATALOG_VERSION, RULESET
from .domain import rhythm
from .store import ensure_profile, consume

cfg = config()
app = app_factory(cfg,(lambda raw:consume(cfg,raw)) if cfg.get('character_write',True) else None)
PREFIX = '/api/character/v1'


@app.exception_handler(HTTPException)
async def error(request, exc):
    detail = exc.detail
    return JSONResponse(status_code=exc.status_code,content={'detail':detail,
        'code':detail.get('code','character_error') if isinstance(detail,dict) else 'character_error',
        'correlation_id':getattr(request.state,'request_id',None)})


@app.exception_handler(RequestValidationError)
async def invalid_request(request,exc):
    return JSONResponse(status_code=422,content={'code':'validation_error','detail':'Некорректный формат запроса',
        'correlation_id':getattr(request.state,'request_id',None)})


def actor(request, write=False):
    result = identity(request,cfg,'character:write' if write else 'character:read')
    if not cfg.get('character_write' if write else 'character_read',True):
        raise HTTPException(503,{'code':'character_unavailable','message':'Путь временно недоступен'})
    return result


def art(item):
    # Per-part runtime manifest is published independently of ownership/XP.
    from .assets import representation
    return representation(item)


@app.get(PREFIX+'/catalog')
def catalog(request: Request):
    actor(request)
    return {'catalog_version':CATALOG_VERSION,'ruleset_version':RULESET,'slots':SLOTS,
            'items':[{**i,**art(i)} for i in ITEMS.values()],
            'sets':[{k:s[k] for k in ('id','name','tier')} for s in DATA['sets']['sets']],
            'ranks':DATA['ranks']['ranks']}


@app.get(PREFIX+'/me/summary')
def summary(request: Request, at_least_practice_seq:int=0):
    actor(request)
    with db(cfg) as conn:
        row = ensure_profile(conn)
        s = row['summary']
        checkpoints = {r['source']:r['applied_seq'] for r in conn.execute('SELECT * FROM source_checkpoints').fetchall()}
        seq = checkpoints.get('practice-service',0)
        prefs = conn.execute("SELECT preferences FROM preferences WHERE profile_id='owner'").fetchone()['preferences']
        settings=conn.execute("SELECT timezone FROM profile_settings_projection WHERE profile_id='owner'").fetchone()
        owned={r['item_id'] for r in conn.execute("SELECT item_id FROM item_ownership WHERE profile_id='owner'").fetchall()}
        pinned=ITEMS.get(prefs.get('pinned_reward'))
        next_item=pinned if pinned and pinned['id'] not in owned else next((i for i in ITEMS.values() if i['id'] not in owned),None)
        return {k:s[k] for k in ('xp','level','chronicles','rank','metrics')} | {
            'computed_at':row['computed_at'],'summary_revision':row['revision'], 'catalog_version':CATALOG_VERSION,
            'ruleset_version':RULESET, 'source_checkpoints':checkpoints,
            'freshness':'pending' if seq<at_least_practice_seq else 'current',
            'next_level':DATA['progression']['levels'][s['level']] if s['level']<60 else None,
            'preferences':prefs,'next_reward':next_item,
            'rhythm':rhythm(s['activity_instants'],now(),settings['timezone'] if settings else cfg.get('profile_timezone','Europe/Moscow'))}


def inventory_rows(conn):
    rows = {r['item_id']:r for r in conn.execute("SELECT * FROM item_ownership WHERE profile_id='owner'").fetchall()}
    slots = conn.execute("SELECT slots FROM loadouts WHERE profile_id='owner'").fetchone()['slots']
    return [{**item,**art(item),'owned':item['id'] in rows,'equipped':item['id'] in slots.values(),
             'current_qualified':rows.get(item['id'],{}).get('current_qualified',False),
             'evidence_recheck':rows.get(item['id'],{}).get('evidence_recheck',False)} for item in ITEMS.values()]


@app.get(PREFIX+'/me/inventory')
def inventory(request: Request, offset:int=0, limit:int=60):
    actor(request)
    if offset<0 or not 1<=limit<=60:
        raise HTTPException(422,'Некорректная страница')
    with db(cfg) as conn:
        ensure_profile(conn)
        return {'items':inventory_rows(conn)[offset:offset+limit],'total':len(ITEMS),'catalog_version':CATALOG_VERSION}


@app.get(PREFIX+'/me/items/{item_id}')
def item_detail(item_id:str,request:Request):
    actor(request)
    with db(cfg) as conn:
        ensure_profile(conn)
        item = next((i for i in inventory_rows(conn) if i['id']==item_id),None)
        if not item:
            raise HTTPException(404,'Предмет не найден')
        return item


@app.get(PREFIX+'/me/loadout')
def loadout(request:Request):
    actor(request)
    with db(cfg) as conn:
        ensure_profile(conn)
        row=conn.execute("SELECT * FROM loadouts WHERE profile_id='owner'").fetchone()
        return {**row,'rig_version':'crucible-dragonborn-front-v3','manifest_url':'/character/manifest.json'}


class Loadout(RevisionCommand):
    slots:dict[str,str|None]


def validate_owned(conn,ids,slot=None):
    owned={r['item_id'] for r in conn.execute("SELECT item_id FROM item_ownership WHERE profile_id='owner'").fetchall()}
    for item_id in ids:
        if item_id is None:
            continue
        item=ITEMS.get(item_id)
        if item is None or item_id not in owned:
            raise HTTPException(422,{'code':'item_not_owned','message':'Предмет ещё не получен'})
        if item['slot']!=slot:
            raise HTTPException(422,{'code':'wrong_slot','message':'Предмет не подходит к слоту'})


@app.put(PREFIX+'/me/loadout')
def equip(body:Loadout,request:Request):
    subject=actor(request,True)
    with db(cfg) as conn:
        def effect():
            ensure_profile(conn)
            if set(body.slots)!=set(SLOTS):
                raise HTTPException(422,{'code':'invalid_slots','message':'Нужны все девять слотов'})
            for slot,item_id in body.slots.items():
                validate_owned(conn,[item_id],slot)
            row=conn.execute("UPDATE loadouts SET slots=%s,revision=revision+1 WHERE profile_id='owner' AND revision=%s RETURNING *",
                             (Jsonb(body.slots),body.expected_revision)).fetchone()
            if row is None:
                current=conn.execute("SELECT revision FROM loadouts WHERE profile_id='owner'").fetchone()['revision']
                raise HTTPException(409,{'code':'revision_conflict','message':'Образ изменён в другой вкладке','current_revision':current})
            emit(conn,cfg,'character.progress.updated.v1','owner','owner:loadout',row['revision'],
                 {'kind':'loadout','revision':row['revision']},request.state.request_id)
            return row
        return command(conn,subject,body,'character.equip',effect)


@app.get(PREFIX+'/me/path')
def path(request:Request):
    actor(request)
    with db(cfg) as conn:
        row=ensure_profile(conn)
        states={r['seal_id']:{**r['state'],'ever_granted':r['ever_granted'],
                'evidence_recheck':r['ever_granted'] and not r['state']['current_qualified']}
                for r in conn.execute("SELECT * FROM seal_state WHERE profile_id='owner'").fetchall()}
        return {'ranks':DATA['ranks']['ranks'],'disciplines':DATA['disciplines']['disciplines'],
            'volumes':[{k:v[k] for k in ('id','discipline_id','name','binding_status')} for v in DATA['volumes']['volumes']],
            'trials':[{k:b[k] for k in ('id','seal','discipline_id','problem_count','min_score','min_C_fraction','requires_E','requires_R','suggested_minutes') if k in b}
                      for b in DATA['trial_blueprints']['blueprints'] if b['seal'] in ('K','M')],
            'seals':states or row['summary']['seals'],'summary_revision':row['revision']}


@app.get(PREFIX+'/me/journal')
def journal(request:Request, after:int=0):
    actor(request)
    with db(cfg) as conn:
        profile=ensure_profile(conn)
        ranks=[r['id'] for r in DATA['ranks']['ranks']]
        chapters=json.loads(Path(__file__).with_name('lore.json').read_text())
        unlocked=set(ranks[:ranks.index(profile['summary']['rank']['id'])+1])
        rows=conn.execute("SELECT * FROM reward_journal WHERE profile_id='owner' AND id>%s ORDER BY id LIMIT 50",(after,)).fetchall()
        return {'entries':rows,'next_cursor':rows[-1]['id'] if rows else after,
                'chapters':[c for c in chapters if c['rank_id'] in unlocked]}


@app.get(PREFIX+'/me/operations/{correlation_id}')
def operation(correlation_id:uuid.UUID,request:Request):
    actor(request)
    with db(cfg) as conn:
        row=conn.execute("SELECT result FROM operations WHERE profile_id='owner' AND correlation_id=%s",(correlation_id,)).fetchone()
        # Opaque pending never discloses whether another subject owns the ID.
        return row['result'] if row else {'status':'pending'}


@app.get(PREFIX+'/me/collection')
def collection(request:Request):
    actor(request)
    with db(cfg) as conn:
        ensure_profile(conn)
        return conn.execute("SELECT * FROM collection_placements WHERE profile_id='owner'").fetchone()


class Collection(RevisionCommand):
    positions:list[str|None]=Field(min_length=9,max_length=9)


@app.put(PREFIX+'/me/collection')
def place(body:Collection,request:Request):
    subject=actor(request,True)
    with db(cfg) as conn:
        def effect():
            ensure_profile(conn)
            ids=[i for i in body.positions if i is not None]
            if len(ids)!=len(set(ids)):
                raise HTTPException(422,'Реликвия занимает только одно место')
            validate_owned(conn,ids,None)
            row=conn.execute("UPDATE collection_placements SET positions=%s,revision=revision+1 WHERE profile_id='owner' AND revision=%s RETURNING *",(Jsonb(body.positions),body.expected_revision)).fetchone()
            if not row:
                raise HTTPException(409,{'code':'revision_conflict','message':'Полка изменена'})
            emit(conn,cfg,'character.progress.updated.v1','owner','owner:collection',row['revision'],
                 {'kind':'collection','revision':row['revision']},request.state.request_id)
            return row
        return command(conn,subject,body,'character.collection',effect)


@app.get(PREFIX+'/me/preferences')
def preferences(request:Request):
    actor(request)
    with db(cfg) as conn:
        ensure_profile(conn)
        return conn.execute("SELECT * FROM preferences WHERE profile_id='owner'").fetchone()


class Preferences(RevisionCommand):
    rpg_visible:bool
    focus_mode:bool
    pinned_reward:str|None=None


@app.patch(PREFIX+'/me/preferences')
def change_preferences(body:Preferences,request:Request):
    subject=actor(request,True)
    with db(cfg) as conn:
        def effect():
            ensure_profile(conn)
            if body.pinned_reward and body.pinned_reward not in ITEMS:
                raise HTTPException(422,'Неизвестная награда')
            value=body.model_dump(exclude={'command_id','expected_revision'})
            row=conn.execute("UPDATE preferences SET preferences=%s,revision=revision+1 WHERE profile_id='owner' AND revision=%s RETURNING *",(Jsonb(value),body.expected_revision)).fetchone()
            if not row:
                raise HTTPException(409,{'code':'revision_conflict','message':'Настройки изменены'})
            emit(conn,cfg,'character.progress.updated.v1','owner','owner:preferences',row['revision'],
                 {'kind':'preferences','revision':row['revision']},request.state.request_id)
            return row
        return command(conn,subject,body,'character.preferences',effect)


@app.get('/internal/character/snapshot')
def snapshot(request:Request):
    identity(request,cfg,'character:snapshot')
    with db(cfg) as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        tables=('character_profile','inbox_events','source_facts','fact_revisions','xp_entitlements','xp_ledger',
            'seal_state','item_ownership','loadouts','collection_placements','preferences','definition_publications',
            'campaign_projection','campaign_publications','profile_settings_projection','source_checkpoints',
            'reward_journal','operations','command_receipts','outbox','source_stream')
        from psycopg import sql
        return {'schema_version':1,'catalog_version':CATALOG_VERSION,'tables':{t:conn.execute(sql.SQL('SELECT * FROM {}').format(sql.Identifier(t))).fetchall() for t in tables}}


@app.get(PREFIX+'/me/diagnostics')
def diagnostics(request:Request):
    identity(request,cfg,'diagnostics:read')
    with db(cfg) as conn:
        return {'inbox':conn.execute('SELECT disposition,count(*) FROM inbox_events GROUP BY disposition').fetchall(),
                'ledger':conn.execute('SELECT sum(delta) AS total,sum(delta) FILTER(WHERE delta<0) AS compensation FROM xp_ledger').fetchone()}
