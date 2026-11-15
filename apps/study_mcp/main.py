"""Thin MCP adapter. It never calculates progress or connects to storage."""
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote
from uuid import UUID
import httpx
from mcp.server.mcpserver import MCPServer

settings = json.loads(Path(os.environ['CRUCIBLE_MCP_CONFIG']).read_text())
settings['base_url'] = os.getenv('CRUCIBLE_MCP_BASE_URL', settings['base_url'])
server = MCPServer("Crucible", instructions='Read saved work first. Never overwrite the learner draft. Record active tutoring explicitly. Propose corrections for owner approval.')


async def api(service, path, method='GET', body=None):
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.request(method, settings['base_url']+'/api/v1/'+service+path,
                                        headers={'Authorization': 'Bearer '+settings['tokens'][service]}, json=body)
        response.raise_for_status()
        return response.json()


async def context(attempt_id=None):
    attempt = await api('practice', '/attempts/'+str(attempt_id)) if attempt_id else (await api('practice', '/current'))['attempt']
    if not attempt:
        return {'attempt': None, 'incomplete': False, 'missing_sections': []}
    # The attempt snapshot pins the published statement even if content is unavailable.
    result = {'attempt': attempt, 'attempt_revision': attempt['revision'],
              'content_release_id': attempt['problem']['content_release_id'], 'generated_at': datetime.now(timezone.utc).isoformat(),
              'missing_sections': [], 'learning_applied_practice_seq': None,
              'saved_work_only': True, 'help_policy': 'No hidden solutions. Active mathematical dialogue requires begin_tutoring.'}
    try:
        summary = await api('learning', '/progress?at_least_practice_seq='+str(attempt['learning_input_seq']))
        result['learning'] = summary
        result['learning_applied_practice_seq'] = summary['applied_practice_seq']
        if summary['pending']:
            result['missing_sections'].append('fresh_learning_projection')
    except httpx.HTTPError:
        result['missing_sections'].append('learning')
    result['incomplete'] = bool(result['missing_sections'])
    return result


@server.tool(structured_output=True)
async def get_study_context(attempt_id: UUID | None = None) -> dict[str, Any]:
    """Read the latest confirmed attempt, questions, reviews and projection cursor; never reveals hidden help."""
    return await context(attempt_id)


@server.tool(structured_output=True)
async def list_review_queue() -> dict[str, Any]:
    """Read explicit unresolved questions without changing the user's records."""
    return await api('practice', '/review-queue')


@server.tool(structured_output=True)
async def begin_tutoring(attempt_id: UUID, expected_revision: int, command_id: UUID) -> dict[str, Any]:
    """Record mathematical help on an active attempt. Completed work retains its original assistance history."""
    return await api('practice', f'/attempts/{attempt_id}/help', 'POST', {'kind': 'tutoring', 'command_id': str(command_id), 'expected_revision': expected_revision})


@server.tool(structured_output=True)
async def append_review(attempt_id: UUID, expected_revision: int, command_id: UUID, text: str) -> dict[str, Any]:
    """Append a review to an existing revision; a stale review never replaces learner work."""
    return await api('practice', f'/attempts/{attempt_id}/reviews', 'POST', {'text': text, 'command_id': str(command_id), 'expected_revision': expected_revision})


@server.tool(structured_output=True)
async def propose_progress_correction(attempt_id: UUID, expected_revision: int, command_id: UUID,
                                      outcome: Literal['independent', 'assisted', 'reviewed', 'unfinished'], reason: str) -> dict[str, Any]:
    """Propose a factual correction. Only the owner can approve it in the website."""
    return await api('practice', f'/attempts/{attempt_id}/proposals', 'POST', {'outcome': outcome, 'reason': reason, 'command_id': str(command_id), 'expected_revision': expected_revision})


@server.tool(structured_output=True)
async def get_material(topic_id: str, section: Literal['core', 'theory', 'widget'], content_release_id: str) -> dict[str, Any]:
    """Read an addressable published topic. This never exposes protected problem solutions."""
    return await api('content', '/topics/'+quote(topic_id, safe='')+'/'+section+'?release_id='+quote(content_release_id, safe=''))


@server.tool(structured_output=True)
async def get_progress_summary() -> dict[str, Any]:
    """Read derived progress and its source cursor; not a measure of admission probability."""
    return await api('learning', '/progress')


@server.tool(structured_output=True)
async def request_export(command_id: UUID) -> dict[str, Any]:
    """Queue a portable export; ordinary tutoring does not depend on report processing."""
    return await api('reports', '/jobs', 'POST', {'command_id': str(command_id)})


@server.tool(structured_output=True)
async def get_job(job_id: UUID) -> dict[str, Any]:
    """Read export status and its manifest."""
    return await api('reports', f'/jobs/{job_id}')


@server.resource('study://attempts/{attempt_id}')
async def attempt_resource(attempt_id: str) -> str:
    return json.dumps(await context(UUID(attempt_id)), ensure_ascii=False)


if __name__ == '__main__':
    server.run(transport='stdio')
