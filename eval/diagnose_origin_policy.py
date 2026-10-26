"""Source queue policy invariants; direct data checks, no network/model/accuracy claim."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from agent.engine import recover_origins


def diagnose():
    rows=[]
    a='https://a.example/';b='https://b.example/';c='https://c.example/'
    f=[(a+'0','A0'),(a+'1','A1'),(b+'0','B0')]
    p=[(b+'1','B1'),(a+'2','A2'),(c+'0','C0')]
    def denied(url,final=None):return {'url':url,'final':final or url,'status':403,'error':'http_403'}
    def repeated(url):return [denied(url),denied(url+'-second')]
    def run(name,events,expected,frontier=None,pending=None,providers=(),target=''):
        frontier=f if frontier is None else frontier;pending=p if pending is None else pending
        active,waiting,trace=recover_origins(frontier,pending,events,providers,target)
        actual=[u for u,l in active]
        preserved={u for u,l in active+waiting}=={u for u,l in frontier+pending}
        passed=actual==expected and preserved and len(active)<=len(frontier)
        rows.append(dict(id=name,passed=bool(passed),expected=expected,actual=actual,
            every_source_retained=preserved,trace=trace,pending=[u for u,l in waiting]))
    original=[u for u,l in f];recovered=[b+'0',b+'1',c+'0']
    run('no-denial',[],original)
    run('denied-origin-moves-back',repeated(a+'start'),recovered)
    run('one-denial-is-resource-specific',[denied(a+'start')],original)
    run('same-resource-does-not-count-twice',[denied(a+'start'),denied(a+'start')],original)
    run('404-is-resource-specific',[{'url':a+'missing','status':404,'error':'http_404'}],original)
    run('429-has-no-new-policy',[{'url':a+'limited','status':429,'error':'http_429'}],original)
    run('later-success-restores-origin',repeated(a+'start')+[{'url':a+'public','status':200,'error':''}],original)
    run('known-readable-origin-keeps-priority',[{'url':a+'public','status':200,'error':''}]+repeated(a+'start'),original)
    run('failed-success-does-not-clear',repeated(a+'start')+[{'url':a+'large','status':200,'error':'body_limit'}],recovered)
    run('all-same-origin-kept',repeated(a+'start'),[a+'0',a+'1'],frontier=f[:2],pending=[(a+'2','A2')])
    run('explicit-navigation-target-kept',repeated(a+'start'),[a+'1',b+'0',b+'1'],target=a+'1')
    run('unrelated-origin-no-effect',[denied('https://other.example/start')],original)
    run('custom-search-provider-not-content',repeated(a+'provider?q=test'),original,providers=[(a+'provider?q=','bing')])
    google='https://www.google.com/'
    run('standard-search-not-content',repeated(google+'search?q=test'),[google+'about',b+'0'],
        frontier=[(google+'about','Google'),(b+'0','B0')],pending=[(c+'0','C0')])
    run('redirect-observation-is-final-origin',[denied(a+'redirect',b+'blocked'),denied(a+'redirect2',b+'blocked2')],[a+'0',a+'1',a+'2'])
    run('canonical-default-port',repeated('HTTPS://A.EXAMPLE:443/start'),recovered)
    run('other-port-independent',[denied('https://a.example:8443/start')],original)
    signed=a+'signed?X-Amz-Signature=literal%2B&x=1'
    run('signed-url-retained',repeated(a+'start'),[b+'0'],frontier=[(signed,'signed')],pending=[(b+'0','B0')])
    run('empty-active-does-not-expand',[denied(a+'start')],[],frontier=[])
    run('invalid-observation-ignored',[denied('http://[broken')],original)
    return rows


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args();target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    rows=diagnose();report=dict(scope=__doc__,passed=sum(r['passed'] for r in rows),total=len(rows),rows=rows,
        engine_sha256=hashlib.sha256((ROOT/'agent/engine.py').read_bytes()).hexdigest())
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=report['passed'],total=report['total'],failures=[r['id'] for r in rows if not r['passed']])))
    if report['passed']!=report['total']:sys.exit(1)
