"""Freeze manually primary-source-checked web questions before any engine scoring.

Author-created, small, and partially correlated by document; never an official score.
Refuses to replace an existing freeze. Primary pages were independently inspected first.
"""
import hashlib
import json
from pathlib import Path
import time


def main():
    target=Path('benchmarks/live-holdout.json')
    if target.exists():raise RuntimeError('Holdout already frozen; do not regenerate it')
    rows=[
      ('curl-connect','curl','What is the default value of CURLOPT_CONNECTTIMEOUT, expressed as a number of seconds?','https://curl.se/libcurl/c/CURLOPT_CONNECTTIMEOUT.html','300'),
      ('nginx-keepalive','nginx','What is the default timeout value for the nginx keepalive_timeout directive? Include the time unit.','https://nginx.org/en/docs/http/ngx_http_core_module.html','75s'),
      ('postgres-connections','postgres','What is the typical default number for PostgreSQL max_connections?','https://www.postgresql.org/docs/current/runtime-config-connection.html','100'),
      ('sshd-port','openssh','What is the default value of the Port setting in sshd_config?','https://man.openbsd.org/sshd_config','22'),
      ('pi-header','pi','How many pins are in the Raspberry Pi 5 standard header? Return the pin count.','https://www.raspberrypi.com/products/raspberry-pi-5/','40'),
      ('sqlite-columns','sqlite','What is the default setting for SQLITE_MAX_COLUMN?','https://www.sqlite.org/limits.html','2000'),
      ('json-ensure-ascii','python','What is the default value of ensure_ascii parameter in json.dumps?','https://docs.python.org/3/library/json.html','True'),
      ('wcag-normal-aa','wcag','In WCAG 2.2 success criterion 1.4.3, what minimum contrast ratio applies to normal text? Return the ratio including the colon.','https://www.w3.org/TR/WCAG22/','4.5:1'),
      ('wcag-normal-aaa','wcag','In WCAG 2.2 success criterion 1.4.6, what minimum contrast ratio applies to normal text? Return the ratio including the colon.','https://www.w3.org/TR/WCAG22/','7:1'),
      ('rfc-title','ietf','What is the title of RFC 9110?','','HTTP Semantics'),
      ('sqlite-missing-email','sqlite','What is the emergency support email address explicitly listed for SQLITE_MAX_COLUMN?','https://www.sqlite.org/limits.html',''),
      ('curl-false-premise','curl','How many NVIDIA GPU cores does CURLOPT_CONNECTTIMEOUT require, according to this document?','https://curl.se/libcurl/c/CURLOPT_CONNECTTIMEOUT.html',''),
      ('sqlite-discovery','discovery-sqlite','According to the SQLite Implementation Limits page, what is the default setting for SQLITE_MAX_COLUMN?','','2000'),
      ('sshd-discovery','discovery-openssh','According to the OpenBSD sshd_config manual, what is the default Port setting?','','22'),
    ]
    data=[]
    for id,family,query,url,answer in rows:
        source=url or ('https://datatracker.ietf.org/api/v1/doc/document/rfc9110/' if family=='ietf' else
            'https://www.sqlite.org/limits.html' if family=='discovery-sqlite' else 'https://man.openbsd.org/sshd_config')
        data.append({'id':id,'family':family,'query':query,'url':url,'answer':answer,'sources':[source] if answer else [],
            'truth_source':source,'truth_checked':'2026-10-20; manually inspected primary documentation before engine run'})
    target.write_text(json.dumps(data,indent=2),encoding='utf-8')
    files=[Path('app.py'),*Path('agent').glob('*.py')]
    freeze={'created_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'cases':len(data),
        'limits':'Same author, two WCAG questions and two repeated facts with discovery; 9 source domains. Not representative hidden data.',
        'dataset_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
        'production_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    Path('benchmarks/live-holdout-freeze.json').write_text(json.dumps(freeze,indent=2),encoding='utf-8')


if __name__=='__main__':main()
