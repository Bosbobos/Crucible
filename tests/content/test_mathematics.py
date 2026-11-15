import itertools
import math
from fractions import Fraction
from pathlib import Path
import yaml


def test_legacy_fixed_points_and_records():
    for n in range(2,8):
        permutations = list(itertools.permutations(range(n)))
        fixed = [sum(i==v for i,v in enumerate(p)) for p in permutations]
        assert Fraction(sum(fixed),len(fixed)) == 1
        assert Fraction(sum(x*x for x in fixed),len(fixed))-1 == 1
        records = [sum(v==max(p[:i+1]) for i,v in enumerate(p)) for p in permutations]
        assert Fraction(sum(records),len(records)) == sum(Fraction(1,k) for k in range(1,n+1))


def test_occupancy_exact_and_graph_isolation():
    for n in range(1,5):
        outcomes = list(itertools.product(range(6),repeat=n))
        assert Fraction(sum(len(set(x)) for x in outcomes),len(outcomes)) == 6*(1-Fraction(5,6)**n)
    edges=list(itertools.combinations(range(4),2))
    isolated=[]
    pairs=[]
    for bits in itertools.product([0,1],repeat=len(edges)):
        vertices={v for e,b in zip(edges,bits) if b for v in e}
        isolated.append(4-len(vertices));pairs.append(0 not in vertices and 1 not in vertices)
    assert Fraction(sum(isolated),len(isolated)) == 4*Fraction(1,2)**3
    assert Fraction(sum(pairs),len(pairs)) == Fraction(1,2)**5


def dot(a,b):
    return sum(x*y for x,y in zip(a,b))


def test_svd_cards_algebra():
    u=[1/math.sqrt(2)]*2;v=[1/math.sqrt(5),2/math.sqrt(5)]
    A=[[math.sqrt(10)*x*y for y in v] for x in u]
    assert all(math.isclose(A[i][j],[[1,2],[1,2]][i][j]) for i in range(2) for j in range(2))
    x=[.1,.2];kernel=[-2,1]
    assert math.isclose(dot(x,kernel),0,abs_tol=1e-12)
    assert all(math.isclose(dot(row,x),.5) for row in A)
    basis=[[1/math.sqrt(3)]*3,[1/math.sqrt(2),-1/math.sqrt(2),0],[1/math.sqrt(6),1/math.sqrt(6),-2/math.sqrt(6)]]
    assert all(math.isclose(dot(a,b),int(i==j),abs_tol=1e-12) for i,a in enumerate(basis) for j,b in enumerate(basis))
    assert all(math.isclose(sum(v),0,abs_tol=1e-12) for v in basis[1:])
    for t in range(361):
        x1,x2=math.cos(t),math.sin(t)
        assert 16*x1*x1+9*x2*x2>=9-1e-12


def test_content_integrity():
    cards=[yaml.safe_load(p.read_text()) for p in Path('content/problems').glob('*.yaml')]
    assert len(cards)==57
    assert {p['id'] for p in cards}=={f'P-{i:03d}' for i in range(1,58)}
    assert len({p['primary_skill_id'] for p in cards})==25
    assert all(p['solution'] and len(p['hints'])==3 and p['review']['method'] for p in cards)
    assert all(p['provenance']['kind']=='obsidian_vault' and p['review']['status']=='source_preserved' for p in cards)
    assert all(p['primary_skill_id']==p['provenance']['legacy_type'] and not p['family_reviewed'] for p in cards)
