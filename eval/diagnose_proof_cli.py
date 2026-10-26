"""Fresh CLI serialization of a real two-page proof with a controlled semantic service.

This checks process/output integration, not model accuracy or official acceptance.
"""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from benchmarks.fakeweb import FakeWeb


if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args()
    target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length','0')))
            reply={'supported':True} if self.path=='/verify' else {'passage':-1,'answer':''}
            body=json.dumps(reply).encode()
            self.send_response(200);self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    service=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    service.daemon_threads=True
    thread=threading.Thread(target=service.serve_forever,daemon=True);thread.start()
    try:
        routes=json.loads((ROOT/'fixtures/proof-20261023.json').read_text(encoding='utf-8'))
        cases=json.loads((ROOT/'benchmarks/proof-20261023-cases.json').read_text(encoding='utf-8'))
        case=next(c for c in cases if c['id'].startswith('16-'))
        with FakeWeb(routes) as web:
            env=dict(os.environ,APERTURE_ALLOW_PRIVATE='1',APERTURE_SEARCH='0',PYTHONIOENCODING='utf-8',
                     APERTURE_MODEL_URL='http://127.0.0.1:'+str(service.server_port))
            process=subprocess.run([sys.executable,'app.py','--query-id','proof-cli-20261023',
                '--query',case['query'],'--url',web.base+case['path'],'--diagnostics',
                '--output-dir','output/proof-20261023'],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',timeout=30)
            output=ROOT/'output/proof-20261023/proof-cli-20261023_output.json'
            result=json.loads(output.read_text(encoding='utf-8'))
            expected=[web.base+p for p in case['source_paths']]
            passed=process.returncode==0 and result['answer'] in case['answers'] and set(result['sources'])==set(expected)
            report={'scope':__doc__,'passed':passed,'exit_code':process.returncode,'result':result,
                    'stdout':process.stdout,'stderr':process.stderr}
    finally:
        service.shutdown();service.server_close();thread.join(timeout=2)
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))
    if not passed:sys.exit(1)
