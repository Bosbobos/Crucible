// Общие вызовы API и runtime-контейнеров для демонстрационных проверок.
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';

const exec = promisify(execFile);
const root = fileURLToPath(new URL('../../', import.meta.url));

export async function apiClient() {
    const directory = process.env.CRUCIBLE_ASSESSMENT === '1' ? '.secrets/assessment' : '.secrets';
    const operator = JSON.parse(await fs.readFile(path.join(root, directory, 'operator.json'), 'utf8'));
    return async (service, url, method = 'GET', body) => {
        const response = await fetch(operator.base_url.replace(/\/$/, '') + '/api/v1/' + service + url, {
            method,
            headers: {Authorization: 'Bearer ' + operator.tokens[service], 'Content-Type': 'application/json'},
            body: body === undefined ? undefined : JSON.stringify(body),
            signal: AbortSignal.timeout(15000),
        });
        if (!response.ok) throw new Error(service + ' HTTP ' + response.status);
        return response.json();
    };
}

export async function python(service, code) {
    // Повторно используем выбор Compose-файлов/project из штатных shell-команд.
    const result = await exec('sh', [
        '-c', '. scripts/compose.sh\ncrucible_compose "$@"', 'demo',
        'exec', '-T', service, 'python', '-c', code,
    ], {cwd: root, timeout: 15000, maxBuffer: 1024 * 1024});
    return result.stdout.trim();
}
