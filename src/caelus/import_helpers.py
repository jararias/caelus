
import sys
import importlib.util


def lazy_import(name):
    """Carga un módulo de forma perezosa."""
    spec = importlib.util.find_spec(name)
    if spec is None:
        raise ImportError(f"missing module {name}")
    
    loader = importlib.util.LazyLoader(spec.loader)
    spec.loader = loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module
