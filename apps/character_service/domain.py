"""Чистый детерминированный пересчёт прав. Доставка и SQL находятся снаружи."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from zoneinfo import ZoneInfo
from .definitions import DATA, ITEMS, RULESET

BASE = DATA['progression']['problem_base_xp']


def number(value):
    if isinstance(value, bool):
        raise ValueError('Boolean не является оценкой')
    try:
        return Fraction(str(value))
    except (ValueError, ZeroDivisionError, TypeError):
        raise ValueError('Требуется конечное число') from None


def instant(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00')) if isinstance(value, str) else value
    if not isinstance(dt, datetime) or dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError('Требуется timestamp с timezone')
    return dt.astimezone(timezone.utc)


def parts(values):
    if not values or len({p['part_id'] for p in values}) != len(values):
        raise ValueError('Пустые или повторяющиеся пункты')
    for p in values:
        if not p['part_id'] or number(p['weight']) <= 0 or not 0 <= number(p['quality']) <= 1:
            raise ValueError('Некорректные веса или качество')
        if p['outcome'] not in {'independent','assisted','reviewed','skipped'} or type(p['note_saved']) is not bool:
            raise ValueError('Неизвестный исход')
    return values


def weighted(values, repeat=False, quality_only=False):
    values = parts(values)
    def contribution(p):
        if p['outcome'] in {'independent','assisted'}:
            coefficient = 1 if quality_only or p['outcome'] == 'independent' else Fraction(7, 10)
            return number(p['quality'])*coefficient
        return Fraction(35,100) if p['outcome']=='reviewed' and p['note_saved'] and not repeat and not quality_only else 0
    return sum((number(p['weight'])*contribution(p) for p in values), Fraction(0))/sum(number(p['weight']) for p in values)


def candidate(snapshot, repeat=False):
    if snapshot['difficulty'] not in BASE:
        raise ValueError('Неизвестная сложность')
    amount = BASE[snapshot['difficulty']]*weighted(snapshot['parts'], repeat=repeat)*(Fraction(3,10) if repeat else 1)
    return amount.numerator//amount.denominator


def level_for(xp):
    if type(xp) is not int or xp < 0:
        raise ValueError('XP должен быть неотрицательным целым')
    return max(row['level'] for row in DATA['progression']['levels'] if row['total_xp'] <= xp)


def cold_independent(s, minimum=Fraction(4,5)):
    return (s['provenance']['owner_confirmed'] is True and s['help_during_attempt'] is False
            and all(v is False for v in s['freshness'].values()) and len(s['freshness']) == 3
            and all(p['outcome']=='independent' for p in s['parts'])
            and weighted(s['parts'], quality_only=True) >= minimum)


def qualified(unlock, metrics):
    return all(metrics.get(c['metric']+(':'+c['discipline_id'] if 'discipline_id' in c else ''), 0) >= c['gte'] for c in unlock['all'])


def recompute(facts, bindings=None):
    """Полные актуальные facts; bindings — подтверждённая private проекция content owner.

    Отсутствующая привязка никогда не выводится из текста, tags или номера навыка.
    Возвращает desired entitlements, которые application сравнивает с применёнными.
    """
    bindings = bindings or {}
    valid = [f for f in facts if f['status']=='confirmed']
    attempts = [f['snapshot'] for f in valid if f['fact_type']=='attempt_result' and f['snapshot']['provenance']['owner_confirmed']]
    groups = defaultdict(list)
    entitlements, evidence = {}, {}
    active = []
    for s in attempts:
        candidate(s)
        if instant(s['began_at']) > instant(s['completed_at']):
            raise ValueError('Завершение раньше начала')
        groups[s['reward_equivalence_id']].append(s)
        if weighted(s['parts']) > 0:
            active.append(s['completed_at'])
    for eq, rows in sorted(groups.items()):
        best, last, repeats, used_obligations = 0, None, 0, set()
        for s in sorted(rows, key=lambda s: (instant(s['completed_at']), s['source_sequence'], s['attempt_id'])):
            amount = candidate(s)
            if amount > best:
                best, last = amount, instant(s['completed_at'])
                evidence['primary:'+eq] = [s['attempt_id']]
                rc=s['review_context']
                if rc and instant(s['completed_at'])>=instant(rc['due_at']):used_obligations.add(rc['obligation_id'])
                continue
            rc = s['review_context']
            if (rc and rc['is_scheduler_obligation'] is True and rc['owner']=='learning-service'
                    and repeats < 3 and rc['obligation_id'] not in used_obligations and last is not None and s['help_during_attempt'] is not None
                    and instant(s['completed_at']) >= instant(rc['due_at'])
                    and instant(s['completed_at'])-last >= timedelta(hours=168)
                    and instant(s['completed_at'])-instant(rc['last_credited_learning_at']) >= timedelta(hours=168)
                    and weighted(s['parts'], quality_only=True) >= Fraction(4,5)):
                key = 'repeat:'+eq+':'+s['attempt_id']
                entitlements[key] = candidate(s, repeat=True)
                evidence[key] = [s['attempt_id']]
                repeats += 1
                used_obligations.add(rc['obligation_id'])
                last = instant(s['completed_at'])
        entitlements['primary:'+eq] = best
    units = {}
    diagnostics = {}
    for f in valid:
        s = f['snapshot']
        if f['fact_type']=='learning_unit_completed' and s['owner_confirmed']:
            b = bindings.get('units', {}).get(s['unit_id'])
            if not b or b['volume_id']!=s['volume_id'] or b['content_version']!=s['content_version'] or b['unit_kind']!=s['unit_kind']:
                continue
            ok = s['explicit_completion'] and s['answers_saved']
            if s['unit_kind']=='lab':
                ok = s['explicit_completion'] and s['explanation_saved'] and s['prediction_saved'] and s['run_saved']
            if s['unit_kind']=='volume_final_check':
                ok = ok and s['explanation_saved'] and s['total_count']==4 and s['correct_count']>=3
            if ok:
                units[s['unit_id']] = s
                entitlements['unit:'+s['unit_id']] = DATA['progression']['learning_units_xp'][s['unit_kind']]
                evidence['unit:'+s['unit_id']] = [s['unit_id']]
                active.append(s['completed_at'])
        if f['fact_type']=='diagnostic_result' and s['owner_confirmed'] and s['total_count']==4 and s['correct_count']>=3:
            b = bindings.get('volumes', {}).get(s['volume_id'], {})
            if b.get('diagnostic_id')==s['check_id'] and b.get('diagnostic_version')==s['check_version']:
                diagnostics[s['volume_id']] = s
    seals = {}
    for v in DATA['volumes']['volumes']:
        vid = v['id']
        b = bindings.get('volumes', {}).get(vid)
        candidates = []
        for s in attempts:
            pb = bindings.get('problems', {}).get(s['problem_id'])
            if (pb and s['mapped_volume_id']==vid and pb.get('volume_id')==vid
                    and pb.get('mapping_version')==s['mapping_version'] and s['family_id']
                    and pb.get('family_id')==s['family_id'] and pb.get('rubric_version')==s['rubric_version']
                    and pb.get('content_version')==s['content_version']
                    and pb.get('reward_equivalence_id')==s['reward_equivalence_id']
                    and s['difficulty'] in {'B','C'} and cold_independent(s)):
                candidates.append(s)
        candidates.sort(key=lambda s: (instant(s['completed_at']), s['attempt_id']))
        e = []
        for s in candidates:
            if s['family_id'] not in {x['family_id'] for x in e}:
                e.append(s)
            if len(e)==2:
                break
        mapped_families={p['family_id'] for p in bindings.get('problems',{}).values() if p.get('volume_id')==vid}
        availability={'V':bool(b and b.get('final_check_id') and (b.get('diagnostic_id') or
            (len(b.get('theory_section_ids',[]))==4 and b.get('core_id') and b.get('lab_id')))),
            'E':bool(b and len(mapped_families)>=2),'R':bool(b and len(mapped_families)>=3)}
        for kind in ('V','E','R'):
            seals[kind+'-'+vid] = {'kind':kind, 'volume_id':vid, 'current_qualified':False,
                'status':'not_qualified' if availability[kind] else 'BLOCKED_CONTENT', 'evidence_ids':[]}
        if b and len(e)==2:
            seals['E-'+vid].update(current_qualified=True, status='qualified', evidence_ids=[s['attempt_id'] for s in e])
            r = next((s for s in candidates if s['family_id'] not in {x['family_id'] for x in e}
                      and instant(s['completed_at'])>=instant(e[1]['completed_at'])
                      and instant(s['completed_at'])-instant(e[0]['completed_at'])>=timedelta(hours=168)), None)
            if r:
                seals['R-'+vid].update(current_qualified=True, status='qualified', evidence_ids=[*seals['E-'+vid]['evidence_ids'], r['attempt_id']])
        if b:
            final = units.get(b.get('final_check_id'))
            reader_ids = [*b.get('theory_section_ids', []), b.get('core_id'), b.get('lab_id')]
            reader = len(b.get('theory_section_ids', []))==4 and all(i in units for i in reader_ids)
            known = vid in diagnostics and len(e)==2
            if final and (reader or known):
                seals['V-'+vid].update(current_qualified=True, status='qualified',
                    evidence_ids=[final['unit_id'], *(reader_ids if reader else [diagnostics[vid]['check_id'], *[s['attempt_id'] for s in e]])])
    by_attempt = {s['attempt_id']:s for s in attempts}
    used_m_families = set()
    assessments = sorted((f['snapshot'] for f in valid if f['fact_type']=='assessment_result'), key=lambda s:(instant(s['completed_at']),s['assessment_id']))
    for bp in DATA['trial_blueprints']['blueprints']:
        if bp['seal'] not in {'K','M'}:
            continue
        bid, kind = bp['id'], bp['seal']
        b = bindings.get('assessments', {}).get(bid)
        seals[bid] = {'kind':kind, 'current_qualified':False, 'status':'not_qualified' if b else 'BLOCKED_CONTENT', 'evidence_ids':[]}
        if not b:
            continue
        if kind=='K':
            vids = [v['id'] for v in DATA['volumes']['volumes'] if v['discipline_id']==bp['discipline_id']]
            if sum(seals['E-'+v]['current_qualified'] for v in vids)<5 or sum(seals['R-'+v]['current_qualified'] for v in vids)<3:
                continue
        for s in assessments:
            if not s['owner_confirmed'] or s['assessment_kind']!=kind or s['variant_id']!=b['variant_id'] or s['publication_version']!=b['publication_version']:
                continue
            rows = s['problem_results']
            expected_weights = [20,25,25,30] if kind=='K' else [15,15,15,15,15,25]
            if [number(r['weight']) for r in rows] != expected_weights or [r['problem_id'] for r in rows]!=b['problem_ids']:
                continue
            if len({r['attempt_id'] for r in rows})!=len(rows) or len({r['problem_id'] for r in rows})!=len(rows):
                continue
            if any(r['independent'] is not True or r['fresh_at_start'] is not True for r in rows):
                continue
            refs = [by_attempt.get(r['attempt_id']) for r in rows]
            if any(a is None or a['problem_id']!=r['problem_id'] or not cold_independent(a, Fraction(0))
                   or abs(weighted(a['parts'],quality_only=True)-number(r['score_fraction']))>Fraction(1,10**12) for a,r in zip(refs,rows)):
                continue
            if [a['difficulty'] for a in refs]!=(['B','B','B','C'] if kind=='K' else ['B']*5+['C']):
                continue
            if [r['is_C'] for r in rows]!=[False]*(len(rows)-1)+[True]:
                continue
            if kind=='M' and {a['discipline_id'] for a in refs[:5]}!={'LA','CA','PR','DS','OD'}:
                continue
            families = {a['family_id'] for a in refs}
            if None in families or len(families)<(3 if kind=='K' else 6):
                continue
            scores=[weighted(a['parts'],quality_only=True) for a in refs]
            if sum(number(r['weight'])*score for r,score in zip(rows,scores))<80 or not rows[-1]['is_C'] or scores[-1]<Fraction(1,2):
                continue
            if kind=='M' and (families & used_m_families or families & set(bindings.get('training_family_ids', []))):
                continue
            if kind=='M':
                used_m_families |= families
            seals[bid].update(current_qualified=True, status='qualified', evidence_ids=[s['assessment_id']])
            break
    for key, seal in seals.items():
        if seal['current_qualified']:
            entitlements['seal:'+key] = DATA['progression']['seals_xp'][seal['kind']]
            evidence['seal:'+key] = seal['evidence_ids']
    xp = sum(entitlements.values())
    metrics = {'level':level_for(xp), **{'seals.'+k:sum(s['current_qualified'] for s in seals.values() if s['kind']==k) for k in 'VERKM'}}
    for discipline in DATA['disciplines']['disciplines']:
        did = discipline['id']
        metrics['discipline_seal.K:'+did] = int(seals.get('K-'+did, {}).get('current_qualified', False))
        metrics['first_fresh_independent_C_ge_80:'+discipline['id']] = int(any(s['discipline_id']==discipline['id'] and s['difficulty']=='C' and cold_independent(s) for s in attempts))
    for kind in ('V','E'):
        metrics['disciplines_with_'+kind] = sum(any(seals[kind+'-'+v['id']]['current_qualified']
            for v in DATA['volumes']['volumes'] if v['discipline_id']==d['id']) for d in DATA['disciplines']['disciplines'])
    rank = [r for r in DATA['ranks']['ranks'] if qualified(r['unlock'],metrics)][-1]
    return {'xp':xp, 'level':metrics['level'], 'chronicles':max(0,(xp-33276)//2000),
            'rank':rank, 'metrics':metrics, 'seals':seals, 'entitlements':entitlements,
            'evidence':evidence, 'qualified_items':[i['id'] for i in ITEMS.values() if qualified(i['unlock'], metrics)],
            'activity_instants':sorted(set(active)), 'ruleset_version':RULESET}


def rhythm(instants, at, zone):
    zone = ZoneInfo(zone)
    today = instant(at).astimezone(zone).date()
    days = {instant(t).astimezone(zone).date() for t in instants if instant(t)<=instant(at)}
    return {'days_per_7':sum(today-timedelta(days=i) in days for i in range(7)), 'goal':5, 'timezone':str(zone)}
