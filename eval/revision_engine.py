"""Load an isolated historical agent package for paired diagnostics, without copying weights/repo."""
import hashlib
import importlib
import importlib.abc
import importlib.util
import subprocess
import sys
import types


def load_engine(revision):
    revision=subprocess.check_output(['git','rev-parse','--verify',revision+'^{commit}'],text=True).strip()
    prefix='_aperture_revision_'+revision[:12]
    package=types.ModuleType(prefix)
    package.__path__=[]
    sys.modules[prefix]=package
    hashes={}

    class Loader(importlib.abc.MetaPathFinder,importlib.abc.Loader):
        def find_spec(self,fullname,path=None,target=None):
            if not fullname.startswith(prefix+'.'):return None
            return importlib.util.spec_from_loader(fullname,self)

        def create_module(self,spec):return None

        def exec_module(self,module):
            name=module.__name__.split('.')[-1]
            filename='agent/'+name+'.py'
            source=subprocess.check_output(['git','show',revision+':'+filename])
            hashes[filename]=hashlib.sha256(source).hexdigest()
            module.__file__='git:'+revision+':'+filename
            exec(compile(source,module.__file__,'exec'),module.__dict__)

    sys.meta_path.insert(0,Loader())
    engine=importlib.import_module(prefix+'.engine').Engine
    return engine,revision,hashes
