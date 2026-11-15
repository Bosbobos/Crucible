from datetime import datetime
from uuid import UUID
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Event(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal[1] = 1
    event_id: UUID
    event_type: str
    producer: str
    profile_id: str
    source_seq: int = Field(ge=1)
    aggregate_id: str
    aggregate_revision: int = Field(ge=1)
    occurred_at: datetime
    correlation_id: UUID
    payload: dict


class PartFact(BaseModel):
    model_config = ConfigDict(extra='forbid')
    part_id: str
    skill_id: str
    outcome: Literal['independent','assisted','reviewed','unfinished']


class PracticeFact(BaseModel):
    model_config = ConfigDict(extra='forbid')
    problem_id: str
    content_release_id: str
    problem_family_id: str
    primary_skill_id: str
    level: Literal['A','B','C']
    attempt_status: Literal['running','paused','completed','abandoned']
    completed_at: datetime | None
    part_outcomes: list[PartFact]
    mathematical_help_used: bool
    active_minutes: float = Field(ge=0)
    eligible_for_progress: bool
    active_attempt_id: UUID | None
