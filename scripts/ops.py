import json
import os
import subprocess
import socket
from pathlib import Path

ASSESSMENT=os.getenv('CRUCIBLE_ASSESSMENT')=='1'
COMPOSE=['docker','compose']+(['-f','compose.yaml','-f','compose.assessment.yaml','-p',os.getenv('CRUCIBLE_ASSESSMENT_PROJECT','crucible-assessment')] if ASSESSMENT else [])
if ASSESSMENT and os.getenv('CRUCIBLE_ASSESSMENT_OVERLAY'):
    COMPOSE[-2:-2]=['-f',os.environ['CRUCIBLE_ASSESSMENT_OVERLAY']]
SECRETS=Path('.secrets/assessment' if ASSESSMENT else '.secrets')


def run(args,*,input=None,check=True):
    result=subprocess.run(args,input=input,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if check and result.returncode:
        raise RuntimeError('Command failed: '+str(args[:5])+'\n'+result.stderr[-2500:])
    return result


def compose(*args,**kwargs):
    return run(COMPOSE+list(args),**kwargs)


def container(service):
    result=compose('ps','-aq',service).stdout.strip()
    if not result:raise RuntimeError('Missing service '+service)
    return result


def evidence(name,data):
    folder=Path('.private/evidence');folder.mkdir(parents=True,exist_ok=True)
    (folder/(name+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2,default=str))
    host_owned(folder/(name+'.json'))


def host_owned(path):
    """Новые закрытые файлы принадлежат владельцу checkout, а не UID контейнера."""
    if os.getenv('CRUCIBLE_OPERATOR_CONTAINER')=='1' and os.geteuid()==0:
        owner=Path.cwd().stat()
        os.chown(path,owner.st_uid,owner.st_gid)


def api_base_url(base=None):
    """Оператор присоединяет только себя к API-сети выбранного project."""
    if os.getenv('CRUCIBLE_OPERATOR_CONTAINER')!='1':
        raise RuntimeError('api_base_url предназначен для операторского контейнера')
    command=base or COMPOSE
    web=run(command+['ps','-q','web']).stdout.strip()
    if not web:raise RuntimeError('Web выбранного project не запущен')
    target=json.loads(run(['docker','inspect',web]).stdout)[0]
    network=next(name for name in target['NetworkSettings']['Networks'] if name.endswith('_content_api'))
    own=socket.gethostname()
    current=json.loads(run(['docker','inspect',own]).stdout)[0]
    if network not in current['NetworkSettings']['Networks']:
        run(['docker','network','connect',network,own])
    return 'http://'+target['Name'].lstrip('/')+':8080'


def refresh_firewall(base=None):
    """Пересчитываем только правила выбранного project после start/recreate."""
    env=dict(os.environ)
    if base:
        env['CRUCIBLE_ASSESSMENT']='0'
        env['COMPOSE_PROJECT_NAME']=base[base.index('-p')+1]
        env['COMPOSE_FILE']=os.pathsep.join(base[i+1] for i,value in enumerate(base) if value=='-f')
    result=subprocess.run([str(Path.cwd()/'scripts/firewall'),'apply'],env=env,text=True,capture_output=True)
    if result.returncode:raise RuntimeError('Не удалось восстановить firewall: '+result.stderr[-500:])
