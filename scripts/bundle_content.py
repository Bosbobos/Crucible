import json
from pathlib import Path
import yaml


def bundle(root=Path('content')):
    problems = [yaml.safe_load(p.read_text()) for p in sorted((root/'problems').glob('*.yaml'))]
    topics = {}
    for p in sorted((root/'topics').glob('*/metadata.yaml')):
        meta = yaml.safe_load(p.read_text())
        topics[meta['id']] = {**meta, **{section: (p.parent/(section+'.md')).read_text() if (p.parent/(section+'.md')).exists() else None for section in ['core','theory']}}
    return {'schema_version': 1, 'problems': problems, 'topics': topics}


if __name__ == '__main__':
    print(json.dumps(bundle(), ensure_ascii=False))
