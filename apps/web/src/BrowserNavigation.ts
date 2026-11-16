import {useCallback, useEffect, useState} from 'react';

export type Page = 'today' | 'practice' | 'library' | 'questions';
export type Route = {
  page: Page;
  attemptId?: string;
  topicId?: string;
  material?: string;
  releaseId?: string;
  anchor?: string;
  chapter?: number;
  laboratory?: boolean;
  query?: string;
  section?: string;
};

export function readRoute(): Route {
  const url = new URL(window.location.href), params = url.searchParams;
  let parts: string[];
  try {parts = url.pathname.split('/').filter(Boolean).map(decodeURIComponent);} catch {return {page: 'today'};}
  const page: Page = parts[0] === 'materials' ? 'library' : parts[0] === 'practice' ? 'practice' : parts[0] === 'questions' ? 'questions' : 'today';
  const chapter = Number(params.get('chapter'));
  return {
    page,
    ...(page === 'practice' && parts[1] ? {attemptId: parts[1], material: params.get('material') || undefined, topicId: params.get('topic') || undefined} : {}),
    ...(page === 'library' ? {topicId: parts[1], material: parts[1] ? params.get('part') === 'theory' ? 'theory' : 'core' : undefined, query: params.get('q') || '', section: params.get('section') || ''} : {}),
    releaseId: params.get('release') || undefined,
    anchor: params.get('anchor') || undefined,
    chapter: Number.isSafeInteger(chapter) && chapter > 0 ? chapter - 1 : undefined,
    laboratory: params.get('view') === 'lab',
  };
}

export function routeHref(route: Route) {
  const path = route.page === 'library' ? '/materials' + (route.topicId ? '/' + encodeURIComponent(route.topicId) : '')
    : route.page === 'practice' ? '/practice' + (route.attemptId ? '/' + encodeURIComponent(route.attemptId) : '')
    : route.page === 'questions' ? '/questions' : '/';
  const params = new URLSearchParams();
  if (route.material) {
    params.set(route.page === 'library' ? 'part' : 'material', route.material);
    if (route.page === 'practice' && route.topicId) params.set('topic', route.topicId);
    if (route.releaseId) params.set('release', route.releaseId);
    if (route.anchor) params.set('anchor', route.anchor);
    if (route.chapter !== undefined) params.set('chapter', String(route.chapter + 1));
    if (route.laboratory) params.set('view', 'lab');
  } else if (route.page === 'library') {
    if (route.query) params.set('q', route.query);
    if (route.section) params.set('section', route.section);
  }
  return path + (params.size ? '?' + params : '');
}

export function materialRouteKey(route: Route) {
  return route.material ? routeHref({...route, anchor: undefined, chapter: undefined, laboratory: false}) : '';
}

export function useBrowserNavigation() {
  const [route, setRoute] = useState(readRoute);
  useEffect(() => {
    const restore = () => setRoute(readRoute());
    window.addEventListener('popstate', restore);
    return () => window.removeEventListener('popstate', restore);
  }, []);
  const go = useCallback((next: Route, replace = false) => {
    const href = routeHref(next);
    if (href !== window.location.pathname + window.location.search) window.history[replace ? 'replaceState' : 'pushState'](null, '', href);
    setRoute(next);
  }, []);
  return {route, go};
}

// Уже раскрытые подсказки переживают обновление вкладки без повторной команды помощи.
const openedMaterials = new Map<string, Record<string, any>>();
export function rememberOpenedMaterial(key: string, material: Record<string, any>) {
  openedMaterials.set(key, material);
  try {sessionStorage.setItem('crucible-open-material:' + key, JSON.stringify(material));} catch { /* Кэш не влияет на сохранение попытки. */ }
}

export function openedMaterial(key: string): Record<string, any> | null {
  if (openedMaterials.has(key)) return openedMaterials.get(key)!;
  try {
    const value = JSON.parse(sessionStorage.getItem('crucible-open-material:' + key) || 'null');
    return value && typeof value.text === 'string' ? value : null;
  } catch {return null;}
}
