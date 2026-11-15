"""Операторский netfilter probe. Docker API и файлов хоста внутри него нет."""
import argparse
import hashlib
import json
import shlex
import signal
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

CHAIN = 'CRUCIBLE_EGRESS'
TARGETS = {
    'web': [('content', 8000), ('practice', 8000), ('learning', 8000), ('reports', 8000)],
    'content': [('postgres', 5432), ('rabbitmq', 5672)],
    'practice': [('postgres', 5432), ('rabbitmq', 5672), ('content', 8000)],
    'learning': [('postgres', 5432), ('rabbitmq', 5672), ('redis', 6379)],
    'reports': [('postgres', 5432), ('rabbitmq', 5672), ('practice', 8000), ('learning', 8000)],
}
DENIED = {'web': [('postgres', 5432), ('redis', 6379)],
          'content': [('practice', 8000), ('learning', 8000)],
          'practice': [('redis', 6379), ('learning', 8000)],
          'learning': [('practice', 8000), ('content', 8000)],
          'reports': [('content', 8000)]}


def run(*args, input=None, check=True):
    result = subprocess.run(args, input=input, text=True, capture_output=True, timeout=15)
    if check and result.returncode:
        raise RuntimeError('Ошибка netfilter: '+result.stderr.strip()[:300])
    return result


def iptables(*args, check=True):
    return run('iptables', '-w', '5', *args, check=check)


def snapshot():
    chain = iptables('-S', CHAIN, check=False)
    output = iptables('-S', 'OUTPUT').stdout.splitlines()
    jumps = [(index, line) for index, line in enumerate(output[1:], 1)
             if CHAIN in shlex.split(line)]
    return {'chain': chain.stdout.splitlines() if chain.returncode == 0 else None, 'jumps': jumps}


def restore(saved):
    # Only our chain and its OUTPUT references change; other rules are untouched.
    for _, rule in snapshot()['jumps']:
        iptables('-D', *shlex.split(rule)[1:])
    if saved['chain'] is None:
        iptables('-F', CHAIN, check=False)
        iptables('-X', CHAIN, check=False)
    else:
        rules = [line for line in saved['chain'] if line.startswith('-A ')]
        run('iptables-restore', '--wait', '5', '--noflush',
            input='*filter\n:'+CHAIN+' - [0:0]\n-F '+CHAIN+'\n'+'\n'.join(rules)+'\nCOMMIT\n')
    for index, rule in saved['jumps']:
        tokens = shlex.split(rule)
        iptables('-I', 'OUTPUT', str(index), *tokens[2:])


def policy(metadata, source, *, build_rules=True):
    containers = {}
    projects = set()
    for item in metadata:
        labels = item['Config']['Labels']
        name = labels.get('com.docker.compose.service')
        if name in containers:
            raise ValueError('Нужен один контейнер каждого сервиса')
        containers[name] = item
        projects.add(labels.get('com.docker.compose.project'))
    if len(projects) != 1 or None in projects:
        raise ValueError('Контейнеры должны принадлежать одному Compose project')
    targets = list(TARGETS[source])
    if 'standby' in containers and source != 'web':
        targets += [('standby', 5432), ('rabbitmq2', 5672), ('rabbitmq3', 5672)]
    networks = {name: {network: data['IPAddress'] for network, data in
                      item['NetworkSettings']['Networks'].items() if data['IPAddress']}
                for name, item in containers.items()}
    if not build_rules:
        return containers, networks, targets, []
    rules = [['-o', 'lo', '-j', 'ACCEPT'],
             ['-m', 'conntrack', '--ctstate', 'ESTABLISHED,RELATED', '-j', 'ACCEPT']]
    for target, port in targets:
        addresses = sorted(set(networks[target].values()))
        if not addresses:
            raise ValueError('Нет активного адреса '+target)
        rules += [['-d', ip, '-p', 'tcp', '--dport', str(port), '-j', 'ACCEPT'] for ip in addresses]
    rules.append(['-j', 'REJECT'])
    return containers, networks, targets, rules


def apply(rules):
    text = '*filter\n:'+CHAIN+' - [0:0]\n-F '+CHAIN+'\n'
    text += '\n'.join(shlex.join(['-A', CHAIN, *rule]) for rule in rules)+'\nCOMMIT\n'
    run('iptables-restore', '--wait', '5', '--noflush', input=text)
    # Keep exactly one jump, first in OUTPUT, without flushing unrelated rules.
    for _, line in snapshot()['jumps']:
        iptables('-D', *shlex.split(line)[1:])
    iptables('-I', 'OUTPUT', '1', '-j', CHAIN)


def verify(rules):
    state = snapshot()
    actual = [line for line in state['chain'] or [] if line.startswith('-A ')]
    expected_jump = [(1, '-A OUTPUT -j '+CHAIN)]
    return (state['jumps'] == expected_jump and len(actual) == len(rules) and
            all(iptables('-C', CHAIN, *rule, check=False).returncode == 0 for rule in rules))


def probe(networks, source, target, port):
    shared = sorted(set(networks[source]) & set(networks[target]))
    address = networks[target][shared[0]] if shared else sorted(networks[target].values())[0]
    with socket.socket() as connection:
        connection.settimeout(2)
        allowed = connection.connect_ex((address, port)) == 0
    return allowed, bool(shared)


def reject_packets():
    lines = iptables('-nvxL', CHAIN).stdout.splitlines()
    return sum(int(parts[0]) for line in lines if len(parts := line.split()) > 2 and parts[2] == 'REJECT')


def application_status():
    config = json.loads(Path('/run/secrets/operator').read_text())
    request = Request('http://127.0.0.1:8000/api/v1/learning/progress',
                      headers={'Authorization': 'Bearer '+config['tokens']['learning']})
    try:
        with urlopen(request, timeout=12) as response:
            return response.status
    except HTTPError as error:
        return error.code


def test(networks, source, targets):
    checks = []
    for target, port in targets:
        allowed, shared = probe(networks, source, target, port)
        checks.append({'source': source, 'target': target, 'port': port, 'allowed': allowed, 'expected': True})
        if not allowed:
            raise RuntimeError('Разрешённый TCP-путь недоступен: '+source+' → '+target)
    for target, port in DENIED[source]:
        before = reject_packets()
        allowed, shared = probe(networks, source, target, port)
        after = reject_packets()
        checks.append({'source': source, 'target': target, 'port': port, 'allowed': allowed,
                       'expected': False, 'shared_network': shared, 'reject_packets_delta': after-before})
        if allowed or (shared and after <= before):
            raise RuntimeError('Запрещённый путь не подтверждён netfilter: '+source+' → '+target)
    if source == 'learning':
        before = application_status()
        if before != 200:
            raise RuntimeError('Learning progress недоступен до блокировки')
        blocked_rules = [['-d', address, '-p', 'tcp', '--dport', '5432', '-j', 'REJECT']
                         for name in ['postgres', 'standby'] if name in networks
                         for address in networks[name].values()]
        try:
            for rule in blocked_rules:
                iptables('-I', CHAIN, '1', *rule)
            blocked = application_status()
            if blocked not in [500, 503]:
                raise RuntimeError('Запрет БД не вызвал серверную ошибку приложения')
        finally:
            for rule in blocked_rules:
                iptables('-D', CHAIN, *rule)
        after = application_status()
        if after != 200:
            raise RuntimeError('Приложение не восстановилось после возврата правила')
        checks.append({'scenario': 'learning progress: DB permission removed and restored',
                       'http_before': before, 'http_blocked': blocked, 'http_restored': after})
    return checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['apply', 'check', 'show', 'test', 'rollback', 'report', 'summary', 'display'])
    parser.add_argument('--source', choices=list(TARGETS))
    args = parser.parse_args()
    if args.action in ['summary', 'display']:
        data = json.load(sys.stdin)
        if args.action == 'display':
            for row in data['services']:
                print('\n'+row['project']+' / '+row['source'])
                print('\n'.join(row.get('rules') or []))
                print(row.get('counters', row.get('error', '')))
            return 0 if data['ok'] else 1
        summary = {key: data[key] for key in ['at', 'action', 'project', 'ok']}
        summary['services'] = {row['source']: row.get('error', 'ok' if row['ok'] else 'failed') for row in data['services']}
        if data['action'] == 'test':
            summary['checks'] = sum(len(row.get('checks', [])) for row in data['services'])
            summary['previous_policy_restored'] = all(row.get('previous_policy_restored', False) for row in data['services'])
            summary['application'] = [check for row in data['services'] for check in row.get('checks', []) if 'scenario' in check]
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if data['ok'] else 1
    if args.action == 'report':
        results = [json.loads(p.read_text()) for p in sorted(Path('/results').glob('*.result.json'))]
        report = {'at': datetime.now(timezone.utc).isoformat(), 'action': results[0]['action'],
                  'project': results[0]['project'], 'ok': all(r['ok'] for r in results),
                  'scope': 'Linux container network namespaces; host rules untouched', 'services': results}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report['ok'] else 1
    metadata = json.loads(Path('/metadata.json').read_text())
    try:
        containers, networks, targets, rules = policy(metadata, args.source,
            build_rules=args.action not in ['show', 'rollback'])
    except (ValueError, KeyError) as error:
        print(json.dumps({'source': args.source, 'action': args.action, 'ok': False,
                          'project': metadata[0]['Config']['Labels'].get('com.docker.compose.project'),
                          'error': 'Невозможно проверить политику: '+str(error)}, ensure_ascii=False))
        return 1
    saved = snapshot()
    result = {'source': args.source, 'action': args.action,
              'project': containers[args.source]['Config']['Labels']['com.docker.compose.project'],
              'container_id': containers[args.source]['Id'][:12], 'ok': False}
    try:
        if args.action == 'rollback':
            restore({'chain': None, 'jumps': []})
        elif args.action in ['apply', 'test']:
            apply(rules)
            if not verify(rules):
                raise RuntimeError('Установленные правила отличаются от политики')
            if args.action == 'test':
                result['checks'] = test(networks, args.source, targets)
        elif args.action == 'check' and not verify(rules):
            raise RuntimeError('Firewall отсутствует или не соответствует текущим адресам; выполните scripts/deploy')
        result['rules'] = snapshot()['chain']
        result['counters'] = iptables('-nvxL', CHAIN, check=False).stdout
        result['ok'] = True
    except (Exception, KeyboardInterrupt) as error:
        result['error'] = str(error)
        if args.action == 'apply':
            restore(saved)
    finally:
        if args.action == 'test':
            restore(saved)
            result['previous_policy_restored'] = snapshot() == saved
            result['ok'] = result['ok'] and result['previous_policy_restored']
        result['policy_sha256'] = hashlib.sha256(json.dumps(snapshot(), sort_keys=True).encode()).hexdigest()
        print(json.dumps(result, ensure_ascii=False))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    def interrupted(signum, frame):
        raise InterruptedError('Сетевое испытание прервано')
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    raise SystemExit(main())
