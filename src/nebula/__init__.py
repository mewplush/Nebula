"""Nebula (PyNeb): interpretador da linguagem Nebula.

Uso programático:
    import nebula
    valor, erro, contexto = nebula.run('arquivo.neb', 'falar("oi")')

Todos os nomes públicos dos submódulos são reexportados aqui (compatível com o antigo
arquivo único `pyneb.py`, que agora é só um atalho para este pacote).
"""
import importlib as _importlib
import types as _types

_SUBMODULES = ('paths', 'config', 'modules', 'string_with_arrows', 'errors', 'position', 'tokens', 'lexer',
               'nodes', 'parser', 'context', 'values', 'typesystem', 'builtin_functions', 'interpreter', 'runtime', 'linter')

for _name in _SUBMODULES:
    _mod = _importlib.import_module(f'.{_name}', __name__)
    for _key, _value in vars(_mod).items():
        if _key.startswith('_') or isinstance(_value, _types.ModuleType):
            continue
        globals().setdefault(_key, _value)

from . import config as _config  # noqa: E402


def __getattr__(name):
    # FILENAME e SAFE_MODE eram variáveis globais; agora vivem em config.STATE.
    if name == 'FILENAME':
        return _config.STATE.filename
    if name == 'SAFE_MODE':
        return _config.STATE.safe_mode
    raise AttributeError(f"module 'nebula' has no attribute {name!r}")
