"""Read educational fields from an Obsidian vault. Never executes JS or imports user history."""
import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import unquote

import yaml


class LiteralReader:
    """Small data-only reader for the literal second argument of dv.view.

    Functions, interpolation, identifiers, calls and prototype keys are rejected.
    String.raw templates preserve LaTeX exactly. No eval/exec/Function is used.
    """
    def __init__(self, text):
        self.text, self.pos = text, 0

    def ws(self):
        while self.pos < len(self.text) and self.text[self.pos].isspace():
            self.pos += 1

    def value(self):
        self.ws()
        raw = self.text.startswith('String.raw`', self.pos)
        if raw:
            self.pos += len('String.raw')
        char = self.text[self.pos]
        if char in "'\"`":
            self.pos += 1
            output = ''
            while self.pos < len(self.text):
                char = self.text[self.pos]
                self.pos += 1
                # The delimiter is stored independently of escaped contents.
                if char == self.delimiter:
                    if raw and '${' in output:
                        raise ValueError('Template interpolation is not content data')
                    return output
                if char == '\\' and not raw:
                    following = self.text[self.pos]
                    self.pos += 1
                    output += {'n': '\n', 'r': '\r', 't': '\t'}.get(following, following)
                elif char == '\\' and raw and self.pos < len(self.text) and self.text[self.pos] == '`':
                    output += '\\`'
                    self.pos += 1
                else:
                    output += char
            raise ValueError('Unterminated string')
        if char == '{':
            self.pos += 1
            result = {}
            while True:
                self.ws()
                if self.text[self.pos] == '}':
                    self.pos += 1
                    return result
                if self.text[self.pos] in "'\"":
                    key = self.read()
                else:
                    match = re.match(r'[A-Za-z_][A-Za-z_0-9]*', self.text[self.pos:])
                    if not match:
                        raise ValueError('Expected literal property name')
                    key = match[0]
                    self.pos += len(key)
                if key in ('__proto__', 'prototype', 'constructor') or key in result:
                    raise ValueError('Unsafe or duplicate key')
                self.ws()
                if self.text[self.pos] != ':':
                    raise ValueError('Expected colon')
                self.pos += 1
                result[key] = self.read()
                self.ws()
                if self.text[self.pos] == ',':
                    self.pos += 1
                elif self.text[self.pos] != '}':
                    raise ValueError('Expected comma')
        if char == '[':
            self.pos += 1
            result = []
            while True:
                self.ws()
                if self.text[self.pos] == ']':
                    self.pos += 1
                    return result
                result.append(self.read())
                self.ws()
                if self.text[self.pos] == ',':
                    self.pos += 1
                elif self.text[self.pos] != ']':
                    raise ValueError('Expected comma')
        match = re.match(r'-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|true\b|false\b|null\b', self.text[self.pos:])
        if not match:
            raise ValueError('Only literal data is accepted')
        self.pos += len(match[0])
        return json.loads(match[0])

    def read(self):
        self.ws()
        old = getattr(self, 'delimiter', None)
        start = self.pos + (len('String.raw') if self.text.startswith('String.raw`', self.pos) else 0)
        self.delimiter = self.text[start]
        try:
            return self.value()
        finally:
            self.delimiter = old


def frontmatter(path):
    raw = path.read_text()
    header, body = raw.split('---', 2)[1:]
    return yaml.safe_load(header), body.strip(), raw


def callouts(raw, kind):
    pattern = r'^> \[!' + re.escape(kind) + r'\][+-]?[^\n]*\n((?:>[^\n]*(?:\n|$))*)'
    return ['\n'.join(re.sub(r'^> ?', '', line) for line in match.splitlines()).strip()
            for match in re.findall(pattern, raw, re.M)]


def exercise_data(code):
    start = re.search(r'\{\s*primer\s*:', code)
    if not start or '/extra/widgets/lab' not in code:
        raise ValueError('Unrecognized Dataview block')
    reader = LiteralReader(code[start.start():])
    result = reader.read()
    if reader.text[reader.pos:].strip() not in (')', ');'):
        raise ValueError('Unexpected executable expression')
    if result['kind'] not in ('ask', 'try', 'recall', 'sim', 'moves', 'bank'):
        raise ValueError('Unsupported exercise kind')
    return result


TOPIC_IDS = {
    'Матожидание, дисперсия и индикаторы': 'vault-expectation',
    'Условная вероятность и формула Байеса': 'vault-bayes',
    'Уравнения первого порядка': 'vault-first-order',
    'Карта приёмов': 'vault-methods',
}


def topic_link(target):
    name, _, anchor = target.partition('#')
    name = Path(unquote(name)).stem
    if name in TOPIC_IDS:
        # Route through the app, preserving the source's block reference as metadata.
        return 'study-material:' + TOPIC_IDS[name] + ('#' + anchor if anchor else '')
    return None


def adapt_markdown(text, card_ids, exercises=None):
    # Preserve educational text; navigation/CSS/Obsidian scripting are presentation data.
    text = re.sub(r'^> \[!hero\][^\n]*\n', '', text, flags=re.M)
    text = re.sub(r'^> .*\[← Тренажёр\].*(?:\n|$)', '', text, flags=re.M)
    text = re.sub(r'^> `[^\n]*`[^\n]*(?:\n|$)', '', text, flags=re.M)
    text = re.sub(r'</?span\b[^>]*>', '', text)
    text = re.sub(r'^\^([\w-]+)\s*$', lambda match:'\n```vault-anchor\n'+match[1]+'\n```\n', text, flags=re.M)

    def fence(match):
        language, code = match.group(1), match.group(2)
        if language.strip() != 'dataviewjs':
            return match.group(0)
        item = exercise_data(code)
        if item['kind'] == 'bank':
            selected = [card['id'] for card in card_ids if card['type'] in item['types']]
            return '\n' + ' · '.join('[' + id + '](study-problem:' + id + ')' for id in selected) + '\n'
        if exercises is not None:
            exercises.append(item)
        if item['kind'] == 'sim':
            return '\n[Открыть лабораторию](study-lab:vault-indicators)\n'
        return '\n```vault-exercise\n' + json.dumps(item, ensure_ascii=False) + '\n```\n'
    text = re.sub(r'```([^\n]*)\n(.*?)```', fence, text, flags=re.S)

    def wiki(match):
        target, _, alias = match.group(2).partition('|')
        label = alias or target.split('#')[0].split('/')[-1]
        href = topic_link(target)
        if href:
            return '[' + label + '](' + href + ')'
        problem = re.match(r'(P-\d{3})\b', target)
        if problem:
            return '[' + label + '](study-problem:' + problem[1] + ')'
        # Keep external bibliographic references without inventing a target document.
        return label + ' *(ссылка в исходном vault)*'
    text = re.sub(r'(!?)\[\[([^\]]+)\]\]', wiki, text)

    def local_link(match):
        label, target = match.group(1), match.group(2)
        if re.match(r'^(https?:|study-)', target):
            return match.group(0)
        href = topic_link(target)
        return '[' + label + '](' + href + ')' if href else label + ' *(ссылка в исходном vault)*'
    text = re.sub(r'\[([^\]\n]+)\]\(([^\)\n]+)\)', local_link, text)
    return text.strip()


def collect(source):
    types = {item['id']: item for item in json.loads((source/'extra/types.json').read_text())['types']}
    cards = []
    for path in sorted((source/'Задачи').glob('P-*.md')):
        meta, body, raw = frontmatter(path)
        problem = callouts(body, 'problem')
        hints = callouts(body, 'idea')
        solution, remember = callouts(body, 'solution'), callouts(body, 'method')
        if len(problem) != 1 or len(hints) != 3 or len(solution) != 1 or len(remember) != 1:
            raise ValueError('Incomplete source card ' + meta['id'])
        # The first paragraph of the problem callout is its source type/level badge.
        statement = re.sub(r'^`[^\n]+`[^\n]*\n\s*', '', problem[0]).strip()
        cards.append({'id': meta['id'], 'type': meta['type'], 'metadata': meta,
                      'statement': statement, 'hints': hints, 'solution': solution[0], 'remember': remember[0],
                      'source_file': str(path.relative_to(source)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    topics = {}
    exercises = []
    for path in sorted((source/'Ядро темы').glob('*.md')):
        meta, body, raw = frontmatter(path)
        topic_id = TOPIC_IDS[path.stem]
        topics[topic_id] = {'id': topic_id, 'title': path.stem,
                            'widget': 'vault-indicators' if topic_id == 'vault-expectation' else None,
                            'skill_ids': meta.get('types', []), 'prerequisites': [],
                            'core': '# ' + path.stem + '\n\n' + adapt_markdown(body, cards, exercises), 'theory': None,
                            'provenance': {'kind': 'obsidian_vault', 'source_file': str(path.relative_to(source)),
                                           'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                           'adaptation': 'Formatting and data-only widget conversion; no new educational prose'}}
    problems = []
    for card in cards:
        meta = card['metadata']; type_info = types[card['type']]
        primer = type_info.get('primer')
        topic_id = TOPIC_IDS.get(Path(primer).stem) if primer else None
        parts = meta.get('parts', 1)
        problems.append({'schema_version': 1, 'id': card['id'], 'title': meta['title'],
                         'primary_skill_id': card['type'], 'skill_title': type_info['title'], 'secondary_skill_ids': [],
                         # No unverified independent-family assignments or automatic v2 aliases.
                         'problem_family_id': 'unclassified-' + card['type'], 'family_reviewed': False,
                         'level': meta['level'], 'level_reason': 'Уровень из исходной карточки',
                         'pool': 'train', 'status': 'published', 'section': meta['section'], 'topic_id': topic_id,
                         'estimated_minutes': None, 'content_language': 'en', 'revision': 1, 'prerequisites': [],
                         'parts': [{'id': chr(97+i), 'skill_id': card['type'], 'title': 'Результат' if parts == 1 else 'Часть ('+chr(97+i)+')'} for i in range(parts)],
                         'provenance': {'kind': 'obsidian_vault', 'legacy_id': card['id'], 'legacy_type': card['type'],
                                        'source_reference': meta.get('source'), 'source_file': card['source_file'],
                                        'source_sha256': card['sha256'], 'mathematical_review': 'not_performed_on_import'},
                         'review': {'status': 'source_preserved', 'method': 'Educational fields extracted from source; structure and checksums checked; not an expert mathematical review', 'reviewed_at': '2026-11-14'},
                         **{field: adapt_markdown(card[field], cards) for field in ('statement', 'solution', 'remember')},
                         'hints': [adapt_markdown(hint, cards) for hint in card['hints']],
                         'completion_criteria': '', 'typical_errors': [], 'theory_sections': [topic_id+'/core'] if topic_id else []})
    return {'schema_version': 1, 'problems': problems, 'topics': topics}, cards, exercises


def write_bundle(source, output):
    bundle, cards, exercises = collect(source)
    from contracts.content import ContentBundle
    ContentBundle.model_validate(bundle)
    output.mkdir(parents=True, exist_ok=False)
    (output/'problems').mkdir(); (output/'topics').mkdir()
    for problem in bundle['problems']:
        (output/'problems'/(problem['id']+'.yaml')).write_text(yaml.safe_dump(problem, allow_unicode=True, sort_keys=False, width=1000))
    for topic_id, topic in bundle['topics'].items():
        folder = output/'topics'/topic_id; folder.mkdir()
        meta = {k:v for k,v in topic.items() if k not in ('core', 'theory')}
        (folder/'metadata.yaml').write_text(yaml.safe_dump(meta, allow_unicode=True, sort_keys=False))
        (folder/'core.md').write_text(topic['core']+'\n')
    manifest = {'source': 'existing Obsidian vault', 'schema_version': 1, 'cards': len(cards), 'notes': len(bundle['topics']),
                'interactive_blocks': len(exercises), 'types_with_cards': len({c['type'] for c in cards}),
                'history_imported': False, 'new_educational_text_generated': False,
                'families': 'Unclassified: grouped conservatively by original type; no transfer credit inferred',
                'files': [{'source_file': c['source_file'], 'source_sha256': c['sha256']} for c in cards] + [t['provenance'] for t in bundle['topics'].values()]}
    (output/'vault-import.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, required=True, help='A NEW output directory; existing content is never overwritten')
    args = parser.parse_args()
    manifest = write_bundle(args.source, args.output)
    print(json.dumps({k:v for k,v in manifest.items() if k != 'files'}, ensure_ascii=False, indent=2))
