"""Проверяем настоящий Docker stdio entrypoint без изменения учебных фактов."""
import asyncio
import json
import os
from pathlib import Path
from mcp import Client, StdioServerParameters
from ops import evidence


async def check():
    # Клиент SDK запускает ту же обёртку, которую использует desktop/IDE host.
    params=StdioServerParameters(command=str(Path.cwd()/'scripts/study-mcp'),
                                env=dict(os.environ),cwd=str(Path.cwd()))
    # Жизненный цикл клиента включает initialize и корректное закрытие stdin.
    async with Client(params) as client:
        # Список проверяет реальное согласование JSON-RPC и capabilities.
        listing=await client.list_tools()
        names=sorted(tool.name for tool in listing.tools)
        # Выполняем только чтение через scoped credentials самого MCP-сервера.
        result=await client.call_tool('get_progress_summary',{})
        if result.is_error:raise RuntimeError('MCP get_progress_summary завершился ошибкой')
        # Сохраняем только факт проверки, не весь личный учебный контекст.
        report={'transport':'Docker stdio, no TTY','tools':names,'read_call':'passed',
                'desktop_host_registered':False,'mutating_calls':0}
        evidence('mcp-container',report)
        print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    # Сам проверяющий клиент также исполняется в операторском контейнере.
    asyncio.run(check())
