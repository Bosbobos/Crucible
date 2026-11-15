"""Публикация через API владельца; инициализация сохраняет существующий release."""
import argparse
import json
import os
import time
import uuid
from pathlib import Path
import httpx
from bundle_content import bundle


def publish(*, if_empty=False, wait_learning=False):
    config = json.loads(Path(os.getenv('CRUCIBLE_OPERATOR_CONFIG', '.secrets/operator.json')).read_text())
    base_url = os.getenv('CRUCIBLE_BASE_URL', config['base_url']).rstrip('/')
    learning_url = os.getenv('CRUCIBLE_LEARNING_URL', base_url).rstrip('/')
    headers = {'Authorization': 'Bearer '+config['tokens']['content']}
    with httpx.Client(timeout=20) as client:
        current = client.get(base_url+'/api/v1/content/catalog', headers=headers)
        if current.status_code == 200 and if_empty:
            data = current.json()
            result = {'release_id': data['content_release_id'], 'catalog_seq': data['catalog_seq'], 'existing': True}
        else:
            if current.status_code not in [200, 404]:
                raise RuntimeError('Чтение каталога завершилось HTTP '+str(current.status_code))
            content = bundle()
            command_id = str(uuid.uuid4())
            for attempt in range(3):
                try:
                    response = client.post(base_url+'/api/v1/content/releases', headers=headers,
                                           json={'command_id': command_id, 'bundle': content})
                    if response.status_code >= 400:
                        raise RuntimeError('Публикация завершилась HTTP '+str(response.status_code))
                    result = response.json()
                    break
                except httpx.TransportError:
                    if attempt == 2:
                        raise
                    time.sleep(1)
        # Existing installations may be awaiting retained-outbox replay after a
        # restore. Do not block startup before that operator step can run.
        if wait_learning and not result.get('existing'):
            deadline = time.monotonic()+90
            while True:
                response = client.get(learning_url+'/api/v1/learning/progress',
                                      headers={'Authorization': 'Bearer '+config['tokens']['learning']})
                if response.status_code == 200:
                    progress = response.json()
                    if (progress['content_release_id'] == result['release_id'] and
                            progress['catalog_seq'] >= result['catalog_seq']):
                        break
                elif response.status_code < 500:
                    raise RuntimeError('Проверка learning завершилась HTTP '+str(response.status_code))
                if time.monotonic() > deadline:
                    raise RuntimeError('Learning не получил каталог за 90 секунд')
                time.sleep(.5)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--if-empty', action='store_true')
    parser.add_argument('--wait-learning', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(publish(if_empty=args.if_empty, wait_learning=args.wait_learning), ensure_ascii=False))
    except (RuntimeError, httpx.HTTPError) as error:
        raise SystemExit('Ошибка публикации: '+str(error)) from None
