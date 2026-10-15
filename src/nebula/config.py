"""Constantes, estado compartilhado e configuração padrão."""

import string
import sys
from types import SimpleNamespace

from .paths import MODULES_NAME


DIGITS = '0123456789'
LETTERS = string.ascii_letters
LETTERS += 'áéíóúãâêôãõçÁÉÍÓÚÃÂÊÔÃÕÇ_'
LETTERS_DIGITS = LETTERS + DIGITS
# versões em conjunto (set): teste de pertencimento O(1) no lexer
DIGITS_SET = frozenset(DIGITS)
DIGITS_DOT_SET = frozenset(DIGITS + '.')
LETTERS_SET = frozenset(LETTERS)
LETTERS_DIGITS_SET = frozenset(LETTERS_DIGITS + '_')

sys.setrecursionlimit(max(sys.getrecursionlimit(), 10000))

# Estado mutável compartilhado entre os módulos (antes eram globais de um arquivo só).
STATE = SimpleNamespace(filename='', safe_mode=False)

# Modo seguro: bloqueia funções que tocam o sistema (executar, python, arquivos).
DANGEROUS_BUILTINS = {'clicommand', 'python', 'escrever_arquivo', 'ler_arquivo'}


def set_safe_mode(enabled=True):
	STATE.safe_mode = bool(enabled)


DEFAULT_CONFIG = {
	'version': "1.11.0",
	'author': 'mewplush',
	'publisher': 'mewplush',
	'interpreter': 'pyneb',
	'python': {
		'author-version':'3.12.10',
		'user-version': sys.version,
	},
	'description': 'PyNeb é o interpretador principal da linguagem Nebula. Escrito em Python, ele é capaz de executar scripts Nebula e também pode ser usado como um shell interativo.',
	'special-keys': {
		'__shell__': 'Nebula Shell',
		'.config': 'Configuração do PyNeb',
		'__path__': 'Caminho do arquivo',
		'.version': 'Versão do PyNeb',
		'setmain <filename>': 'Define o arquivo principal',
		'.': 'Executar arquivo principal'
	}
}
DEFAULT_CONFIG['modules'] = [str(module) for module in MODULES_NAME]
DEFAULT_CONFIG['special-keys'].update({key: value for key, value in DEFAULT_CONFIG.items()})
