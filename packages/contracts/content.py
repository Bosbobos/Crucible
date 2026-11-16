from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class DTO(BaseModel):
    model_config=ConfigDict(extra='forbid')


class Part(DTO):
    id:str=Field(min_length=1,max_length=40)
    skill_id:str=Field(min_length=1,max_length=80)
    title:str=Field(min_length=1,max_length=200)
    weight:float=Field(default=1,gt=0,allow_inf_nan=False)


class Review(DTO):
    status:Literal['verified','source_preserved']
    method:str=Field(min_length=1,max_length=2000)
    reviewed_at:str


class Problem(DTO):
    schema_version:Literal[1]
    id:str=Field(pattern=r'^P-\d{3,6}$')
    title:str=Field(min_length=1,max_length=200)
    primary_skill_id:str
    skill_title:str | None = None
    family_reviewed:bool = True
    reward_equivalence_id:str | None = Field(default=None,min_length=1,max_length=150)
    secondary_skill_ids:list[str]
    problem_family_id:str=Field(min_length=1,max_length=150)
    level:Literal['A','B','C']
    level_reason:str=Field(min_length=1)
    pool:Literal['train','holdout','extension']
    status:Literal['published']
    section:str
    topic_id:str | None
    estimated_minutes:list[int] | None=Field(default=None,min_length=2,max_length=2)
    content_language:Literal['en']
    revision:int=Field(ge=1)
    prerequisites:list[str]
    parts:list[Part]=Field(min_length=1,max_length=20)
    provenance:dict
    review:Review
    statement:str=Field(min_length=1,max_length=30000)
    hints:list[str]=Field(min_length=3,max_length=3)
    solution:str=Field(min_length=1,max_length=50000)
    remember:str=Field(min_length=1,max_length=6000)
    completion_criteria:str
    typical_errors:list[str]
    theory_sections:list[str]


class LearningUnitMetadata(DTO):
    kind:Literal['theory_section','core','lab','volume_final_check']
    title:str=Field(min_length=1,max_length=200)
    section:Literal['core','theory','widget']
    anchor:str|None=None
    rubric_version:str=Field(min_length=1,max_length=150)
    check_answers:dict[str,str]=Field(default_factory=dict)


class DiagnosticMetadata(DTO):
    rubric_version:str=Field(min_length=1,max_length=150)
    check_answers:dict[str,str]=Field(min_length=4,max_length=4)


class Topic(DTO):
    id:str
    title:str
    widget:Literal['expectation','svd','vault-indicators'] | None = None
    skill_ids:list[str]
    prerequisites:list[str]
    core:str | None=Field(default=None,min_length=1,max_length=120000)
    theory:str | None=Field(default=None,min_length=1,max_length=120000)
    provenance:dict = Field(default_factory=dict)
    learning_units:dict[str,LearningUnitMetadata] = Field(default_factory=dict)
    diagnostic_checks:dict[str,DiagnosticMetadata] = Field(default_factory=dict)


class ContentBundle(DTO):
    schema_version:Literal[1]
    problems:list[Problem]=Field(min_length=1,max_length=1000)
    topics:dict[str,Topic]
