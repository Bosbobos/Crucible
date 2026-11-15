import json
import sys
from pathlib import Path
import pytest
from pydantic import ValidationError
from contracts.content import ContentBundle
from contracts.events import PracticeFact


def test_source_content_is_a_valid_closed_contract():
    sys.path.insert(0,str(Path('scripts').resolve()))
    from bundle_content import bundle
    b=bundle();ContentBundle.model_validate(b)
    b['problems'][0]['execute_shell']='not a supported authoring field'
    with pytest.raises(ValidationError):ContentBundle.model_validate(b)


def test_event_facts_reject_private_text_and_negative_time():
    fact={'problem_id':'P-001','content_release_id':'sha256:example','problem_family_id':'f','primary_skill_id':'s','level':'A','attempt_status':'completed','completed_at':'2026-11-13T12:00:00Z',
          'part_outcomes':[{'part_id':'a','skill_id':'s','outcome':'independent'}],'mathematical_help_used':False,'active_minutes':4,'eligible_for_progress':True,'active_attempt_id':None}
    PracticeFact.model_validate(fact)
    with pytest.raises(ValidationError):PracticeFact.model_validate({**fact,'draft':'private text'})
    with pytest.raises(ValidationError):PracticeFact.model_validate({**fact,'active_minutes':-1})
