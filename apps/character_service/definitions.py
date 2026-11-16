"""Неизменяемая публикация проверенных определений пакета 3.0.0."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).with_name('definitions')
FILES = ('progression', 'items', 'ranks', 'sets', 'volumes', 'trial_blueprints', 'disciplines', 'id_aliases')


def validate(data):
    expected = {'items': ('items', 59), 'ranks': ('ranks', 6), 'sets': ('sets', 6),
                'volumes': ('volumes', 25), 'trial_blueprints': ('blueprints', 58), 'disciplines': ('disciplines', 5)}
    if set(data) != set(FILES):
        raise ValueError('Неполная публикация definitions')
    for name, (key, count) in expected.items():
        doc = data[name]
        if doc['schema_version'] != 1 or len(doc[key]) != count:
            raise ValueError('Неверная версия/количество: '+name)
        ids = [v['id'] for v in doc[key]]
        if len(set(ids)) != len(ids) or not all(isinstance(i, str) and i for i in ids):
            raise ValueError('Неуникальные ID: '+name)
    p = data['progression']
    if p['ruleset_id'] != 'crucible-v1' or len(p['levels']) != 60:
        raise ValueError('Неизвестный ruleset')
    for level, row in enumerate(p['levels'], 1):
        if row != {'level': level, 'total_xp': 100*(level-1)+8*(level-1)*(level-2),
                   'next_level_cost': 100+16*(level-1) if level < 60 else None}:
            raise ValueError('Неверный порог уровня')
    slots = data['items']['slots']
    if len(slots) != 9 or len(set(slots)) != 9:
        raise ValueError('Неверные слоты')
    metrics = {'level', 'seals.V', 'seals.E', 'seals.R', 'seals.K', 'seals.M', 'first_fresh_independent_C_ge_80',
               'discipline_seal.K', 'disciplines_with_E', 'disciplines_with_V'}
    for row in data['items']['items']+data['ranks']['ranks']:
        if set(row['unlock']) != {'all'} or row['grants_xp'] != 0:
            raise ValueError('Награды не создают XP')
        for condition in row['unlock']['all']:
            if condition['metric'] not in metrics or type(condition['gte']) is not int or condition['gte'] < 0:
                raise ValueError('Неизвестное условие unlock')
            if condition['metric'] == 'first_fresh_independent_C_ge_80' and condition.get('discipline_id') not in {'LA','CA','PR','DS','OD'}:
                raise ValueError('Неизвестная дисциплина')
    for row in data['items']['items']:
        if row['slot'] not in [*slots, None] or row['auto_equip'] is not False or row['auto_grant'] is not True:
            raise ValueError('Неверный предмет')
    ids = {v['id'] for v in data['items']['items']}
    if not set(data['id_aliases']['item_id_aliases'].values()) <= ids:
        raise ValueError('Alias не существует')
    return data


DATA = validate({n: json.loads((ROOT/(n+'.json')).read_text()) for n in FILES})
HASH = hashlib.sha256(json.dumps(DATA, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
CATALOG_VERSION = '3.0.0:'+HASH[:16]
RULESET = DATA['progression']['ruleset_id']
ITEMS = {i['id']: i for i in DATA['items']['items']}
SLOTS = tuple(DATA['items']['slots'])
STARTING = tuple(i['id'] for i in ITEMS.values() if not i['unlock']['all'])
