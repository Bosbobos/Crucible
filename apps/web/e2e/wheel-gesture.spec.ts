import {test, expect} from '@playwright/test';
import {WheelGesture} from '../src/WheelGesture';

// Синтетические временные ряды: интервалы и амплитуды задаются явно, без sleep.
const flick = [12,24,36,54,72,80,76,65,50,38,26,16,9,5];
const tail = Array.from({length: 90}, (_, i) => 4.8 * 0.97 ** i);
type Frame = {x?: number; y?: number; dt?: number; momentum?: boolean};
const horizontal = (values: number[]): Frame[] => values.map(x => ({x}));

function replay(frames: Frame[]) {
  const gesture = new WheelGesture(), turns: {direction: number; at: number}[] = [];
  let at = 0, distance = 0;
  const samples = frames.map(frame => {
    at += frame.dt ?? 16;
    const motion = gesture.sample(frame.x ?? 0, frame.y ?? 0, at, frame.momentum);
    if (!motion) return motion;
    if (motion.start || !motion.active) distance = 0;
    if (motion.active) {
      distance += motion.distance;
      if (distance >= (motion.axis === 'x' ? 60 : 240)) {
        turns.push({direction: motion.direction, at});
        gesture.consume();
        distance = 0;
      }
    }
    return motion;
  });
  return {turns, samples};
}

test('один разгон, плато и длинное затухание дают один переход', () => {
  const frames = horizontal([12,24,36,...Array(18).fill(85),...flick.slice(7),...tail]);
  const {turns} = replay(frames);
  expect(turns).toEqual([{direction: 1, at: 48}]);
});

test('новый разгон в ту же сторону принимается внутри непрерывного инерционного хвоста', () => {
  const first = horizontal(flick);
  const {turns} = replay([...first,...horizontal([8,16,30,45,60,50,35,20,10,5]),...horizontal(tail)]);
  expect(turns).toHaveLength(2);
  expect(turns[1].at - first.length * 16).toBeLessThanOrEqual(64);
});

test('быстрый второй жест после короткой паузы не ждёт cooldown', () => {
  const {turns} = replay([...horizontal(flick),{x: 18,dt: 64},{x: 36},{x: 60},...horizontal(tail)]);
  expect(turns).toHaveLength(2);
  expect(turns[1].at - flick.length * 16).toBeLessThanOrEqual(96);
});

test('смена направления и новая ось принимаются сразу', () => {
  const {turns} = replay([...horizontal(flick),{x: -75},{y: 250}]);
  expect(turns.map(turn => turn.direction)).toEqual([1,-1,1]);
  expect(turns[2].at - turns[1].at).toBe(16);
});

test('одиночный всплеск и мелкий отскок в хвосте не вызывают переход', () => {
  const {turns} = replay([...horizontal(flick),...horizontal([4,3,34,2.8,-1.5,2.5,2,1.8,1.2]),...horizontal(tail)]);
  expect(turns).toHaveLength(1);
});

test('пакеты событий с разными интервалами сравниваются по скорости', () => {
  const {turns} = replay([...horizontal(flick.slice(0,11)),{x: 32,dt: 32},{x: 28,dt: 32},{x: 24,dt: 32},{x: 20,dt: 32},...horizontal(tail)]);
  expect(turns).toHaveLength(1);
});

test('ослабевший вертикальный скролл не превращается в намерение листать у края', () => {
  const gesture = new WheelGesture();
  const samples = [80,140,180,160,120,90,65,40,25,12].map((dy,i) => gesture.sample(0,dy,(i+1)*16));
  expect(samples.slice(-5).every(sample => sample && !sample.active && !sample.consumed)).toBeTruthy();
});

test('после вертикального перехода хвост подавляется, новый импульс доступен сразу', () => {
  const frames = [80,110,150,170,130,90,50,25,12,6,16,35,75,110,150,100,60,25,8].map(y => ({y}));
  const {turns} = replay(frames);
  expect(turns).toHaveLength(2);
  expect(turns[1].at).toBeLessThanOrEqual(240);
});

test('нативный признак инерции используется при наличии', () => {
  const {turns} = replay([{x: 75,momentum: false},{x: 120,momentum: true},{x: 90,momentum: true},{x: 80,momentum: false}]);
  expect(turns.map(turn => turn.at)).toEqual([16,64]);
});

test('разная сила жестов и частота пакетов сохраняют два намеренных перехода', () => {
  for (const dt of [8,16,32]) for (const force of [0.25,0.5,1,2]) {
    const frames = [...flick,...flick,...tail].map(x => ({x: x * force * dt / 16,dt}));
    expect(replay(frames).turns, `interval=${dt}, force=${force}`).toHaveLength(2);
  }
});

test('диагональные колебания сохраняют ось вертикального жеста', () => {
  const gesture = new WheelGesture();
  const frames = [[1,80],[40,30],[8,35],[20,14],[2,40]];
  expect(frames.map(([dx,dy],i) => gesture.sample(dx,dy,(i+1)*16)?.axis)).toEqual(Array(5).fill('y'));
  expect(gesture.sample(80,1,96)?.axis).toBe('x');
});

test('малый отскок не меняет направление, намеренное медленное движение распознаётся', () => {
  const gesture = new WheelGesture();
  gesture.sample(0,80,16);
  expect(gesture.sample(0,-6,32)?.direction).toBe(1);
  expect(gesture.sample(0,60,48)?.direction).toBe(1);
  expect(gesture.sample(0,-6,64)?.direction).toBe(1);
  expect(gesture.sample(0,-6,80)?.direction).toBe(-1);
});
