"""Offline real-TLS smoke; generates a private temporary test CA, never changes host trust."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import tempfile
import threading

from registry_transport import RangeConnections


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--openssl');args=parser.parse_args()
    executable=args.openssl or shutil.which('openssl')
    if not executable:raise SystemExit('Pass --openssl PATH for this offline TLS test')
    root=Path(__file__).resolve().parents[1]
    state=root/'.state';state.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='tls-smoke-',dir=state) as directory:
        folder=Path(directory).resolve()
        assert folder.is_relative_to(state.resolve())
        key=folder/'key.pem';cert=folder/'cert.pem'
        subprocess.run([executable,'req','-x509','-newkey','rsa:2048','-sha256','-nodes','-days','1',
            '-keyout',str(key),'-out',str(cert),'-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost'],check=True,capture_output=True)
        body=bytes(range(256))*4096
        class Server(ThreadingHTTPServer):
            connections=0
            def get_request(self):
                socket,address=super().get_request();self.connections+=1;return socket,address
        class Handler(BaseHTTPRequestHandler):
            protocol_version='HTTP/1.1'
            def log_message(self,*args):return
            def do_GET(self):
                match=re.fullmatch(r'bytes=(\d+)-(\d+)',self.headers.get('Range',''))
                start,end=map(int,match.groups())
                value=body[start:end+1]
                self.send_response(206);self.send_header('Content-Length',str(len(value)))
                self.send_header('Content-Range',f'bytes {start}-{end}/{len(body)}');self.end_headers();self.wfile.write(value)
        server=Server(('127.0.0.1',0),Handler)
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cert,key)
        server.socket=context.wrap_socket(server.socket,server_side=True)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        client=RangeConnections(ssl.create_default_context(cafile=str(cert)))
        rejected=False
        try:
            def one(index):
                start=index*16384;end=start+16383
                with client.open(f'https://localhost:{server.server_port}/blob',{'Range':f'bytes={start}-{end}'}) as response:
                    value=response.read(16385)
                assert value==body[start:end+1]
                return hashlib.sha256(value).hexdigest()
            with ThreadPoolExecutor(8) as pool:results=list(pool.map(one,range(64)))
            reused=server.connections
            assert reused<=8, 'Connections were not reused'
            try:client.open(f'https://127.0.0.1:{server.server_port}/blob',{'Range':'bytes=0-1'})
            except ssl.SSLCertVerificationError:rejected=True
            assert rejected,'Hostname validation was bypassed'
        finally:
            client.close();server.shutdown();server.server_close();thread.join(timeout=3)
        report={'real_tls':True,'ranges_verified':len(results),'connections_for_64_requests':reused,
            'wrong_hostname_rejected':rejected,'host_trust_store_changed':False,'test_key_shipped':False}
        target=root/'benchmarks/registry-transport-tls-smoke.json';target.write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report))


if __name__=='__main__':main()
