"""Private metadata publication. Ответов и текстов контрольных условий здесь нет."""
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,model_validator


class Closed(BaseModel):
    model_config=ConfigDict(extra='forbid')


class UnitBinding(Closed):
    volume_id:str
    content_version:str
    unit_kind:Literal['theory_section','core','lab','volume_final_check']


class VolumeBinding(Closed):
    theory_section_ids:list[str]=Field(default_factory=list,max_length=4)
    core_id:str|None=None
    lab_id:str|None=None
    final_check_id:str|None=None
    diagnostic_id:str|None=None
    diagnostic_version:str|None=None


class ProblemBinding(Closed):
    volume_id:str|None=None
    discipline_id:Literal['LA','CA','PR','DS','OD']
    family_id:str=Field(min_length=1,max_length=150)
    reward_equivalence_id:str=Field(min_length=1,max_length=150)
    rubric_version:str=Field(min_length=1,max_length=150)
    mapping_version:str=Field(min_length=1,max_length=150)
    content_version:str=Field(min_length=1,max_length=80)
    difficulty:Literal['A','B','C']
    pool:Literal['train','campaign_holdout']


class AssessmentBinding(Closed):
    variant_id:str=Field(min_length=1,max_length=150)
    publication_version:str=Field(min_length=1,max_length=150)
    problem_ids:list[str]=Field(min_length=4,max_length=6)


class Campaign(Closed):
    schema_version:Literal[1]=1
    publication_version:str=Field(min_length=1,max_length=150)
    content_release_id:str=Field(min_length=1,max_length=80)
    volumes:dict[str,VolumeBinding]
    units:dict[str,UnitBinding]
    problems:dict[str,ProblemBinding]
    assessments:dict[str,AssessmentBinding]
    training_family_ids:list[str]=Field(default_factory=list)

    @model_validator(mode='after')
    def references(self):
        volumes={f'{d}-{i:02d}' for d in ('LA','CA','PR','DS','OD') for i in range(1,6)}
        if not set(self.volumes)<=volumes or len(self.problems)>2000 or len(self.units)>1000:
            raise ValueError('Неизвестные тома или слишком большая публикация')
        for uid,u in self.units.items():
            if not uid or u.volume_id not in self.volumes:
                raise ValueError('Unit без привязки к тому')
        used_units=set()
        for vid,v in self.volumes.items():
            ids=[*v.theory_section_ids,*[i for i in (v.core_id,v.lab_id,v.final_check_id) if i]]
            if len(set(ids))!=len(ids) or set(ids)&used_units:
                raise ValueError('Повторная привязка unit')
            used_units.update(ids)
            for uid in ids:
                if uid not in self.units or self.units[uid].volume_id!=vid:
                    raise ValueError('Unit не соответствует тому')
            expected=[*(('theory_section',uid) for uid in v.theory_section_ids),
                      *((kind,uid) for kind,uid in (('core',v.core_id),('lab',v.lab_id),('volume_final_check',v.final_check_id)) if uid)]
            if any(self.units[uid].unit_kind!=kind for kind,uid in expected):
                raise ValueError('Роль unit не соответствует её виду')
            if bool(v.diagnostic_id)!=bool(v.diagnostic_version):
                raise ValueError('Диагностика требует ID и версию рубрики')
        if used_units!=set(self.units):
            raise ValueError('Unit не указан в составе тома')
        equivalences={}
        for p in self.problems.values():
            if p.volume_id and p.volume_id not in self.volumes:
                raise ValueError('Неверная привязка E')
            if p.content_version!=self.content_release_id:
                raise ValueError('Смешанные версии содержания')
            if p.volume_id and p.discipline_id!=p.volume_id[:2]:
                raise ValueError('Дисциплина задачи не соответствует тому')
            meaning=(p.family_id,p.difficulty,p.discipline_id)
            if p.reward_equivalence_id in equivalences and equivalences[p.reward_equivalence_id]!=meaning:
                raise ValueError('Противоречивый equivalence')
            equivalences[p.reward_equivalence_id]=meaning
        m_families=set()
        registered_problems=set()
        for bid,a in self.assessments.items():
            if bid not in {*(f'K-{d}' for d in ('LA','CA','PR','DS','OD')),'M-01','M-02','M-03'}:
                raise ValueError('Неизвестный blueprint')
            if len(a.problem_ids)!=(4 if bid.startswith('K') else 6) or len(set(a.problem_ids))!=len(a.problem_ids):
                raise ValueError('Неверный состав варианта')
            if registered_problems & set(a.problem_ids):
                raise ValueError('Контрольные условия пересекаются')
            registered_problems.update(a.problem_ids)
            if any(pid not in self.problems or self.problems[pid].pool!='campaign_holdout' for pid in a.problem_ids):
                raise ValueError('Контрольный вариант требует отдельного пула')
            families={self.problems[pid].family_id for pid in a.problem_ids}
            difficulties=[self.problems[pid].difficulty for pid in a.problem_ids]
            if difficulties!=(['B','B','B','C'] if bid.startswith('K') else ['B']*5+['C']):
                raise ValueError('Состав по сложности не соответствует blueprint')
            if bid.startswith('K') and (len(families)<3 or any(self.problems[pid].discipline_id!=bid[2:] for pid in a.problem_ids)):
                raise ValueError('Неверные семейства/дисциплина K')
            if bid.startswith('M'):
                if {self.problems[pid].discipline_id for pid in a.problem_ids[:5]}!={'LA','CA','PR','DS','OD'}:
                    raise ValueError('В M должны быть представлены пять дисциплин')
                if families & (m_families|set(self.training_family_ids)) or len(families)<6:
                    raise ValueError('Семейства M пересекаются')
                m_families|=families
        return self
