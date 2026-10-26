"""CPU-only assessment-boundary checks over invented upstream rows, never holdout gold."""
import asyncio
import ast
from contextlib import redirect_stdout
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from eval import run as runner


class AssessmentInputs(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        upstream=self.root/'research/external-simpleqa'
        upstream.mkdir(parents=True)
        (upstream/'metadata.json').write_text(json.dumps({'sha':'invented-input',
            'cardData':{'license':'test-only'}}),encoding='utf-8')
        with (upstream/'simpleqa_verified.csv').open('w',newline='',encoding='utf-8') as stream:
            writer=csv.DictWriter(stream,fieldnames=['original_index','problem','answer',
                'urls','answer_type','topic','multi_step'])
            writer.writeheader()
            for i,answer in enumerate(['1,234','March 2, 2020','PRIVATE_GOLD_VALUE']):
                writer.writerow({'original_index':str(i),'problem':f'Invented question {i}?',
                    'answer':answer,'urls':f'https://example.org/gold-{i}, https://example.net/other-{i}',
                    'answer_type':'test','topic':'invented','multi_step':'False'})
        # The freeze records production hashes from its working directory.
        (self.root/'app.py').write_text('# invented production marker\n',encoding='utf-8')
        (self.root/'agent').mkdir()
        (self.root/'agent/probe.py').write_text('# invented module marker\n',encoding='utf-8')

    def freeze(self,name,*args,ok=True):
        path=self.root/(name+'.json')
        result=subprocess.run([sys.executable,str(ROOT/'scripts/freeze_external_assessment.py'),
            '--count','3','--seed','17','--out',str(path),*args],cwd=self.root,
            capture_output=True)
        if ok:
            self.assertEqual(result.returncode,0,result.stderr.decode('utf-8',errors='replace'))
            cases=json.loads(path.read_text(encoding='utf-8'))
            manifest=json.loads(path.with_name(path.stem+'-freeze.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['cases_sha256'],hashlib.sha256(path.read_bytes()).hexdigest())
            return cases,manifest
        self.assertNotEqual(result.returncode,0)
        return result

    def test_default_preserves_gold_starting_url(self):
        cases,manifest=self.freeze('assisted')
        self.assertTrue(all(case['url']==case['sources'][0] for case in cases))
        self.assertEqual(manifest['starting_url_mode'],'first-gold')
        self.assertTrue(manifest['adaptation'].startswith('Starting URL is the first gold URL.'))

    def test_question_only_preserves_rows_truth_and_aliases(self):
        assisted,_=self.freeze('assisted')
        questions,manifest=self.freeze('questions','--starting-url','none')
        self.assertEqual(questions,[dict(case,url='') for case in assisted])
        self.assertEqual(manifest['starting_url_mode'],'none')
        self.assertIn('Question-only engine input',manifest['adaptation'])
        by_answer={case['answer']:case for case in questions}
        self.assertEqual(by_answer['1,234']['answers'],['1,234','1234'])
        self.assertEqual(by_answer['March 2, 2020']['answers'],['March 2, 2020','2020-03-02'])

    def test_engine_receives_no_gold_fields(self):
        cases,_=self.freeze('questions','--starting-url','none')
        calls=[]

        class SpyEngine:
            def __init__(self,settings):pass
            async def run(self,*args,**kwargs):
                calls.append((args,kwargs))
                return SimpleNamespace(answer='',sources=[],diagnostics={},confidence=0,
                    reason='CPU boundary probe',internal=lambda:{'answer':'','sources':[]})

        with patch.object(runner,'Engine',SpyEngine),redirect_stdout(io.StringIO()):
            rows=asyncio.run(runner.run(cases,object()))
        self.assertEqual(calls,[((case['query'],''),{}) for case in cases])
        self.assertEqual(len(rows),len(cases))
        self.assertNotIn('PRIVATE_GOLD_VALUE',repr(calls))
        self.assertNotIn('https://example',repr(calls))
        self.assertTrue(all(not row['error'] and not row['answer_ok'] for row in rows))

    def test_exposed_rows_stay_excluded_in_question_only_mode(self):
        prior=[{'upstream_row':1}]
        (self.root/'prior.json').write_text(json.dumps(prior),encoding='utf-8')
        cases,manifest=self.freeze('questions','--starting-url','none',
            '--count','2','--exclude','prior.json')
        self.assertEqual({case['upstream_row'] for case in cases},{0,2})
        self.assertEqual(manifest['eligible_rows'],2)
        self.assertEqual(manifest['excluded_assessments'][0]['n'],1)

    def test_cannot_overwrite_frozen_assessment(self):
        self.freeze('original')
        files=[self.root/'original.json',self.root/'original-freeze.json']
        before=[path.read_bytes() for path in files]
        self.freeze('original','--starting-url','none',ok=False)
        self.assertEqual(before,[path.read_bytes() for path in files])

    def test_invalid_mode_does_not_create_assessment(self):
        self.freeze('bad','--starting-url','guess',ok=False)
        self.assertFalse((self.root/'bad.json').exists())
        self.assertFalse((self.root/'bad-freeze.json').exists())

    def test_production_has_no_static_assessment_import(self):
        # A limited dependency guard, not proof against every possible leakage path.
        forbidden={'eval','benchmarks','fixtures','tests','research'}
        for path in [ROOT/'app.py',*sorted((ROOT/'agent').glob('*.py'))]:
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
                names=([alias.name for alias in node.names] if isinstance(node,ast.Import) else
                    [node.module or ''] if isinstance(node,ast.ImportFrom) and not node.level else [])
                for name in names:
                    self.assertNotIn(name.split('.')[0],forbidden,(str(path),node.lineno,name))


if __name__=='__main__':
    unittest.main(verbosity=2)
