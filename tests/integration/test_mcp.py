import asyncio
import json
import os
import uuid
import sys
from pathlib import Path
import pytest
from mcp import Client, StdioServerParameters
from test_workflow import client,cmd,clear_active,wait_progress

pytestmark=[pytest.mark.integration,pytest.mark.skipif(os.getenv('CRUCIBLE_INTEGRATION')!='1',reason='Requires running stack')]


def test_real_stdio_mcp_client():
    # A clean deployment intentionally has no synthetic attempt history.
    c=client();clear_active(c)
    catalog=c.get('content/catalog');problem=catalog['problems'][0]
    started=c.post('practice/attempts',cmd(problem_id=problem['id'],content_release_id=catalog['content_release_id']))
    a=c.post('practice/attempts/'+started['id']+'/complete',cmd(expected_revision=started['revision'],
             part_outcomes=[{'part_id':part['id'],'outcome':'independent'} for part in started['problem']['parts']]))
    wait_progress(c,a['learning_input_seq'])
    async def exercise():
        root=Path.cwd()
        params=StdioServerParameters(command=sys.executable,args=['-m','study_mcp.main'],
            env={**os.environ,'CRUCIBLE_MCP_CONFIG':str(root/Path(os.getenv('CRUCIBLE_TEST_CONFIG_DIR','.secrets'))/'mcp.json')},cwd=str(root))
        async with Client(params) as mcp:
            listing=await mcp.list_tools()
            names={t.name for t in listing.tools}
            assert {'get_study_context','list_review_queue','begin_tutoring','append_review','propose_progress_correction'}<=names
            result=await mcp.call_tool('get_study_context',{'attempt_id':a['id']})
            assert not result.is_error
            data=result.structured_content
            assert data['attempt_revision']>=1 and data['content_release_id'].startswith('sha256:')
            assert 'solution' not in data['attempt']['problem']
            command={'attempt_id':a['id'],'expected_revision':data['attempt_revision'],'command_id':str(uuid.uuid4()),'text':'Synthetic MCP review: compare the image and the kernel.'}
            first=await mcp.call_tool('append_review',command)
            second=await mcp.call_tool('append_review',command)
            assert not first.is_error and first.structured_content==second.structured_content
            assert c.get('practice/attempts/'+a['id'])['draft']==data['attempt']['draft']
    asyncio.run(exercise())
