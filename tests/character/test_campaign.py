"""Ошибки привязки не должны превращать разные учебные основания в одну награду."""
import copy
import pytest
from contracts.campaign import Campaign


def campaign():
    return dict(publication_version='synthetic-v1',content_release_id='fixture-v1',
                volumes={'LA-01':dict(core_id='core')},
                units={'core':dict(volume_id='LA-01',content_version='fixture-v1',unit_kind='core')},
                problems={'p':dict(volume_id='LA-01',discipline_id='LA',family_id='family',reward_equivalence_id='eq',rubric_version='r1',mapping_version='m1',content_version='fixture-v1',difficulty='B',pool='train')},assessments={})


def test_unit_role_and_no_orphan_or_duplicate_binding():
    valid=campaign();Campaign.model_validate(valid)
    wrong=copy.deepcopy(valid);wrong['units']['core']['unit_kind']='theory_section'
    with pytest.raises(ValueError):Campaign.model_validate(wrong)
    wrong=copy.deepcopy(valid);wrong['volumes']['LA-01']={}
    with pytest.raises(ValueError):Campaign.model_validate(wrong)
    wrong=copy.deepcopy(valid);wrong['volumes']['LA-01']['lab_id']='core'
    with pytest.raises(ValueError):Campaign.model_validate(wrong)


def test_equivalence_cannot_change_family_difficulty_or_discipline():
    for field,value in [('family_id','other'),('difficulty','C'),('discipline_id','CA')]:
        wrong=campaign();wrong['problems']['clone']={**wrong['problems']['p'],field:value}
        with pytest.raises(ValueError):Campaign.model_validate(wrong)
