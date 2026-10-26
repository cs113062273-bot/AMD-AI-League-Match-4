"""Seeded external assessment; no filtering by topic, difficulty, host or outcome."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import random
import re
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent.normalize import iso_date
from eval.external_urls import supporting_urls


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--count',type=int,default=20)
    parser.add_argument('--seed',type=int,default=940217)
    parser.add_argument('--out',default='benchmarks/external-simpleqa20.json')
    parser.add_argument('--exclude',action='append',default=[],help='Previously exposed case files; exclude their upstream row positions')
    parser.add_argument('--starting-url',choices=('first-gold','none'),default='first-gold',
        help='first-gold preserves the source-assisted assessment; none supplies only the question to the engine')
    args=parser.parse_args()
    root=Path('research/external-simpleqa')
    metadata=json.loads((root/'metadata.json').read_text(encoding='utf-8'))
    body=(root/'simpleqa_verified.csv').read_bytes()
    rows=list(csv.DictReader(io.StringIO(body.decode('utf-8-sig'))))
    excluded=set()
    exclusions=[]
    for name in args.exclude:
        path=Path(name)
        prior=json.loads(path.read_text(encoding='utf-8'))
        excluded.update(item['upstream_row'] for item in prior)
        exclusions.append({'path':path.as_posix(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'n':len(prior)})
    eligible=[position for position in range(len(rows)) if position not in excluded]
    if not 1<=args.count<=len(eligible):parser.error('count must fit the remaining eligible population')
    positions=random.Random(args.seed).sample(eligible,args.count)
    cases=[]
    for position in positions:
        row=rows[position]
        urls=supporting_urls(row['urls'])
        if not urls or not all(urls):raise ValueError('Selected row lacks valid supporting URLs; do not silently replace it')
        answers=[row['answer']]
        date=iso_date(row['answer'])
        if date and date not in answers:answers.append(date)
        if re.fullmatch(r'\d+(?:,\d{3})*',row['answer']):
            number=int(row['answer'].replace(',',''))
            answers=list(dict.fromkeys([*answers,str(number),f'{number:,}']))
        cases.append({'id':'simpleqa-'+row['original_index'],'family':'external-'+row['answer_type'],
            'query':row['problem'],'url':urls[0] if args.starting_url=='first-gold' else '',
            'answer':row['answer'],'answers':answers,'sources':urls,
            'upstream_row':position,'upstream_topic':row['topic'],'multi_step':row['multi_step']})
    output=Path(args.out)
    if output.exists():raise FileExistsError('Frozen assessment already exists')
    output.write_text(json.dumps(cases,indent=2,ensure_ascii=False),encoding='utf-8')
    production=[Path('app.py'),*Path('agent').glob('*.py')]
    manifest={'status':'FROZEN_BEFORE_FIRST_RUN','selection_seed':args.seed,'n':args.count,'eligible_rows':len(eligible),
        'selection':'Uniform sample of rows excluding previously exposed assessments; no source/topic/difficulty/answerability filtering.',
        'excluded_assessments':exclusions,
        'url_preprocessing':'Split comma-delimited HTTP URLs including individually quoted entries; remove matching list quotes; preserve path spelling and punctuation. Deduplicate exact canonical URLs.',
        'upstream':'google/simpleqa-verified','revision':metadata['sha'],'upstream_license':metadata['cardData']['license'],
        'csv_sha256':hashlib.sha256(body).hexdigest(),'cases_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
        'production_sha256':{p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in production},
        'starting_url_mode':args.starting_url,
        'adaptation':('Starting URL is the first gold URL. ' if args.starting_url=='first-gold' else
            'Question-only engine input; no starting URL is supplied from gold sources. ')+
            'Exact answer/source scoring with predeclared ISO-date and integer grouping aliases; not the official SimpleQA autorater.'}
    output.with_name(output.stem+'-freeze.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('Frozen',args.count,'external cases from',len(eligible),'eligible rows; revision',metadata['sha'])


if __name__=='__main__':main()
