"""Deterministic policy v1. All pedagogical calculations live here."""
import hashlib
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

POLICY_VERSION = 'heuristic-v1'
SCORES = {'independent': 1.0, 'assisted': 0.5, 'reviewed': 0.0, 'unfinished': 0.0}


def calculate(facts, catalog, at, timezone='Europe/Moscow'):
    zone = ZoneInfo(timezone)
    today = at.astimezone(zone).date()
    by_skill = defaultdict(list)
    for fact in facts:
        if not fact.get('eligible_for_progress') or fact['attempt_status'] != 'completed':
            continue
        per_skill = defaultdict(list)
        for part in fact['part_outcomes']:
            score = SCORES[part['outcome']]
            if fact['mathematical_help_used']:
                score = min(score, 0.5)
            per_skill[part['skill_id']].append(score)
        for skill, scores in per_skill.items():
            by_skill[skill].append({**fact, 'score': sum(scores)/len(scores),
                'day': datetime.fromisoformat(fact['completed_at']).astimezone(zone).date()})
    skills = sorted({p['primary_skill_id'] for p in catalog} | set(by_skill))
    result = []
    for skill in skills:
        history = sorted(by_skill[skill], key=lambda f: (f['completed_at'], f.get('attempt_id', '')))
        distinct = {}
        for f in history:
            distinct[f['problem_family_id']] = f
        window = sorted(distinct.values(), key=lambda f: f['completed_at'])[-5:]
        weakness = 1-sum(f['score'] for f in window)/len(window) if window else 1.0
        streak, due, successes = 0, None, []
        for f in history:
            if f['score'] == 1:
                streak += 1
                interval = [4, 10, 25, 50][min(streak-1, 3)]
                successes.append(f)
            else:
                streak = 0
                interval = 3 if f['score'] > 0 else 1
            due = f['day']+timedelta(days=interval)
        transfer = any(a['problem_family_id'] != b['problem_family_id'] and a['day'] != b['day']
                       and ('B' in [a['level'], b['level']]) for a in successes for b in successes)
        bank_families = {p['problem_family_id'] for p in catalog if p['primary_skill_id'] == skill}
        state = 'not_seen' if not history else 'transfer_confirmed' if transfer else 'practicing' if successes else 'learning'
        if history and len(bank_families) < 2:
            state = 'insufficient_bank'
        if due and due <= today:
            state = 'review_due'
        label=next((p.get('skill_title') for p in catalog if p['primary_skill_id']==skill and p.get('skill_title')),skill)
        result.append({'skill_id': skill, 'skill_title':label, 'state': state, 'transfer_confirmed': transfer,
                       'weakness': weakness, 'due_date': str(due) if due else None,
                       'attempt_count': len(history), 'distinct_families': len(distinct),
                       'bank_families': len(bank_families), 'streak': streak,
                       'last_level': history[-1]['level'] if history else None})
    return result


def make_plan(facts, catalog, skills, at, n=3, timezone='Europe/Moscow', seed='0', weights=None):
    today = at.astimezone(ZoneInfo(timezone)).date()
    weights = weights or {}
    seen = {f['problem_id'] for f in facts}
    seen_families = {f['problem_family_id'] for f in facts}
    last_seen = {p['id']: max((f.get('completed_at') or '0000' for f in facts if f['problem_id'] == p['id']), default='0000') for p in catalog}
    by_skill = {s['skill_id']: s for s in skills}
    allowed = [p for p in catalog if p['pool'] == 'train' and weights.get(p['primary_skill_id'], 1) > 0]
    tie = lambda p: hashlib.sha256((seed+p['id']).encode()).hexdigest()
    selected, reasons, review_due_ids = [], {}, set()
    active = [f for f in facts if f['attempt_status'] in ['running', 'paused']]
    if active:
        f = sorted(active, key=lambda f: f.get('source_seq', 0))[-1]
        p = next((p for p in catalog if p['id'] == f['problem_id']), None)
        if p:
            selected.append(p)
            reasons[p['id']] = 'Продолжить текущую попытку'
    new = [p for p in allowed if p['id'] not in seen]
    due = sorted((s for s in skills if s['due_date'] and s['due_date'] <= str(today)),
                 key=lambda s: (s['due_date'], -s['weakness'], -weights.get(s['skill_id'], 1), s['skill_id']))
    reserve_new = 1 if n >= 3 and new else 0
    processed_due = 0
    for s in due:
        if len(selected) >= n-reserve_new:
            break
        candidates = [p for p in allowed if p['primary_skill_id'] == s['skill_id'] and p not in selected]
        if not candidates:
            continue
        candidates.sort(key=lambda p: (p['id'] in seen, p['problem_family_id'] in seen_families,
                                      p['level'] != s['last_level'], last_seen[p['id']], tie(p)))
        p = candidates[0]
        selected.append(p)
        reasons[p['id']] = 'Повторение навыка: другой вариант' if p['id'] not in seen else 'Повторение навыка: свежих вариантов нет'
        review_due_ids.add(p['id'])
        processed_due += 1
    def priority(p):
        s = by_skill[p['primary_skill_id']]
        return weights.get(s['skill_id'], 1)*s['weakness']
    while len(selected) < n:
        candidates = [p for p in new if p not in selected]
        if not candidates:
            break
        used = {p['section'] for p in selected}
        candidates.sort(key=lambda p: (-priority(p), p['section'] in used, p['level'] != 'A', tie(p)))
        p = candidates[0]
        selected.append(p)
        reasons[p['id']] = 'Новая практика: приоритет × затруднение'
    return {'items': [{**p, 'reason': reasons[p['id']], 'review_due':p['id'] in review_due_ids,'factors': {'weight': weights.get(p['primary_skill_id'], 1),
                      'weakness': by_skill[p['primary_skill_id']]['weakness']}} for p in selected],
            'requested_count': n, 'deferred_reviews': max(0, len(due)-processed_due),
            'shortfall_reason': 'Недостаточно новых допустимых задач; контрольный резерв исключён' if len(selected) < n else None,
            'policy_version': POLICY_VERSION, 'date': str(today), 'timezone': timezone, 'seed': seed}
