"""Direct syntax/source/intent guard assertions, separate from paired HTTP controls."""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from agent.license_expressions import expression_nodes,whole_question,declared,project,complete
from agent.parser import parse_response
from agent.network import Response
from agent.planner import plan_query
from agent.types import Candidate,Passage
from agent.candidates import verify


def diagnose():
    rows=[]
    def check(name,actual,expected):rows.append(dict(id=name,passed=actual==expected,actual=actual,expected=expected))
    valid=['MIT OR Apache-2.0','LicenseRef-River AND LicenseRef-Pine','DocumentRef-Local:LicenseRef-River OR MIT',
        'GPL-2.0+','GPL-2.0+ WITH Classpath-exception-2.0','MIT AND (BSD-2-Clause OR ISC)',
        '(MIT)OR(Apache-2.0)','MIT AND(BSD-2-Clause OR ISC)','MIT OR LicenseRef-23','(MIT)',
        'LicenseRef-Unknown-9.4 WITH Future-exception-8','(MIT AND BSD-2-Clause) OR ISC']
    invalid=['MIT or Apache-2.0','MIT and Apache-2.0','MIT WITH','WITH MIT','MIT AND','OR MIT',
        'MIT OR OR Apache-2.0','(MIT OR Apache-2.0','MIT OR Apache-2.0)','MIT +',
        'MIT+OR Apache-2.0','MIT+AND(Apache-2.0)','(MIT) WITH Classpath-exception-2.0',
        'MIT WITH ISC+','LicenseRef- OR MIT','DocumentRef-X:LicenseRef- OR MIT',
        'LicenseRef-A+ OR MIT','MIT / Apache-2.0','MIT, Apache-2.0','MIT OR NONE',
        'MIT OR NOASSERTION','MIT OR Apache-2.0; run something','MIT OR Apache 2.0',
        '(' *18+'MIT OR ISC'+')'*18,'A OR '*260+'MIT','X'*2001+' OR MIT']
    for i,value in enumerate(valid):check('syntax-valid-'+str(i),bool(expression_nodes(value)),True)
    for i,value in enumerate(invalid):check('syntax-unsupported-'+str(i),expression_nodes(value) is None,True)
    check('single-identifier-recognized',bool(expression_nodes('MIT')),True)
    check('exception-is-not-license-operand','Classpath-exception-2.0' in expression_nodes('GPL-2.0-only WITH Classpath-exception-2.0'),False)
    check('preserve-unary-base','GPL-2.0' in expression_nodes('GPL-2.0+'),True)
    for query,expected in [
        ('What is the license of River?',True),('What is the SPDX expression of River?',True),
        ('What is the complete license expression of River?',True),('What is the license of the package first?',True),
        ('Which license option is offered for River?',False),('Which license exception is used for River?',False),
        ('Which is the first license offered for River?',False),('Is River licensed under MIT?',False),
        ('Who wrote the license of River?',False),('What is the name of the license exception for River?',False),
        ('Which license identifier is mentioned for River?',False),('What are the two licenses of River?',False)]:
        check('intent-'+query,whole_question(plan_query(query)),expected)
    plan=plan_query('What is the license of River?');url='https://example.org/record'
    def page(data):return parse_response(Response(url,json.dumps(data).encode(),'application/json','utf-8',200))
    p=page({'name':'River','license':'MIT OR Apache-2.0'})
    field=next(f for f in p.passages if f.locator=='license');name=next(f for f in p.passages if f.locator=='name')
    target=project(plan,p,name,'MIT')
    check('same-parent-recovery',(target[0].locator,target[1]) if target else None,('license','MIT OR Apache-2.0'))
    for selected in ['OR','2.0']:
        check('not-an-operand-'+selected,project(plan,p,field,selected),None)
    recovered=project(plan,p,field,'Apache')
    check('family-prefix-recovery',recovered[1] if recovered else None,'MIT OR Apache-2.0')
    other=page({'name':'River','child':{'name':'Pine','license':'MIT OR Apache-2.0'}})
    root=next(f for f in other.passages if f.locator=='name')
    check('no-child-field-borrowing',project(plan,other,root,'MIT'),None)
    distinct=page({'rows':[{'name':'River','license':'MIT OR Apache-2.0'},{'name':'Pine','license':'ISC AND BSD-2-Clause'}]})
    chosen=next(f for f in distinct.passages if f.locator=='rows[0].name')
    selected=project(plan,distinct,chosen,'ISC')
    check('no-neighbor-record-borrowing',selected,None)
    prose=Passage('River uses MIT OR Apache-2.0.',locator='p[0]')
    check('no-unlabeled-prose-rewrite',project(plan,p,prose,'MIT'),None)
    wrong=Passage('Description: MIT OR Apache-2.0','Description','MIT OR Apache-2.0',kind='field',locator='dl[0]')
    check('no-arbitrary-label-rewrite',project(plan,p,wrong,'MIT'),None)
    c=Candidate('MIT','MIT',url,field.text,field.label,field.section,'license',10,{'locator':field.locator})
    check('partial-candidate-rejected',verify(c,plan,[p]),False)
    full=replace(c,raw='MIT OR Apache-2.0',answer='MIT OR Apache-2.0')
    check('full-candidate-supported',verify(full,plan,[p]),True)
    check('answer-fragment-rejected',verify(replace(full,answer='MIT'),plan,[p]),False)
    check('forged-field-value-rejected',verify(replace(c,signals={'field_value':'MIT','qualifiers':{'license':'MIT'}}),plan,[p]),False)
    check('forged-source-rejected',verify(replace(full,source='https://other.example.org/record'),plan,[p]),False)
    check('forged-evidence-rejected',verify(replace(full,evidence='license: MIT OR ISC'),plan,[p]),False)
    check('parent-context-partial-rejected',verify(replace(c,evidence=name.text,label=name.label,signals={'locator':'name'}),plan,[p]),False)
    value=' OR '.join(['LicenseRef-Long'+str(i) for i in range(24)])
    long=page({'license':value});long_field=long.passages[0]
    check('long-expression-no-overflow',project(plan,long,long_field,'LicenseRef-Long0'),None)
    check('long-expression-no-fragment',complete(plan,long,long_field,'LicenseRef-Long0'),False)
    # Index invalidates when parsed source passages are added.
    project(plan,p,name,'MIT')
    p.passages.append(Passage('license expression: MIT OR ISC','license expression','MIT OR ISC',kind='json',locator='license_expression'))
    check('ambiguous-siblings-no-rewrite',project(plan,p,name,'MIT'),None)
    check('source-index-append-invalidates',complete(plan,p,name,'MIT'),False)
    return rows


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args();target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    rows=diagnose();report=dict(scope=__doc__,passed=sum(r['passed'] for r in rows),total=len(rows),rows=rows,
        production_sha256={p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path('app.py'),*sorted(Path('agent').glob('*.py'))]})
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=report['passed'],total=report['total'],failures=[r['id'] for r in rows if not r['passed']])))
    if report['passed']!=report['total']:sys.exit(1)
