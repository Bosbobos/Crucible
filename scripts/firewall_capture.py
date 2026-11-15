"""Живой NFLOG → ulogd2 LOGEMU. Содержимое firewall.log пишет штатный ulogd."""
import argparse
import glob
import json
import os
from pathlib import Path
import signal
import subprocess
import time

from firewall import CHAIN, TARGETS, DENIED, policy, probe, run, snapshot, restore, apply, verify, iptables, application_status

parser = argparse.ArgumentParser()
parser.add_argument('--source', required=True, choices=list(TARGETS))
args = parser.parse_args()
folder = Path('/results')
folder.mkdir(exist_ok=True)
metadata = json.loads(Path('/metadata.json').read_text())
containers, networks, targets, rules = policy(metadata, args.source)
saved = snapshot()
routes = []
daemon = None


def interrupted(signum, frame):
    raise InterruptedError('Запись сетевого журнала прервана')


signal.signal(signal.SIGTERM, interrupted)
signal.signal(signal.SIGINT, interrupted)
plugins = ['inppkt_NFLOG', 'raw2packet_BASE', 'filter_IFINDEX', 'filter_IP2STR', 'filter_PRINTPKT', 'output_LOGEMU']
config = '[global]\nlogfile="/results/ulogd-diagnostic.log"\nloglevel=5\n'
for plugin in plugins:
    paths = glob.glob('/usr/lib/**/ulogd_'+plugin+'.so', recursive=True)
    if len(paths) != 1:
        raise RuntimeError('Не найден plugin '+plugin)
    config += 'plugin="'+paths[0]+'"\n'
config += '''stack=log1:NFLOG,base1:BASE,ifi1:IFINDEX,ip2str1:IP2STR,print1:PRINTPKT,emu1:LOGEMU
[log1]
group=100
numeric_label=1
netlink_qthreshold=1
netlink_qtimeout=10
netlink_socket_buffer_size=1048576
netlink_socket_buffer_maxsize=4194304
[emu1]
file="/results/firewall.log"
sync=1
'''
Path('/tmp/ulogd.conf').write_text(config)
try:
    apply(rules)
    assert verify(rules)
    (folder/'iptables.rules').write_text(run('iptables', '-S', CHAIN).stdout)
    daemon = subprocess.Popen(['ulogd', '-c', '/tmp/ulogd.conf'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    deadline = time.monotonic()+5
    while not (folder/'firewall.log').exists():
        if daemon.poll() is not None:
            raise RuntimeError('ulogd: '+daemon.communicate()[0].decode())
        if time.monotonic()>deadline:
            raise RuntimeError('ulogd не открыл журнал')
        time.sleep(.05)
    # В internal-сетях отсутствует default route. Диагностический /32 маршрут
    # даёт SYN дойти до OUTPUT. ACCEPT-правила и Docker network membership не меняются.
    # Финальный REJECT должен остановить каждый такой пакет до выхода из namespace.
    if args.source != 'web':
        own = 'postgres-'+args.source
        shared = sorted(set(networks[args.source]) & set(networks[own]))[0]
        own_ip = networks[args.source][shared]
    else:
        shared = sorted(set(networks['web']) & set(networks['content']))[0]
        own_ip = networks['web'][shared]
    # local route возвращает lo; физический интерфейс находим по собственному IP.
    interfaces = json.loads(run('ip', '-j', 'address').stdout)
    interface = next(i['ifname'] for i in interfaces if any(a.get('local')==own_ip for a in i['addr_info']))
    for target, port in DENIED[args.source]:
        if set(networks[args.source]) & set(networks[target]):
            continue
        address = sorted(networks[target].values())[0]
        entry = [address+'/32', 'dev', interface]
        added = run('ip', 'route', 'add', *entry, check=False)
        if added.returncode == 0:
            routes.append(entry)
    # Готовность подписчика подтверждаем получением реального разрешённого SYN.
    deadline = time.monotonic()+5
    while 'ALLOW_'+args.source not in (folder/'firewall.log').read_text():
        probe(networks, args.source, *targets[0])
        if daemon.poll() is not None or time.monotonic()>deadline:
            raise RuntimeError('NFLOG-подписчик не получил контрольный SYN')
        time.sleep(.05)
    checks = []
    # Одно свежее TCP-подключение к каждой разрешённой и запрещённой цели.
    for expected, pairs in [(True, targets), (False, DENIED[args.source])]:
        for target, port in pairs:
            connected, shared_network = probe(networks, args.source, target, port)
            assert connected == expected, (target, connected)
            shared = sorted(set(networks[args.source]) & set(networks[target]))
            address = networks[target][shared[0]] if shared else sorted(networks[target].values())[0]
            checks.append({'target': target, 'address': address, 'port': port, 'connected': connected})
    if args.source == 'learning':
        assert application_status() == 200
        blocked_rules = []
        for name in ('postgres-learning', 'postgres-learning-standby'):
            for address in networks.get(name, {}).values():
                match = ['-d', address, '-p', 'tcp', '--dport', '5432']
                blocked_rules += [match+['-j', 'REJECT'], match+['--syn', '-j', 'NFLOG',
                                   '--nflog-group', '100', '--nflog-prefix', 'BLOCK_learning']]
        try:
            for rule in blocked_rules:
                iptables('-I', CHAIN, '1', *rule)
            (folder/'blocked.rules').write_text(run('iptables', '-S', CHAIN).stdout)
            assert application_status() in (500, 503)
        finally:
            for rule in reversed(blocked_rules):
                iptables('-D', CHAIN, *rule)
        assert application_status() == 200
    deadline = time.monotonic()+5
    while True:
        log = (folder/'firewall.log').read_text()
        missing = [c for c in checks if not any(('ALLOW_' if c['connected'] else 'DENY_')+args.source in line
                   and 'DST='+c['address']+' ' in line and 'DPT='+str(c['port'])+' ' in line
                   for line in log.splitlines())]
        if not missing:
            break
        if time.monotonic()>deadline:
            raise RuntimeError('В NFLOG не подтверждены пакеты: '+str([c['target'] for c in missing]))
        time.sleep(.05)
    daemon.terminate()
    daemon.wait(timeout=5)
    daemon = None
    log = (folder/'firewall.log').read_text()
    assert 'ALLOW_'+args.source in log and 'DENY_'+args.source in log
    if args.source == 'learning':
        assert 'BLOCK_learning' in log
    (folder/'checks.json').write_text(json.dumps(checks, indent=2))
    (folder/'iptables-counters.log').write_text(run('iptables', '-nvxL', CHAIN).stdout)
    print(log, end='')
finally:
    if daemon is not None:
        daemon.terminate()
        daemon.wait(timeout=5)
    for entry in reversed(routes):
        run('ip', 'route', 'del', *entry, check=False)
    restore(saved)
    if snapshot() != saved:
        raise RuntimeError('Прежняя политика не восстановлена')
