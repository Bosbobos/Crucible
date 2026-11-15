import copy
import os
import sys
from pathlib import Path
import pytest
from test_workflow import client,cmd,clear_active

pytestmark=[pytest.mark.integration,pytest.mark.skipif(os.getenv('CRUCIBLE_INTEGRATION')!='1',reason='Requires synthetic stack')]


def test_release_activation_preserves_pinned_attempt_and_can_return_to_previous_release():
    sys.path.insert(0,str(Path('scripts').resolve()))
    from bundle_content import bundle
    c=client();author=client('operator');clear_active(c)
    original=bundle();first=author.post('content/releases',cmd(bundle=original))['release_id']
    a=c.post('practice/attempts',cmd(problem_id=original['problems'][0]['id'],content_release_id=first))
    modified=copy.deepcopy(original);modified['problems'][0]['statement']+='\n\nSynthetic publication contract check.'
    try:
        second=author.post('content/releases',cmd(bundle=modified))['release_id']
        assert second!=first
        assert c.get('content/catalog')['content_release_id']==second
        saved=c.get('practice/attempts/'+a['id'])
        assert saved['problem']['content_release_id']==first
        assert 'Synthetic publication' not in saved['problem']['statement']
    finally:
        restored=author.post('content/releases',cmd(bundle=original))
        assert c.get('content/catalog')['content_release_id']==first
        current=c.get('practice/attempts/'+a['id'])
        assert c.request('PATCH','practice/attempts/'+a['id'],cmd(expected_revision=current['revision'],state='abandoned')).status_code==200
