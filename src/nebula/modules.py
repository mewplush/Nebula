"""Cache de módulos e busca de arquivos de módulo (.modneb / .neb)."""

from pathlib import Path

from .paths import BASE_DIR, MODULES_DIR, STDLIB_DIR
from .config import STATE


# Cache de módulos já executados e controle de importação circular.
MODULE_CACHE = {}
MODULES_LOADING = set()


def resolve_module_path(module_name, current_file=None):
	"""Procura o módulo: .modneb (modules/, stdlib/) e depois .neb (pasta do arquivo atual, pasta atual, pasta pai da instalação)."""
	candidates = [
		MODULES_DIR / f'{module_name}.modneb',
		STDLIB_DIR / f'{module_name}.modneb',
	]
	current = current_file if current_file is not None else STATE.filename
	if current and not str(current).startswith('<'):
		candidates.append(Path(current).resolve().parent / f'{module_name}.neb')
	candidates.append(Path.cwd() / f'{module_name}.neb')
	candidates.append(BASE_DIR.parent / f'{module_name}.neb')  # compatibilidade com o antigo '../'
	for candidate in candidates:
		if candidate.exists():
			return candidate
	return None
