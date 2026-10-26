"""Reproducible static checks supplement, rather than replace, manual flow review."""
import ast
import hashlib
import json
from pathlib import Path
import re


def main():
    root=Path(__file__).resolve().parents[1]
    production=[root/'app.py',*sorted((root/'agent').glob('*.py'))]
    all_files=production+sorted(path for directory in ('scripts','tests','eval') for path in (root/directory).glob('*.py'))
    forbidden={'benchmarks','fixtures','research','bitsandbytes','flash_attn','vllm'}
    findings=[]
    for path in all_files:
        source=path.read_text(encoding='utf-8-sig')
        tree=ast.parse(source,filename=str(path))
        compile(tree,str(path),'exec')
        if path not in production:continue
        for node in ast.walk(tree):
            imports=[item.name for item in node.names] if isinstance(node,ast.Import) else [node.module or ''] if isinstance(node,ast.ImportFrom) else []
            for name in imports:
                if name.split('.')[0] in forbidden:findings.append({'file':path.relative_to(root).as_posix(),'line':node.lineno,'kind':'forbidden_production_import','name':name})
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in {'eval','exec'}:
                findings.append({'file':path.relative_to(root).as_posix(),'line':node.lineno,'kind':'dynamic_code_execution'})
        for line_number,line in enumerate(source.splitlines(),1):
            if re.search(r'\b(?:TODO|FIXME|NotImplementedError)\b',line):findings.append({'file':path.relative_to(root).as_posix(),'line':line_number,'kind':'unfinished_marker'})
            if re.search(r'\b(?:hf_[A-Za-z0-9]{24,}|sk-[A-Za-z0-9]{28,})\b',line):findings.append({'file':path.relative_to(root).as_posix(),'line':line_number,'kind':'possible_secret'})
    report={'scope':'Python syntax/compile, production import boundaries, dynamic execution, unfinished markers and common token patterns. Manual architecture, behavior and artifact review are separately documented in AUDIT.md.',
        'python_files':len(all_files),'production_files':len(production),
        'production_sha256':{path.relative_to(root).as_posix():hashlib.sha256(path.read_bytes()).hexdigest() for path in production},'findings':findings}
    target=root/'benchmarks/source-audit-final.json'
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'python_files':len(all_files),'production_files':len(production),'findings':findings}))
    if findings:raise SystemExit(1)


if __name__=='__main__':main()
