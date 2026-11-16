"""Small executable arithmetic reference, NOT the production progression service.

No database, event delivery, ownership, V/E/R/K/M evaluator, or security is implemented.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from fractions import Fraction
from typing import Iterable

BASE = {"A": 40, "B": 80, "C": 120}
COEFFICIENT = {"independent": Fraction(1), "assisted": Fraction(7, 10)}

def rational(value: object) -> Fraction:
    if isinstance(value, bool):
        raise ValueError("Boolean is not a numeric grade or weight")
    try:
        return Fraction(str(value))
    except (ValueError, ZeroDivisionError, TypeError) as exc:
        raise ValueError(f"Invalid finite number: {value!r}") from exc

@dataclass(frozen=True)
class Part:
    part_id: str
    weight: object
    outcome: str
    quality: object = 0
    note_saved: bool = False


def validate_parts(parts: Iterable[Part]) -> list[Part]:
    values = list(parts)
    if not values:
        raise ValueError("At least one part is required")
    ids: set[str] = set()
    for p in values:
        if not p.part_id or p.part_id in ids:
            raise ValueError("Part IDs must be nonempty and unique")
        ids.add(p.part_id)
        if rational(p.weight) <= 0:
            raise ValueError("Weights must be positive")
        q = rational(p.quality)
        if q < 0 or q > 1:
            raise ValueError("Quality must be in [0, 1]")
        if p.outcome not in {"independent", "assisted", "reviewed", "skipped"}:
            raise ValueError("Unknown outcome")
        if not isinstance(p.note_saved, bool):
            raise ValueError("note_saved must be boolean")
    return values


def contribution(p: Part, *, repeat: bool = False) -> Fraction:
    if p.outcome in COEFFICIENT:
        return COEFFICIENT[p.outcome] * rational(p.quality)
    if p.outcome == "reviewed" and p.note_saved and not repeat:
        return Fraction(35, 100)
    return Fraction(0)


def candidate_xp(difficulty: str, parts: Iterable[Part]) -> int:
    if difficulty not in BASE:
        raise ValueError("Unknown difficulty; normalize B+ explicitly at the boundary")
    values = validate_parts(parts)
    weighted = sum((rational(p.weight) * contribution(p) for p in values), Fraction(0))
    total_weight = sum((rational(p.weight) for p in values), Fraction(0))
    amount = BASE[difficulty] * weighted / total_weight
    return amount.numerator // amount.denominator


def repeat_amount(difficulty: str, parts: Iterable[Part]) -> int:
    """Amount only. Eligibility belongs to the confirmed scheduler/evidence contract."""
    if difficulty not in BASE:
        raise ValueError("Unknown difficulty")
    values = validate_parts(parts)
    weighted = sum((rational(p.weight) * contribution(p, repeat=True) for p in values), Fraction(0))
    total_weight = sum((rational(p.weight) for p in values), Fraction(0))
    amount = BASE[difficulty] * Fraction(3, 10) * weighted / total_weight
    return amount.numerator // amount.denominator


def elapsed_gate(completed_at: datetime, due_at: datetime, last_credited_at: datetime) -> bool:
    """One timing gate only; does not imply a valid scheduler obligation or quality."""
    for value in (completed_at, due_at, last_credited_at):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timezone-aware timestamps required")
    # Compare UTC instants, including when local datetimes span a DST transition.
    from datetime import timezone
    end = completed_at.astimezone(timezone.utc)
    return end >= due_at.astimezone(timezone.utc) and end - last_credited_at.astimezone(timezone.utc) >= timedelta(hours=168)


def total_xp(level: int) -> int:
    if isinstance(level, bool) or not isinstance(level, int) or not 1 <= level <= 60:
        raise ValueError("Level must be an integer in [1, 60]")
    return 100 * (level - 1) + 8 * (level - 1) * (level - 2)


def level_for_xp(xp: int) -> int:
    if isinstance(xp, bool) or not isinstance(xp, int) or xp < 0:
        raise ValueError("XP must be a nonnegative integer")
    return max(level for level in range(1, 61) if total_xp(level) <= xp)


def chronicles(xp: int) -> int:
    level_for_xp(xp)  # Validate input.
    return max(0, (xp - total_xp(60)) // 2000)


def primary_entitlement(candidates: Iterable[int]) -> int:
    values = list(candidates)
    if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in values):
        raise ValueError("Candidates must be nonnegative integer XP values")
    return max(values, default=0)


def compensation(previous_candidates: Iterable[int], current_candidates: Iterable[int]) -> int:
    return primary_entitlement(current_candidates) - primary_entitlement(previous_candidates)
