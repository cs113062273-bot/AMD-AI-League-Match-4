"""Small structural diagnosis for calendar precision and compact DOM record scope."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from agent.planner import plan_query
from agent.normalize import normalize,iso_month,literal_span
from agent.parser import parse_response
from agent.network import Response
from agent.candidates import extract,verify
from agent.engine import rank_passages
from agent.selector import payload


def diagnose():
    rows=[]
    def check(name,value):rows.append({'id':name,'passed':bool(value)})
    for i,question in enumerate(['Which month and year was Oriole appointed?',
        'What is the month and year of the appointment?','In what month and year was Oriole appointed?',
        'Which year and month was Oriole appointed?','What were the year and month when Oriole retired?',
        'What month and year did Oriole retire?']):
        plan=plan_query(question)
        check('month-intent-'+str(i),plan.kind=='date' and plan.date_precision=='month' and plan.operation=='single')
    for question in ['In what year was Oriole appointed?','What day, month, and year was Oriole appointed?',
                     'How many months and years did Oriole serve?']:
        check('preserve-'+question,not plan_query(question).date_precision)
    for raw,expected in [('February 14, 1942','February 1942'),('2024-02-29','February 2024'),
                         ('Feb 1942','February 1942'),('1942-02','February 1942')]:
        check('projection-'+raw,normalize(raw,'date','month')==expected)
    for raw in ['2023-02-29','1942-13','February 30, 1942','February','1942']:
        check('invalid-'+raw,not iso_month(raw))
    check('no-invalid-day-prefix',not literal_span('1942-02','Date: 1942-02-99','date'))
    plan=plan_query('Which month and year was Oriole appointed?','https://example.com/appointment')
    page=parse_response(Response(plan.url,b'<title>Oriole appointment</title><p>Oriole was appointed on February 14, 1942.</p>','text/html',status=200))
    valid=[candidate for candidate in extract(plan,page) if verify(candidate,plan,[page])]
    check('verified-calendar-projection',any(c.raw=='February 14, 1942' and c.answer=='February 1942' for c in valid))
    check('changed-projection-rejected',bool(valid) and not verify(replace(valid[0],answer='April 1942'),plan,[page]))
    html=b'''<title>Ridge Academy awardees</title><h1>Awardees</h1>
    <article data-year="1987" data-surname="Voss" data-id="private-42"><div>1987</div><div>Elin Voss</div><div>Biochemist</div></article>
    <article><div>1993</div><div>Marin Shaw</div><div>Physicist</div></article>
    <div role="row"><span>1999</span><span>Nora Hart</span><span>Artist</span></div>
    <article><h2>Long biography</h2><p>'''+b'Long prose. '*100+b'</p></article>'
    page=parse_response(Response('https://example.com/awards',html,'text/html',status=200))
    records=[p.text for p in page.passages if p.kind=='record']
    check('compact-records',records==['1987 | Elin Voss | Biochemist','1993 | Marin Shaw | Physicist','1999 | Nora Hart | Artist'])
    check('no-cross-record-fusion',all(not ('Voss' in text and 'Shaw' in text) for text in records))
    record=next(p for p in page.passages if p.kind=='record' and 'Voss' in p.text)
    check('visible-record-source-fields',record.qualifiers.get('source_fields')=={'year':'1987','surname':'Voss'})
    check('no-sibling-field-inheritance',all(not p.qualifiers.get('source_fields') for p in page.passages if p.kind=='record' and 'Shaw' in p.text))
    plan=plan_query('In what year did Elin Voss receive the Ridge Academy award?',page.url)
    data=payload(plan,[],rank_passages(plan,[page]))
    check('record-source-headings',any(p.get('document_headings')==['Awardees','Long biography'] for p in data['passages'] if 'Voss' in p['text']))
    check('source-fields-reach-model',any(p.get('source_fields')=={'year':'1987','surname':'Voss'} for p in data['passages'] if 'Voss' in p['text']))
    return {'scope':__doc__,'passed':sum(row['passed'] for row in rows),'total':len(rows),'rows':rows}


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args();target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    report=diagnose();target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'total':report['total'],'failures':[row['id'] for row in report['rows'] if not row['passed']]}))
    if report['passed']!=report['total']:sys.exit(1)
