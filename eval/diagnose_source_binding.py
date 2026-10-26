"""Authored CPU source-binding controls, not independent question accuracy."""
import argparse
import asyncio
from dataclasses import replace
import hashlib
import importlib
import json
from pathlib import Path
import sys

from aiohttp import web

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.engine import Engine
from revision_engine import load_engine


async def diagnose(engine):
    package = engine.__module__.rsplit('.', 1)[0]
    types = importlib.import_module(package + '.types')
    verify = importlib.import_module(package + '.candidates').verify
    semantic = importlib.import_module(package + '.selector').verify_selection
    plan_query = importlib.import_module(package + '.planner').plan_query
    Page, Passage, Candidate = types.Page, types.Passage, types.Candidate
    url = 'https://example.org/awards'
    plan = plan_query('Who won the award in 2024?')
    facts = [Passage('Winner: Elm Choir', 'Winner', 'Elm Choir', 'Awards ' + year,
                     'field', 'row[' + str(i) + ']', {'record': i})
             for i, year in enumerate(['2023', '2024'])]
    page = Page(url, passages=facts)
    c = Candidate('Elm Choir', 'Elm Choir', url, facts[1].text, facts[1].label,
                  facts[1].section, signals={'locator': facts[1].locator,
                  'structure': facts[1].kind, 'field_value': facts[1].value,
                  'qualifiers': dict(facts[1].qualifiers)})
    rows = []

    def check(name, candidate, pages, expected, query=plan):
        actual = verify(candidate, query, pages)
        rows.append({'id': name, 'passed': actual == expected, 'actual': actual, 'expected': expected})

    check('selected-second-year', c, [page], True)
    check('selected-year-order-independent', c, [Page(url, passages=list(reversed(facts)))], True)
    check('wrong-year-still-rejected', replace(c, section=facts[0].section,
          signals={**c.signals, 'locator': facts[0].locator, 'qualifiers': facts[0].qualifiers}), [page], False)
    for key, value in [('locator', 'missing'), ('structure', 'json'), ('field_value', 'Birch Choir'),
                       ('qualifiers', {'record': 0})]:
        check('forged-' + key, replace(c, signals={**c.signals, key: value}), [page], False)
    for key, value in [('section', 'Awards 2025'), ('label', 'Nominee'), ('source', url + '/fake')]:
        check('forged-' + key, replace(c, **{key: value}), [page], False)
    check('errored-source', c, [replace(page, error='unavailable')], False)
    check('legacy-unique', replace(c, label='', section='', signals={}), [Page(url, passages=[facts[1]])], True)
    check('legacy-missing-scope-cannot-bypass-year', replace(c, label='', section='', signals={}),
          [Page(url, passages=[facts[0]])], False)
    check('legacy-ambiguous', replace(c, label='', section='', signals={}), [page], False)
    check('ambiguous-qualifiers', replace(c, signals={'locator': 'row[1]'}),
          [Page(url, passages=[facts[1], replace(facts[1], qualifiers={'record': 9})])], False)
    check('conflicting-page-instances', c, [page, replace(page, title='Other source identity')], False)
    check('identical-duplicate-record', c, [Page(url, passages=[facts[1], replace(facts[1])])], True)
    check('explicit-empty-locator', replace(c, signals={**c.signals, 'locator': ''}),
          [Page(url, passages=[replace(facts[1], locator='')])], True)

    member_plan = plan_query('Which two authors won the Cedar Prize in 1998?')
    member_facts = [Passage('Winners: Mira Chen and Orin Vale', 'Winners', 'Mira Chen and Orin Vale',
                           'Cedar Prize ' + year, 'field', 'winners[' + str(i) + ']')
                    for i, year in enumerate(['1997', '1998'])]
    members = Candidate('Mira Chen and Orin Vale', 'Mira Chen and Orin Vale', url, member_facts[1].text,
                        'Winners', 'Cedar Prize 1998', signals={'locator': member_facts[1].locator,
                        'literal_spans': ['Mira Chen', 'Orin Vale']})
    check('members-selected-second-year', members, [Page(url, passages=member_facts)], True, member_plan)
    check('members-forged-scope', replace(members, section='Cedar Prize 1999'),
          [Page(url, passages=member_facts)], False, member_plan)
    check('members-wrong-year', replace(members, section='Cedar Prize 1997',
          signals={**members.signals, 'locator': member_facts[0].locator}),
          [Page(url, passages=member_facts)], False, member_plan)

    active = ('forward', True, '2024')
    calls = []

    async def source(request):
        years = ['2024', '2023'] if active[0] == 'reverse' else ['2023', '2024']
        html = ''.join('<h2>Awards ' + year + '</h2><p><b>Winner:</b> Elm Choir</p>' for year in years)
        return web.Response(text=html, content_type='text/html')

    async def model(request):
        data = await request.json()
        calls.append({'path': request.path, 'data': data})
        if request.path == '/verify':
            supported = active[1] and data['passages'][0]['section'] == 'Awards 2024'
            return web.json_response({'supported': supported})
        selected = next(p for p in data['passages'] if p['section'] == 'Awards ' + active[2]
                        and 'Winner' in p['text'] and 'Elm Choir' in p['text'])
        return web.json_response({'candidate': -1, 'passage': selected['id'], 'answer': 'Elm Choir'})

    app = web.Application()
    app.router.add_get('/source', source)
    app.router.add_post('/{tail:.*}', model)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0)
    await site.start()
    base = 'http://127.0.0.1:' + str(site._server.sockets[0].getsockname()[1])
    settings = types.Settings(model_url=base, allow_private=True, search=False, browser=False, max_depth=0, budget=5)
    try:
        for active in [('forward', True, '2024'), ('reverse', True, '2024'),
                       ('semantic-reject', False, '2024'), ('wrong-year', True, '2023')]:
            calls.clear()
            result = await engine(settings).run(plan.question, base + '/source')
            expected = 'Elm Choir' if active[1] and active[2] == '2024' else ''
            passed = (result.answer == expected and result.sources == ([base + '/source'] if expected else [])
                      and not result.diagnostics.get('errors'))
            if expected:
                passed = passed and [r['path'] for r in calls] == ['/select', '/verify']
            if active[0] == 'semantic-reject':
                passed = passed and any(r['path'] == '/verify' for r in calls)
            rows.append({'id': 'http-' + active[0], 'passed': passed, 'answer': result.answer,
                         'reason': result.reason, 'calls': list(calls)})

        # Independent semantic verification must bind the same real record,
        # and must reject forged source metadata before calling the endpoint.
        active = ('forward', True, '2024')
        ranked = [(page, p, 1) for p in facts]
        for name, chosen, should_call in [('valid', c, True), ('forged-scope', replace(c, section='Awards 2025'), False),
                                          ('forged-field', replace(c, label='Nominee'), False),
                                          ('forged-locator', replace(c, signals={**c.signals, 'locator': 'missing'}), False)]:
            calls.clear()
            supported, state = await semantic(plan, chosen, ranked, settings, types.Deadline(5))
            contexts = calls[0]['data']['passages'] if calls else []
            passed = (supported == should_call and bool(calls) == should_call)
            if should_call:
                passed = passed and len(contexts) == 2 and contexts[0]['section'] == 'Awards 2024'
            rows.append({'id': 'semantic-' + name, 'passed': passed, 'state': state,
                         'supported': supported, 'calls': list(calls)})
        calls.clear()
        empty_page = Page(url, passages=[replace(p, locator='') for p in facts])
        supported, state = await semantic(plan, replace(c, signals={**c.signals, 'locator': ''}),
                                         [(empty_page, p, 1) for p in empty_page.passages], settings, types.Deadline(5))
        contexts = calls[0]['data']['passages'] if calls else []
        rows.append({'id': 'semantic-empty-locator-scopes', 'passed': supported and len(contexts) == 2
                     and contexts[0]['section'] == 'Awards 2024', 'state': state, 'calls': list(calls)})
    finally:
        await runner.cleanup()
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    out = Path(args.out)
    if out.exists():
        raise FileExistsError(out)
    old, revision, hashes = load_engine('5c63d23')

    async def run():
        return await diagnose(old), await diagnose(Engine)

    before, after = asyncio.run(run())
    report = {'scope': __doc__, 'baseline': revision, 'baseline_hashes': hashes, 'before': before, 'after': after,
              'before_passed': sum(r['passed'] for r in before), 'after_passed': sum(r['passed'] for r in after),
              'total': len(after), 'torch_imported': 'torch' in sys.modules,
              'diagnostic_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'production_sha256': {p.as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                    for p in sorted(Path('agent').glob('*.py'))}}
    report['wins'] = [a['id'] for b, a in zip(before, after) if a['passed'] and not b['passed']]
    report['losses'] = [a['id'] for b, a in zip(before, after) if b['passed'] and not a['passed']]
    with out.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps({k: report[k] for k in ['before_passed', 'after_passed', 'total', 'wins', 'losses', 'torch_imported']}))
    print(json.dumps([{'id': r['id'], 'actual': r.get('actual'), 'reason': r.get('reason')}
                      for r in after if not r['passed']]))
    if not all(r['passed'] for r in after):
        sys.exit(1)
