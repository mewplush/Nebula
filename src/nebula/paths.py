"""Pastas da Nebula (instalação, modules/, stdlib/)."""

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent  # pasta que contém o pacote 'nebula' (a 'src')
MODULES_DIR = BASE_DIR / 'modules'
STDLIB_DIR = BASE_DIR / 'stdlib'


def _list_modneb(folder):
	try:
		return sorted(item for item in os.listdir(folder) if item.endswith('.modneb'))
	except OSError:
		return []


ALL_MODULES = _list_modneb(MODULES_DIR) + [m for m in _list_modneb(STDLIB_DIR) if m not in _list_modneb(MODULES_DIR)]
MODULES_NAME = [item.replace('.modneb', '') for item in ALL_MODULES]
