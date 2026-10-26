"""Fixed challenge captures and actual loopback HTTP; no GPU or browser launch.

Browser rendering is a spy. This measures source classification and recovery,
not model answers, unseen accuracy, or time saved by a real browser.
"""
import argparse
import asyncio
import base64
import hashlib
import importlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from aiohttp import web
from agent.engine import Engine
from agent.network import Response
from agent.parser import parse_response
from agent.types import Settings
from revision_engine import load_engine


AWS = '<html><title></title><script src="https://a.token.awswaf.com/a/challenge.js"></script><body><div id="challenge-container"></div><noscript>JavaScript is disabled</noscript></body></html>'
RECAPTCHA = '<html><title>Checking your browser - reCAPTCHA</title><base href="https://www.google.com/recaptcha/challengepage/"><body><div>Checking your browser before accessing example.org</div></body></html>'
ARTICLE = '<h1>Boreal Instruments support</h1><dl><dt>Support phone</dt><dd>+1 202-555-0148</dd></dl>'


def fixtures():
    source = ROOT / 'research/external-disjoint12b-20261023-repeat/simpleqa-516.json'
    report = json.loads((ROOT / 'benchmarks/external-disjoint12b-20261023-repeat.json').read_text(encoding='utf-8'))
    row = next(r for r in report['rows'] if r['id'] == 'simpleqa-516')
    assert hashlib.sha256(source.read_bytes()).hexdigest() == row['capture_sha256']
    responses = json.loads(source.read_text(encoding='utf-8'))
    cases = []
    for name, url, error in [
        ('actual-ieee', 'https://ieeexplore.ieee.org/document/10361706', 'challenge_aws_waf'),
        ('actual-pmc', 'https://pmc.ncbi.nlm.nih.gov/articles/PMC8970926/', 'challenge_recaptcha'),
    ]:
        data = dict(responses[url]);data['body'] = base64.b64decode(data.pop('body_base64'))
        cases.append((name, Response(**data), error))
    for name, html, status, error in [
        ('aws-shell', AWS, 202, 'challenge_aws_waf'),
        ('aws-relative-script', AWS.replace('https://a.', '//a.'), 202, 'challenge_aws_waf'),
        ('aws-lookalike', AWS.replace('token.awswaf.com/', 'token.awswaf.com.example.org/'), 202, ''),
        ('aws-other-path', AWS.replace('/challenge.js', '/integration.js'), 202, ''),
        ('aws-ordinary-status', AWS, 200, ''),
        ('aws-article-widget', AWS.replace('</body>', '<article>' + ARTICLE + '</article></body>'), 202, ''),
        ('aws-long-document', AWS.replace('</body>', '<p>' + 'A readable source sentence. ' * 40 + '</p></body>'), 202, ''),
        ('accepted-article', '<html><p>Research was accepted for review.</p></html>', 202, ''),
        ('challenge-discussion', '<h1>AWS WAF challenge.js</h1><p>How the challenge-container works.</p>', 202, ''),
        ('recaptcha-shell', RECAPTCHA, 200, 'challenge_recaptcha'),
        ('recaptcha-title-only', RECAPTCHA.replace('<base href="https://www.google.com/recaptcha/challengepage/">', ''), 200, ''),
        ('recaptcha-lookalike', RECAPTCHA.replace('www.google.com/', 'www.google.com.example.org/'), 200, ''),
        ('recaptcha-other-path', RECAPTCHA.replace('/recaptcha/challengepage/', '/recaptcha/about/'), 200, ''),
        ('recaptcha-article', RECAPTCHA.replace('</body>', '<article>Browser verification is the subject of this article.</article></body>'), 200, ''),
        ('widget-on-source', '<title>Boreal Instruments</title><script src="https://www.google.com/recaptcha/enterprise.js"></script>' + ARTICLE, 200, ''),
        ('js-application', '<html><div id="app"></div><script src="/app.js"></script></html>', 200, ''),
        ('invalid-script-url', AWS.replace('https://a.token.awswaf.com/a/challenge.js', 'https://['), 202, ''),
        ('old-soft-error', '<title>Access denied</title><p>Please sign in.</p>', 200, 'soft_error_page'),
    ]:
        cases.append((name, Response('https://example.org/source', html.encode(), 'text/html', status=status), error))
    return cases, row['capture_sha256']


def parse_checks(parser, cases):
    rows = []
    for name, response, expected in cases:
        page = parser(response)
        passed = page.error == expected
        if expected.startswith('challenge_'):
            passed = passed and not page.passages and not page.links and not page.dynamic
        if name == 'js-application':passed = passed and page.dynamic
        if name in {'aws-article-widget', 'widget-on-source', 'accepted-article'}:passed = passed and bool(page.passages)
        rows.append(dict(id=name, passed=passed, expected=expected, error=page.error,
                         dynamic=page.dynamic, passages=len(page.passages), links=len(page.links)))
    return rows


async def engine_checks(engine, cases):
    hits = [];renders = [];mode = '';base = ''
    captures = {name:response for name,response,error in cases if name.startswith('actual-')}
    async def handler(request):
        hits.append(request.path)
        if request.path == '/provider':
            return web.Response(text='<li class="b_algo"><h2><a href="' + base + '/contact">Boreal Instruments support phone</a></h2></li>', content_type='text/html')
        if request.path == '/contact':return web.Response(text=ARTICLE, content_type='text/html')
        if mode == 'js-app':return web.Response(text='<div id="app"></div><script src="/app.js"></script>', content_type='text/html')
        response = captures[mode.replace('-recovery', '')]
        return web.Response(body=response.body, status=response.status, headers={'content-type':response.content_type})
    async def render(url, *args, **kwargs):
        renders.append(url)
        return None, {'state':'spy_no_browser_launch'}
    app = web.Application();app.router.add_get('/{tail:.*}', handler)
    runner = web.AppRunner(app);await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0);await site.start()
    base = 'http://127.0.0.1:' + str(site._server.sockets[0].getsockname()[1])
    module = engine.__module__.rsplit('.', 1)[0];browser = importlib.import_module(module + '.browser')
    rows = []
    try:
        with patch.object(browser, 'render', render):
            for mode in ['actual-ieee', 'actual-pmc', 'js-app', 'actual-ieee-recovery', 'actual-pmc-recovery']:
                hits.clear();renders.clear();recovery = mode.endswith('-recovery')
                settings = Settings(model_url='', search=recovery, browser=True, allow_private=True,
                                    budget=9, max_depth=1 if recovery else 0,
                                    search_providers=[(base+'/provider?q=', 'bing')])
                result = await engine(settings).run('What is the support phone of Boreal Instruments?', base+'/start')
                passed = len(renders) == (1 if mode == 'js-app' else 0)
                if recovery:passed = passed and result.answer == '+1 202-555-0148' and result.sources == [base+'/contact']
                else:passed = passed and not result.answer and not result.sources
                rows.append(dict(id=mode, passed=passed, browser_spy_calls=len(renders),
                                 hits=list(hits), result=result.internal()))
    finally:await runner.cleanup()
    return rows


if __name__ == '__main__':
    ap = argparse.ArgumentParser();ap.add_argument('--out', required=True);args = ap.parse_args();target = Path(args.out)
    if target.exists():raise FileExistsError(target)
    cases, capture_sha = fixtures()
    old, revision, hashes = load_engine('299eee3')
    parser = importlib.import_module(old.__module__.rsplit('.', 1)[0]+'.parser').parse_response
    before = parse_checks(parser, cases) + asyncio.run(engine_checks(old, cases))
    after = parse_checks(parse_response, cases) + asyncio.run(engine_checks(Engine, cases))
    report = dict(scope=__doc__, baseline_revision=revision, baseline_source_sha256=hashes,
                  capture_sha256=capture_sha, before=before, after=after,
                  before_passed=sum(r['passed'] for r in before), after_passed=sum(r['passed'] for r in after), total=len(after),
                  wins=[a['id'] for b,a in zip(before,after) if a['passed'] and not b['passed']],
                  losses=[a['id'] for b,a in zip(before,after) if b['passed'] and not a['passed']],
                  production_sha256={p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('agent').glob('*.py')})
    target.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['before_passed','after_passed','total','wins','losses']}))
    if not all(r['passed'] for r in after):sys.exit(1)
