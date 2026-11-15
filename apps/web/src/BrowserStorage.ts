// Переносим сохранённые данные по назначению ключа, независимо от прежнего бренда.
// Сначала записываем новое значение: ошибка quota не удалит исходный черновик.
export function migrateBrowserStorage(storage: Storage) {
  const keys = Array.from({length: storage.length}, (_, index) => storage.key(index));
  for (const key of keys) {
    if (!key || key.startsWith('crucible-')) continue;
    const match = key.match(/^[a-z][a-z0-9-]*?-(pending-command|emergency-.+|vault-try:.+)$/);
    if (!match) continue;
    const target = 'crucible-' + match[1];
    const value = storage.getItem(key);
    if (value === null) continue;
    const current = storage.getItem(target);
    if (current !== null && current !== value) continue;
    storage.setItem(target, value);
    storage.removeItem(key);
  }
}
