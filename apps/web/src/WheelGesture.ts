export type WheelAxis = 'x' | 'y';
export type WheelMotion = {axis: WheelAxis; direction: -1 | 1; distance: number; speed: number; active: boolean; start: boolean; consumed: boolean};

// WheelEvent обычно не сообщает момент отпускания пальцев. Различаем импульсы по
// скорости потока, подтверждённому затуханию и повторному разгону, а не cooldown.
export class WheelGesture {
  private axis: WheelAxis | null = null;
  private direction: -1 | 1 = 1;
  private lastAt = -Infinity;
  private speed = 0;
  private peak = 0;
  private valley = 0;
  private falling = 0;
  private slowed = false;
  private consumed = false;
  private nativeMomentum: boolean | undefined;
  private reversing = 0;
  private restart: {speed: number; distance: number; at: number} | null = null;

  consume() {this.consumed = true; this.restart = null;}

  sample(dx: number, dy: number, at: number, momentum?: boolean): WheelMotion | null {
    const gap = at - this.lastAt;
    const proposedAxis: WheelAxis = Math.abs(dx) > Math.abs(dy) * 1.2 ? 'x' : 'y';
    const primary = Math.abs(this.axis === 'x' ? dx : dy), cross = Math.abs(proposedAxis === 'x' ? dx : dy);
    // Ось удерживается на диагональных колебаниях. Явный поперечный жест доступен сразу.
    const keepAxis = this.axis && gap < 120 && proposedAxis !== this.axis && cross < Math.max(12, primary * 2.4);
    const axis = keepAxis ? this.axis! : proposedAxis;
    const delta = axis === 'x' ? dx : dy, distance = Math.abs(delta);
    if (distance < 0.5) return null;
    const direction: -1 | 1 = delta > 0 ? 1 : -1;
    // Учитываем объединённые браузером события; пауза не уменьшает силу нового жеста.
    const speed = distance * 16 / (gap >= 4 && gap <= 50 ? gap : 16);
    if (this.axis === axis && direction !== this.direction && gap < 120) {
      this.reversing += distance;
      if (this.reversing < 12) {
        this.lastAt = at;
        return {axis, direction: this.direction, distance: 0, speed: 0, active: false, start: false, consumed: this.consumed};
      }
    } else this.reversing = 0;
    let start = !this.axis || gap >= 120 || axis !== this.axis || direction !== this.direction || momentum === false && this.nativeMomentum === true;
    let acceptedDistance = distance;
    if (!start) {
      this.falling = speed <= this.speed + 0.5 ? this.falling + 1 : 0;
      this.peak = Math.max(this.peak, speed);
      if (!this.slowed && this.falling >= 2 && speed < this.peak * 0.8) {
        this.slowed = true;
        this.valley = speed;
      }
      if (this.slowed) this.valley = Math.min(this.valley, speed);
      if ((this.consumed || this.slowed) && momentum !== true) {
        const accelerating = this.slowed && speed >= Math.max(6, this.valley + 4, this.valley * 1.5);
        if (accelerating) {
          const candidate = this.restart;
          // Одиночный всплеск в хвосте ещё не считается новым движением пальцев.
          if (candidate && at - candidate.at <= 60 && speed >= candidate.speed - 0.5) {
            start = true;
            acceptedDistance += candidate.distance;
          } else this.restart = {speed, distance, at};
        } else this.restart = null;
      }
    }
    if (start) {
      this.peak = speed;
      this.valley = speed;
      this.falling = 0;
      this.slowed = false;
      this.consumed = false;
      this.restart = null;
      this.reversing = 0;
    }
    this.axis = axis;
    this.direction = direction;
    this.lastAt = at;
    this.speed = speed;
    this.nativeMomentum = momentum;
    return {
      axis, direction, distance: acceptedDistance, speed, start, consumed: this.consumed,
      active: momentum !== true && !this.consumed && (axis === 'x' || !this.slowed),
    };
  }
}
