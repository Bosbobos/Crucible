import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path('scripts').resolve()))
from import_vault_content import LiteralReader,callouts,adapt_markdown,exercise_data


def test_import_extracts_educational_blocks_without_personal_notes():
    raw='''> [!problem] P-001
> `PR-01` `level A`
>
> Source condition $x^2$.

## Мои попытки
PRIVATE OWNER DRAFT SHOULD NEVER BE IMPORTED

> [!idea]- Hint 1
> Source hint.

> [!solution]- Solution
> Source solution.
'''
    fields=callouts(raw,'problem')+callouts(raw,'idea')+callouts(raw,'solution')
    assert all('PRIVATE OWNER' not in value for value in fields)
    assert fields[1:]==['Source hint.','Source solution.']


def test_dataview_is_parsed_as_literals_and_latex_is_preserved():
    data=exercise_data(r"await dv.view('x/extra/widgets/lab', {primer:'E-Var', kind:'ask', id:'test', q:String.raw`$\frac1n$`, ans:'1/2', choices:['a','b'],})")
    assert data['q']==r'$\frac1n$' and data['ans']=='1/2'
    for unsafe in ["{x:process.exit()}","{x:()=>1}","{__proto__:{x:1}}","{x:String.raw`${readSecrets()}`}" ]:
        with pytest.raises(ValueError):LiteralReader(unsafe).read()


def test_source_links_and_block_anchors_are_preserved_without_execution():
    value=adapt_markdown('^ind\n\n[[Ядро темы/Матожидание, дисперсия и индикаторы#^ind|индикаторы]]',[])
    assert '```vault-anchor\nind\n```' in value
    assert '[индикаторы](study-material:vault-expectation#^ind)' in value
