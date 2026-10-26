"""Capture primary-source truth BEFORE the live run. Keep snapshots, dates, and expected URLs."""
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent.network import Fetcher
from agent.types import Settings,Deadline


async def main():
    cases=[]
    Path("research/live").mkdir(exist_ok=True)
    async with Fetcher(Settings(request_timeout=8),Deadline(120)) as f:
        for package,field,label in [("httpx","license","license"),("flask","requires_python","Requires-Python constraint"),
                ("numpy","version","latest stable version"),("pydantic","version","latest stable version"),
                ("requests","author","author"),("beautifulsoup4","requires_python","Requires-Python constraint"),
                ("packaging","version","latest stable version"),("pytest","requires_python","Requires-Python constraint")]:
            endpoint=f"https://pypi.org/pypi/{package}/json"
            resp=await f.fetch(endpoint,max_bytes=8_000_000)
            if resp.error:
                print(package,resp.error,flush=True);continue
            data=json.loads(resp.text)
            Path(f"research/live/pypi-{package}.json").write_text(json.dumps(data,ensure_ascii=False),encoding="utf-8")
            value=data["info"].get(field)
            if not value:
                print(package,field,"no truth value",flush=True);continue
            cases.append({"id":f"pypi-{package}-{field}","family":"registry", "query":f"What is the {label} of the {package} package on PyPI?",
                          "answer":str(value),"source":endpoint,"truth_retrieved_at":datetime.now(timezone.utc).isoformat()})
        for repo,field in [("encode/httpx","language"),("pallets/flask","default_branch"),("psf/requests","license"),("pytest-dev/pytest","license")]:
            endpoint=f"https://api.github.com/repos/{repo}"
            resp=await f.fetch(endpoint)
            if resp.error:
                print(repo,resp.error,flush=True);continue
            data=json.loads(resp.text)
            Path(f"research/live/github-{repo.replace('/','-')}.json").write_text(json.dumps(data,ensure_ascii=False),encoding="utf-8")
            value=data.get(field)
            if field=="license":
                value=value.get("spdx_id") if value else ""
            if value:
                cases.append({"id":f"github-{repo.replace('/','-')}","family":"registry","query":f"What is the {field.replace('_',' ')} of the {repo} GitHub repository?",
                    "answer":str(value),"source":endpoint,"truth_retrieved_at":datetime.now(timezone.utc).isoformat()})
    # Manually specified primary-document facts, independently confirmed against captured pages.
    cases += [
        {"id":"pep-440","family":"docs","query":"What is the title of PEP 440?","url":"https://peps.python.org/pep-0440/","answer":"Version Identification and Dependency Specification","source":"https://peps.python.org/pep-0440/"},
        {"id":"pep-498","family":"docs","query":"What is the title of PEP 498?","url":"https://peps.python.org/pep-0498/","answer":"Literal String Interpolation","source":"https://peps.python.org/pep-0498/"},
        {"id":"pep-750","family":"docs","query":"What is the title of PEP 750?","url":"https://peps.python.org/pep-0750/","answer":"Template Strings","source":"https://peps.python.org/pep-0750/"},
        {"id":"arxiv-title","family":"paper","query":"What is the title of arXiv paper 1810.04805?","url":"https://arxiv.org/abs/1810.04805","answer":"BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding","source":"https://arxiv.org/abs/1810.04805"},
        {"id":"arxiv-first-author","family":"paper","query":"Who is the first author of arXiv paper 1810.04805?","url":"https://arxiv.org/abs/1810.04805","answer":"Jacob Devlin","source":"https://arxiv.org/abs/1810.04805"},
        {"id":"python-docs","family":"docs","query":"What is the default value of the allow_fragments parameter in urlparse?","url":"https://docs.python.org/3/library/urllib.parse.html","answer":"True","source":"https://docs.python.org/3/library/urllib.parse.html"},
    ]
    Path("benchmarks/live.json").write_text(json.dumps(cases,ensure_ascii=False,indent=2),encoding="utf-8")
    print("Captured",len(cases),"live questions",flush=True)


if __name__=="__main__":
    asyncio.run(main())
