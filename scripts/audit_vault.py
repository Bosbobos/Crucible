"""Read-only inventory and byte-preserving private backup; never executes legacy JS."""
import argparse
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path
import yaml


def audit(source: Path, destination: Path):
    source = source.resolve(strict=True)
    destination.mkdir(parents=True, exist_ok=False)
    records, cards = [], []
    for item in sorted(source.rglob('*')):
        if not item.is_file():
            continue
        if item.is_symlink():
            raise ValueError(f'Symlink requires explicit review: {item.name}')
        relative = item.relative_to(source)
        data = item.read_bytes()
        target = destination / 'source' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        assert hashlib.sha256(target.read_bytes()).hexdigest() == digest
        records.append({'path': str(relative), 'bytes': len(data), 'sha256': digest})
        if relative.parts[0] == 'Задачи' and item.suffix == '.md':
            text = data.decode('utf-8')
            meta = yaml.safe_load(text.split('---', 2)[1])
            cards.append({'path': str(relative), 'metadata': meta, 'sha256': digest})
    events = json.loads((source/'extra/log.json').read_text())['events']
    types = json.loads((source/'extra/types.json').read_text())['types']
    current = json.loads((source/'extra/current.json').read_text())
    report = {'schema_version': 1, 'files': records, 'cards': cards,
              'counts': {'files': len(records), 'cards': len(cards), 'types': len(types),
                         'populated_types': len({c['metadata']['type'] for c in cards}),
                         'events': len(events), 'minutes': sum(e.get('minutes', 0) for e in events)},
              'current': current, 'levels': dict(Counter(c['metadata']['level'] for c in cards)),
              'not_imported': ['Control PDFs copied without extracting their content',
                               'localStorage not available; no timer duration inferred'],
              'events': events, 'types': types}
    (destination/'inventory.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    print(json.dumps(report['counts'], ensure_ascii=False))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    audit(args.source, args.destination)
