"""Executable proof checks with real source spans, including adversarial literal premises."""
from dataclasses import replace
import asyncio
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from agent.network import Response
from agent.parser import parse_response
from agent.planner import plan_query
from agent.proofs import Atom,Proof,propose,validate
from agent.engine import Engine
from agent.types import Settings
from benchmarks.fakeweb import FakeWeb
from aiohttp import web


def page(url,html):return parse_response(Response(url=url,content_type='text/html',body=html.encode()))


def diagnose():
    cases=json.loads((ROOT/'benchmarks/proof-20261023-cases.json').read_text(encoding='utf-8'))
    routes=json.loads((ROOT/'fixtures/proof-20261023.json').read_text(encoding='utf-8'))
    saved={};rows=[]
    for case in cases:
        prefix='/'.join(case['path'].split('/')[:-1])+'/'
        pages=[page('https://example.org'+path,r[2]) for path,r in routes.items() if path.startswith(prefix)]
        plan=plan_query(case['query'],'https://example.org'+case['path'])
        proof,required=propose(plan,pages)
        derived=case['id'][:2] in {'07','09','16'}
        expected_required=case['id'] not in {'single-fee','single-table'}
        passed=(proof is not None)==derived and required==expected_required
        if proof:passed=passed and validate(proof,plan,pages) and proof.answer in case['answers']
        rows.append({'id':case['id'],'passed':passed,'proof_answer':proof.answer if proof else None,'required':required})
        saved[case['id']]=(plan,pages,proof)

    def check(name,proof,plan,pages):
        rows.append({'id':name,'passed':not validate(proof,plan,pages)})

    plan,pages,proof=saved['09-web-table-cell']
    target=next(p for p in pages if p.url.endswith('schedule.html'))
    other=next(p for p in target.passages if p.kind=='table' and 'Glass' in p.text)
    wrong=Atom(target.url,other.locator,other.text,other.qualifiers['cells'][2],'hours')
    check('literal_parts_from_different_rows',replace(proof,atoms=(proof.atoms[0],wrong)),plan,pages)
    check('missing_required_component',replace(proof,atoms=proof.atoms[:1]),plan,pages)

    plan,pages,proof=saved['07-doc-cross-version-comparison']
    check('wrong_requested_version',replace(proof,atoms=(replace(proof.atoms[0],version='4'),proof.atoms[1])),plan,pages)
    changed=page('https://example.org/07-doc-cross-version-comparison/v3.html',
        '<title>FernAPI v3 request quota</title><p>The per-client request quota in version 3 is 80 requests per hour.</p>')
    p=next(p for p in changed.passages if '80 requests' in p.text)
    atom=Atom(changed.url,p.locator,p.text,'80 requests per hour','3',version='3')
    check('incompatible_units',replace(proof,atoms=(proof.atoms[0],atom)),plan,[*pages,changed])
    conflict=page('https://example.org/07-doc-cross-version-comparison/alternate-v3.html',
        '<title>FernAPI v3 request quota</title><p>The per-client request quota in version 3 is 90 requests per minute.</p>')
    check('conflicting_same_version',proof,plan,[*pages,conflict])
    preview=page('https://example.org/07-doc-cross-version-comparison/v3beta.html',
        '<title>FernAPI v3beta request quota</title><p>The per-client request quota in version 3 is 80 requests per minute.</p>')
    p=next(p for p in preview.passages if '80 requests' in p.text)
    atom=Atom(preview.url,p.locator,p.text,'80 requests per minute','3',version='3')
    check('preview_is_not_requested_release',replace(proof,atoms=(proof.atoms[0],atom)),plan,[*pages,preview])

    plan,pages,proof=saved['16-web-two-source-mapping']
    fees=next(p for p in pages if p.url.endswith('fees.html'))
    other=next(p for p in fees.passages if p.kind=='prose' and '$32' in p.text)
    wrong=Atom(fees.url,other.locator,other.text,'$32','value',key='F',relation='category')
    check('different_join_key',replace(proof,atoms=(proof.atoms[0],wrong)),plan,pages)
    check('fabricated_mapping_value',replace(proof,atoms=(replace(proof.atoms[0],value='C'),proof.atoms[1])),plan,pages)
    foreign=replace(fees,url='https://unrelated.example/fees.html')
    check('unrelated_origin',replace(proof,atoms=(proof.atoms[0],replace(proof.atoms[1],source=foreign.url))),plan,[*pages,foreign])
    conflict=page('https://example.org/16-web-two-source-mapping/alternate.html',
        '<title>Blue Lantern market categories</title><p>Book vendors are assigned category C.</p>')
    check('conflicting_mapping_proof',proof,plan,[*pages,conflict])
    check('join_cannot_replace_comparison',proof,replace(plan,operation='compare_versions',versions=['2','3']),pages)
    check('join_cannot_answer_person',proof,replace(plan,kind='text'),pages)
    return {'scope':__doc__,'rows':rows,'passed':sum(r['passed'] for r in rows),'total':len(rows)}


async def transport_checks():
    """A real model HTTP boundary rejects proofs; no gold is sent to production."""
    mode='busy'
    async def handler(request):
        await request.read()
        if request.path=='/verify':
            if mode=='busy':return web.json_response({'error':'busy'},status=503)
            if mode=='invalid':return web.json_response({'supported':'yes'})
            return web.json_response({'supported':False})
        return web.json_response({'passage':-1,'answer':''})
    app=web.Application();app.router.add_post('/{path}',handler)
    runner=web.AppRunner(app);await runner.setup()
    site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    url='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])
    cases=json.loads((ROOT/'benchmarks/proof-20261023-cases.json').read_text(encoding='utf-8'))[:3]
    routes=json.loads((ROOT/'fixtures/proof-20261023.json').read_text(encoding='utf-8'))
    rows=[]
    try:
        with FakeWeb(routes) as source:
            for mode,reason in [('busy','proof_service_unavailable'),('reject','proof_semantic_rejection'),('invalid','proof_invalid_reply')]:
                for case in cases if mode!='invalid' else cases[:1]:
                    # Supply the table page directly: this check targets the
                    # verifier boundary, not the model's navigation decision.
                    start=case['source_paths'][0] if case['id'].startswith('09-') else case['path']
                    result=await Engine(Settings(model_url=url,search=False,allow_private=True,max_depth=2,budget=8)).run(
                        case['query'],source.base+start)
                    rows.append({'id':case['id']+'_'+mode,'passed':not result.answer and not result.sources
                        and result.reason==reason and bool(result.diagnostics.get('proof_verification')),
                        'result':result.internal()})
    finally:await runner.cleanup()
    return rows


if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args()
    target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    report=diagnose()
    report['rows'].extend(asyncio.run(transport_checks()))
    report['scope']+=' Plus actual HTTP verification rejection/unavailability/protocol checks.'
    report['passed']=sum(row['passed'] for row in report['rows']);report['total']=len(report['rows'])
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'total':report['total'],'failures':[r['id'] for r in report['rows'] if not r['passed']]}))
    if report['passed']!=report['total']:sys.exit(1)
