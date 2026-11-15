"""Демонстрация CRUD в собственной БД learning с обязательным rollback."""

import json
from pathlib import Path
from uuid import uuid4

import psycopg


def main():
    config = json.loads(Path('/run/secrets/config').read_text())
    with psycopg.connect(config['dsn'], connect_timeout=5) as conn:
        try:
            role, database = conn.execute('SELECT current_user, current_database()').fetchone()
            if (role, database) != ('learning_runtime', 'learning_db'):
                raise RuntimeError('CRUD demo requires learning_runtime in learning_db')
            print('Runtime role:', role)

            key = str(uuid4())
            conn.execute('INSERT INTO plan_drafts(id,title) VALUES (%s,%s)',
                         (key, 'presentation-demo'))
            print('INSERT plan_drafts:', key)

            title = conn.execute('SELECT title FROM plan_drafts WHERE id=%s', (key,)).fetchone()[0]
            if title != 'presentation-demo':
                raise RuntimeError('SELECT did not return the inserted title')
            print('SELECT title:', title)

            conn.execute('UPDATE plan_drafts SET title=%s WHERE id=%s', ('updated', key))
            title = conn.execute('SELECT title FROM plan_drafts WHERE id=%s', (key,)).fetchone()[0]
            if title != 'updated':
                raise RuntimeError('UPDATE did not change the title')
            print('UPDATE title:', title)

            conn.execute('DELETE FROM plan_drafts WHERE id=%s', (key,))
            remaining = conn.execute('SELECT count(*) FROM plan_drafts WHERE id=%s',
                                     (key,)).fetchone()[0]
            if remaining != 0:
                raise RuntimeError('DELETE did not remove the temporary row')
            print('DELETE remaining rows:', remaining)
        finally:
            conn.rollback()

    print('Temporary check complete. Transaction rolled back.')


if __name__ == '__main__':
    main()
