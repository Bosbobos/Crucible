import ast
from pathlib import Path


def test_no_cross_domain_imports_or_shared_orm():
    services={p.name for p in Path('apps').iterdir() if p.is_dir() and p.name!='web'}
    for service in services:
        for path in (Path('apps')/service).rglob('*.py'):
            for node in ast.walk(ast.parse(path.read_text())):
                modules=[node.module or ''] if isinstance(node,ast.ImportFrom) else [n.name for n in node.names] if isinstance(node,ast.Import) else []
                assert all(m.split('.')[0] not in services-{service} for m in modules),path
    for path in Path('packages').rglob('*.py'):
        assert not any(name in path.read_text() for name in ['from sqlalchemy','class Attempt','class DailyPlan'])


def test_every_service_has_own_migrations_and_config():
    for name in ['content','practice','learning','reports']:
        assert (Path('migrations')/name/'001_initial.sql').is_file()
