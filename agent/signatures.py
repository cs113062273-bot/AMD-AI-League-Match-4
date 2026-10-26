"""Read parameter defaults as syntax, never execute documentation code."""
import ast
import io
import re
import tokenize
from functools import lru_cache
from .normalize import clean


@lru_cache(maxsize=256)
def parameter_default(signature,name):
    signature=clean(signature)
    if len(signature)>16000 or not re.fullmatch(r'\w+',name):return None
    opening=signature.find('(')
    if opening<0:return None
    closing=None;depth=0
    try:
        for token in tokenize.generate_tokens(io.StringIO(signature[opening:]).readline):
            if token.type==tokenize.OP:
                if token.string=='(':depth+=1
                elif token.string==')':
                    depth-=1
                    if depth==0:closing=opening+token.end[1];break
    except (tokenize.TokenError,IndentationError):return None
    if closing is None:return None
    code='def _probe'+signature[opening:closing]+':\n pass'
    try:
        args=ast.parse(code).body[0].args
        positional=args.posonlyargs+args.args
        pairs=list(zip(positional[len(positional)-len(args.defaults):],args.defaults))
        pairs+=list(zip(args.kwonlyargs,args.kw_defaults))
        for argument,value in pairs:
            if argument.arg==name and value is not None:
                return ast.get_source_segment(code,value)
        return None
    except (SyntaxError,ValueError,RecursionError):
        # Non-Python documentation signatures: accept only a complete simple literal.
        literal=r'''(?:'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*"|[A-Za-z_]\w*|[-+]?\d+(?:\.\d+)?)'''
        match=re.search(r'\b'+re.escape(name)+r'\s*=\s*('+literal+r')\s*(?=[,\)\]])',signature[opening:closing])
        return match[1] if match else None
