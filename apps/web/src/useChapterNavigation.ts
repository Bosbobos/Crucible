import {useCallback, useEffect, useLayoutEffect, useRef, useState} from 'react';
import type {RefObject} from 'react';
import {WheelGesture} from './WheelGesture';

type Direction = -1 | 1;
type Options = {
  reader: RefObject<HTMLElement | null>;
  paper: RefObject<HTMLElement | null>;
  index: number;
  count: number;
  enabled: boolean;
  material: string;
  visit: (index: number) => void;
};

const edgeHoldTime = 480;
const edgeFeedbackThreshold = 32;
const horizontalThreshold = 60;
const verticalThreshold = 240;
const controls = 'input, textarea, select, [contenteditable]:not([contenteditable="false"]), [role="slider"], [role="spinbutton"], [role="radio"], [role="tab"], .cm-editor';

// Жест внутри таблицы, формулы, оглавления или черновика принадлежит этому блоку.
function hasOwnScroll(target: Element, root: HTMLElement, axis: 'x' | 'y') {
  for (let element: Element | null = target; element && element !== root; element = element.parentElement) {
    if (element.matches('.reader-contents, .reader-draft') || element.matches(controls)) return true;
    const style = getComputedStyle(element);
    if (axis === 'x' && /auto|scroll/.test(style.overflowX) && element.scrollWidth > element.clientWidth + 1) return true;
    if (axis === 'y' && /auto|scroll/.test(style.overflowY) && element.scrollHeight > element.clientHeight + 1) return true;
  }
  return false;
}

export function useChapterNavigation(options: Options) {
  const latest = useRef(options);
  latest.current = options;
  const [edge, setEdge] = useState({direction: 1 as Direction, progress: 0, visible: false});
  const gesture = useRef(new WheelGesture()), distance = useRef(0), edgeEligible = useRef(false);
  const pull = useRef<{direction: Direction; distance: number} | null>(null);
  const edgeDrive = useRef<{speed: number; distance: number; rises: number} | null>(null);
  const feedbackTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const resetEdge = useCallback(() => {
    clearTimeout(feedbackTimer.current);
    pull.current = null;
    edgeDrive.current = null;
    setEdge(current => current.visible ? {...current, visible: false} : current);
  }, []);

  useLayoutEffect(() => {
    resetEdge();
    gesture.current = new WheelGesture();
    distance.current = 0;
    edgeEligible.current = false;
  }, [options.enabled, options.material, resetEdge]);
  // Переход с клавиатуры или кнопки также завершает текущий колёсный импульс.
  useLayoutEffect(() => {
    gesture.current.consume(); distance.current = 0; edgeEligible.current = false; resetEdge();
  }, [options.index, resetEdge]);

  useEffect(() => {
    const root = options.reader.current;
    if (!root) return;

    function keydown(event: KeyboardEvent) {
      const {enabled, index, count, visit} = latest.current;
      if (!enabled || event.defaultPrevented || event.repeat || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      const direction = event.key === 'ArrowRight' || event.key === 'ArrowDown' ? 1 : event.key === 'ArrowLeft' || event.key === 'ArrowUp' ? -1 : 0;
      if (!direction) return;
      const target = event.target;
      if (!(target instanceof Element) || target.closest(controls) || document.querySelector('dialog[open], [aria-modal="true"]')) return;
      if (target !== document.body && !root!.contains(target)) return;
      if (root!.contains(target) && (hasOwnScroll(target, root!, 'x') || hasOwnScroll(target, root!, 'y'))) return;
      const next = index + direction;
      if (next < 0 || next >= count) return;
      event.preventDefault();
      resetEdge();
      visit(next);
    }

    function wheel(event: WheelEvent) {
      const {enabled, index, count, paper, visit} = latest.current;
      if (!enabled || count < 2 || event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      if (!(event.target instanceof Element) || document.querySelector('dialog[open], [aria-modal="true"]')) return;
      const unit = event.deltaMode === WheelEvent.DOM_DELTA_LINE ? 16 : event.deltaMode === WheelEvent.DOM_DELTA_PAGE ? window.innerHeight : 1;
      const dx = event.deltaX * unit, dy = event.deltaY * unit;
      const nativeMomentum = (event as WheelEvent & {momentum?: boolean}).momentum;
      const motion = gesture.current.sample(dx, dy, event.timeStamp, nativeMomentum);
      if (!motion) return;
      if (hasOwnScroll(event.target, root!, motion.axis)) {
        gesture.current.consume();
        distance.current = 0;
        edgeEligible.current = false;
        resetEdge();
        return;
      }
      const atEdge = (direction: number) => direction < 0
        ? window.scrollY <= 8
        : (paper.current?.getBoundingClientRect().bottom ?? Infinity) <= window.innerHeight + 8;
      const {direction} = motion;
      const next = index + direction;
      const canTurn = next >= 0 && next < count;
      if (motion.start) {
        distance.current = 0;
        edgeDrive.current = null;
        edgeEligible.current = motion.axis === 'y' && atEdge(direction) && canTurn;
      }
      if (motion.consumed) {
        event.preventDefault();
        resetEdge();
        return;
      }
      if (motion.axis === 'x') {
        event.preventDefault();
        resetEdge();
        if (!canTurn || !motion.active) return;
        distance.current += motion.distance;
        if (distance.current < horizontalThreshold) return;
      } else {
        if (!canTurn || !atEdge(direction)) {resetEdge(); return;}
        // Обычный скролл, дошедший до края, не становится усилием перелистывания.
        // Однажды начатое усилие сохраняется при замедлении и мелких колебаниях.
        if (!pull.current) {
          if (!motion.active || nativeMomentum === true) {edgeDrive.current = null; return;}
          let initialDistance = motion.distance;
          if (!edgeEligible.current) {
            const previous = edgeDrive.current;
            const rises = previous && motion.speed > previous.speed * 1.08 ? previous.rises + 1 : 0;
            edgeDrive.current = {speed: motion.speed, distance: (previous?.distance ?? 0) + motion.distance, rises};
            // Продолжение скролла с явным усилием тоже принимается, без отпускания пальцев.
            if (rises < 2) return;
            initialDistance = edgeDrive.current.distance;
            edgeEligible.current = true;
          }
          pull.current = {direction, distance: initialDistance};
        } else {
          if (pull.current.direction !== direction) {resetEdge(); return;}
          if (nativeMomentum === true || direction * dy <= 0) return;
          pull.current.distance += direction * dy;
        }
        event.preventDefault();
        const progress = Math.min(1, pull.current.distance / verticalThreshold);
        setEdge({direction, progress, visible: pull.current.distance >= edgeFeedbackThreshold});
        clearTimeout(feedbackTimer.current);
        feedbackTimer.current = setTimeout(resetEdge, edgeHoldTime);
        if (pull.current.distance < verticalThreshold) return;
      }
      gesture.current.consume();
      distance.current = 0;
      edgeEligible.current = false;
      resetEdge();
      visit(next);
    }

    window.addEventListener('keydown', keydown);
    root.addEventListener('wheel', wheel, {passive: false});
    return () => {
      window.removeEventListener('keydown', keydown);
      root.removeEventListener('wheel', wheel);
      clearTimeout(feedbackTimer.current);
    };
  }, [options.reader, options.paper, resetEdge]);

  return edge;
}
