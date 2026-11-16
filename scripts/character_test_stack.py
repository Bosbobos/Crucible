"""Изолированный синтетический стенд G2/G8; не использует рабочие DB volumes."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import yaml
from setup import setup
from database_topology import OWNERS,primary

ROOT=Path(__file__).resolve().parents[1]
PROJECT='crucible-character-test'
PORT=28083
FOLDER=ROOT/'.private/crucible-v3-test'
SECRETS=ROOT/'.secrets/character-test'


def environment():
    FOLDER.mkdir(parents=True,exist_ok=True)
    overlay=FOLDER/'compose.override.yaml'
    base=yaml.safe_load((ROOT/'compose.yaml').read_text())
    text=['services:','  web:',f'    ports: !override [127.0.0.1:{PORT}:8080]','secrets:']
    for name,definition in base['secrets'].items():
        text.append(f'  {name}: {{file: {SECRETS/Path(definition["file"]).name}}}')
    text.append('networks:')
    for index,name in enumerate(base['networks']):
        text.extend([f'  {name}:',f'    ipam: {{config: [{{subnet: 10.245.208.{index*16}/28}}]}}'])
    overlay.write_text('\n'.join(text)+'\n')
    return dict(os.environ,COMPOSE_FILE=str(ROOT/'compose.yaml')+os.pathsep+str(overlay),
                COMPOSE_PROJECT_NAME=PROJECT,CRUCIBLE_DEMO='1',CRUCIBLE_ORIGIN=f'http://127.0.0.1:{PORT}')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['up','status','stop']);args=parser.parse_args()
    os.chdir(ROOT);env=environment()
    def run(*command):subprocess.run(command,env=env,check=True)
    if args.action=='up':
        os.environ['CRUCIBLE_ORIGIN']=env['CRUCIBLE_ORIGIN'];setup(SECRETS)
        practice_path=SECRETS/'practice.json';practice=json.loads(practice_path.read_text())
        if not practice.get('demo_profile'):
            practice['demo_profile']=True;practice_path.write_text(json.dumps(practice,indent=2));practice_path.chmod(0o644)
        run('docker','compose','up','-d','--wait',*[primary(o) for o in OWNERS],'redis','rabbitmq')
        run('docker','compose','cp',str(SECRETS/'rabbit-definitions.json'),'rabbitmq:/tmp/crucible-test-definitions.json')
        run('docker','compose','exec','-T','rabbitmq','rabbitmqctl','import_definitions','/tmp/crucible-test-definitions.json')
        run('docker','compose','up','-d','--force-recreate','migrations');run('docker','compose','wait','migrations')
        run('docker','compose','up','-d','--no-deps','--force-recreate',*OWNERS)
        run('scripts/firewall','apply','--available')
        run('docker','compose','up','-d','--wait','--wait-timeout','180')
        run('scripts/firewall','apply')
        print(f'Синтетический стенд: http://127.0.0.1:{PORT}; отдельные secrets/volumes; рабочая история не менялась.')
    elif args.action=='stop':run('docker','compose','stop')
    else:run('docker','compose','ps')


if __name__=='__main__':main()
