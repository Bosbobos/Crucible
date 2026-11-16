"""Boundary DTO: practice передаёт минимальный полный снимок без текста решения."""
import json
from datetime import datetime
from pathlib import Path
from jsonschema import Draft202012Validator,FormatChecker


def validate_evidence(fact):
    schemas={'learning_unit_completed':'learning-unit-snapshot','diagnostic_result':'diagnostic-snapshot','assessment_result':'assessment-snapshot'}
    if (not {'fact_type','status','snapshot'}<=set(fact) or set(fact)-{'fact_type','status','snapshot','reason'}
            or fact['fact_type'] not in schemas or fact['status'] not in ('confirmed','revoked')):
        raise ValueError('Неверный контракт учебного свидетельства')
    json.dumps(fact,allow_nan=False)
    schema=json.loads((Path(__file__).with_name('schemas')/'character'/(schemas[fact['fact_type']]+'.schema.json')).read_text())
    if list(Draft202012Validator(schema,format_checker=FormatChecker()).iter_errors(fact['snapshot'])):
        raise ValueError('Некорректный полный snapshot')
    at=datetime.fromisoformat(fact['snapshot']['completed_at'].replace('Z','+00:00'))
    if at.tzinfo is None:raise ValueError('Нужен timestamp с timezone')
    if fact['status']=='revoked' and not fact.get('reason','').strip():raise ValueError('Нужна причина аннулирования')
    return fact


def attempt_snapshot(doc):
    metadata = doc['problem'].get('reward_metadata')
    if not metadata or doc['state']!='completed' or not doc.get('rpg_assessment_confirmed'):
        return None
    source_parts = {p['id']:p for p in doc['problem']['parts']}
    return {'fact_type':'attempt_result', 'status':'confirmed', 'snapshot':{
        'attempt_id':doc['id'], 'problem_id':doc['problem']['id'],
        'content_version':doc['problem']['content_release_id'], 'rubric_version':metadata['rubric_version'],
        'reward_equivalence_id':metadata['reward_equivalence_id'], 'family_id':metadata['family_id'],
        'discipline_id':metadata['discipline_id'], 'mapped_volume_id':metadata['mapped_volume_id'],
        'mapping_version':metadata['mapping_version'], 'difficulty':doc['problem']['level'],
        'parts':[{'part_id':p['part_id'], 'weight':source_parts[p['part_id']].get('weight',1),
                  'outcome':'skipped' if p['outcome']=='unfinished' else p['outcome'],
                  'quality':p.get('quality',1 if p['outcome'] in ('independent','assisted') else 0),
                  'note_saved':bool(doc.get('reflection','').strip()) if p['outcome']=='reviewed' else False}
                 for p in doc['part_outcomes']],
        'began_at':doc['started_at'], 'completed_at':doc['completed_at'], 'source_sequence':doc['revision'],
        'provenance':{'assessment_source':'self_assessment','owner_confirmed':True},
        'freshness':doc.get('reward_freshness',{'statement_seen_before_attempt':None,
            'solution_seen_before_attempt':None,'worked_example_seen_before_attempt':None}),
        'help_during_attempt':any(h['mathematical'] and not h.get('retracted') for h in doc['help']) or any(p['outcome']=='assisted' for p in doc['part_outcomes']),
        'review_context':doc.get('reward_review_context')}}
