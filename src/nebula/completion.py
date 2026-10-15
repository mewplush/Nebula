"""Completar código (textDocument/completion) para a Nebula.

Funções puras: recebem a análise (escopos), a linha digitada até o cursor e devolvem itens do LSP.
Contextos tratados, nesta ordem:
  comentário/texto -> nada | `importar ...` -> módulos e nomes do módulo | anotações de tipo (`: `, `->`, `extende`)
  -> tipos e classes | pontos de definição (`função `, `classe `, `para cada `) -> nada
  | `algo.` -> membros (módulo, `esse.`, `super.`, instância de classe, listas/strings/dicionários)
  | geral -> nomes do escopo, funções nativas, palavras-chave e trechos prontos (snippets).
"""
import re
from pathlib import Path

from .builtin_functions import BuiltInFunction
from .context import global_symbol_table
from .linter import analyze_text
from .modules import resolve_module_path
from .paths import MODULES_DIR, STDLIB_DIR
from .tokens import KEYWORDS
from .typesystem import PRIMITIVES, SPECIAL

# CompletionItemKind do LSP
METHOD, FUNCTION, FIELD, VARIABLE, CLASS, MODULE, KEYWORD, SNIPPET, CONSTANT, STRUCT = 2, 3, 5, 6, 7, 9, 14, 15, 21, 22
IDENT = r'[\wÀ-ÿ]'

TYPE_CONTEXTS = [
	re.compile(r'\bdeclarar\s+(?:constante\s+)?' + IDENT + r'+(?:\s*,\s*' + IDENT + r'+)*\s*:\s*([\w.À-ÿ\[\], ]*)$'),
	re.compile(r'->\s*([\w.À-ÿ\[\], ]*)$'),
	re.compile(r'\busando\s*\([^)]*?' + IDENT + r'\s*:\s*([\w.À-ÿ\[\], ]*)$'),
]
EXTENDE_RE = re.compile(r'\bextende\s+([\w.À-ÿ]*)$')
IMPORT_MODULE_RE = re.compile(r'^\s*importar\s+(?:.+\s+de\s+)?(' + IDENT + r'*)$')
IMPORT_NAMES_RE = re.compile(r'^\s*importar\s+([\wÀ-ÿ\s,]*)$')
NAMING_RES = [
	re.compile(r'(?:^|\s)(?:função|classe)\s+(?:privada\s+)?' + IDENT + r'*$'),
	re.compile(r'\bpara\s+cada\s+' + IDENT + r'*$'),
]
DECLARAR_RE = re.compile(r'(?:^|\s)declarar\s+(' + IDENT + r'*)$')
MEMBER_RE = re.compile(r'((?:' + IDENT + r'+\s*\.\s*)+)(' + IDENT + r'*)$')

SNIPPETS = [
	('se … fim', 'se', 'se ${1:condição} então\n\t$0\nfim'),
	('se … senão … fim', 'se', 'se ${1:condição} então\n\t$2\nsenão\n\t$0\nfim'),
	('enquanto … fim', 'enquanto', 'enquanto ${1:condição} faça\n\t$0\nfim'),
	('para cada … em … fim', 'para', 'para cada ${1:item} em ${2:lista} faça\n\t$0\nfim'),
	('para cada … de … até … fim', 'para', 'para cada ${1:i} de ${2:0} até ${3:10} faça\n\t$0\nfim'),
	('função … fim', 'função', 'função ${1:nome} usando (${2})\n\t$0\nfim'),
	('função … => …', 'função', 'função ${1:nome} usando (${2}) => ${0:valor}'),
	('classe … fim', 'classe', 'classe ${1:Nome}\n\tfunção principal usando (esse${2})\n\t\t$0\n\tfim\nfim'),
	('classe … extende … fim', 'classe', 'classe ${1:Nome} extende ${2:Pai}\n\tfunção principal usando (esse${3})\n\t\tsuper(${4})\n\t\t$0\n\tfim\nfim'),
	('tentar … caso … fim', 'tentar', 'tentar\n\t$1\ncaso ${2:erro} faça\n\t$0\nfim'),
	('importar … de …', 'importar', 'importar ${1:nome} de ${2:módulo}'),
]


def lexical_state(prefix):
	"""'code', 'string' ou 'comment' para o fim de `prefix` (entende `${...}` dentro de strings)."""
	stack = []
	i = 0
	while i < len(prefix):
		ch = prefix[i]
		top = stack[-1] if stack else 'code'
		if top == 'str':
			if ch == '\\':
				i += 1
			elif ch == '"':
				stack.pop()
			elif ch == '$' and prefix[i + 1:i + 2] == '{':
				stack.append('expr')
				i += 1
		else:
			if ch == '"':
				stack.append('str')
			elif ch == '#' and top == 'code':
				return 'comment'
			elif ch == '}' and top == 'expr':
				stack.pop()
		i += 1
	return 'string' if stack and stack[-1] == 'str' else 'code'


def item(label, kind, detail='', documentation=None, sort='5', insert=None, snippet=False, filter_text=None):
	result = {'label': label, 'kind': kind, 'sortText': f'{sort}{label}'}
	if detail:
		result['detail'] = detail
	if documentation:
		result['documentation'] = {'kind': 'markdown', 'value': documentation}
	if insert is not None:
		result['insertText'] = insert
		if snippet:
			result['insertTextFormat'] = 2
	if filter_text:
		result['filterText'] = filter_text
	return result


def signature(sym):
	"""`(a: número, b = …) -> tipo` (sem o `esse` dos métodos)."""
	params = sym.params or []
	if sym.is_method and params:
		params = params[1:]
	parts = [p.name + (f': {p.type}' if p.type is not None else '') + (' = …' if p.has_default else '') for p in params]
	return f"({', '.join(parts)})" + (f' -> {sym.return_type}' if sym.return_type is not None else '')


def symbol_item(sym, sort):
	from .linter import describe_symbol
	target = sym.origin or sym
	if target.kind == 'function':
		return item(sym.name, METHOD if target.is_method else FUNCTION, signature(target), describe_symbol(target), sort)
	if target.kind == 'class':
		return item(sym.name, CLASS, 'classe', describe_symbol(target), sort)
	if target.kind == 'module':
		return item(sym.name, MODULE, 'módulo', describe_symbol(target), sort)
	declared = target.type or target.inferred
	detail = str(declared) if declared is not None else {'parameter': 'parâmetro', 'loopvar': 'laço', 'catchvar': 'erro'}.get(target.kind, '')
	return item(sym.name, CONSTANT if target.constant else VARIABLE, detail, None, sort)


def lookup(scope, name):
	while scope is not None:
		if name in scope.symbols:
			return scope.symbols[name]
		scope = scope.parent
	return None


def method_scope(scope):
	while scope is not None:
		if scope.kind == 'function' and scope.is_method:
			return scope
		scope = scope.parent
	return None


def visible_classes(scope):
	found = {}
	while scope is not None:
		for name, sym in scope.symbols.items():
			if sym.kind == 'class' and name not in found:
				found[name] = sym
		scope = scope.parent
	return found


# --------------------------------------------------------------------------- módulos
def available_modules(filename):
	found = {}
	for folder, label in ((MODULES_DIR, 'módulo'), (STDLIB_DIR, 'biblioteca padrão')):
		try:
			for path in sorted(Path(folder).glob('*.modneb')):
				found.setdefault(path.stem, label)
		except OSError:
			pass
	if filename and not str(filename).startswith('<'):
		here = Path(filename).resolve()
		for path in sorted(here.parent.glob('*.neb')):
			if path.resolve() != here:
				found.setdefault(path.stem, 'arquivo local')
	return found


def module_exports_by_name(name, filename):
	path = resolve_module_path(name, filename)
	if path is None:
		return {}
	try:
		text = Path(path).read_text(encoding='utf-8-sig')
	except OSError:
		return {}
	return analyze_text(text, str(path)).exports()


def exports_items(exports, only_classes=False, sort='2'):
	items = []
	for name, sym in sorted(exports.items()):
		if only_classes and sym.kind != 'class':
			continue
		items.append(symbol_item(sym, sort))
	return items


# --------------------------------------------------------------------------- membros
def builtin_groups():
	groups = {}
	for attr in dir(BuiltInFunction):
		if attr.startswith('execute_'):
			group, _, name = attr[len('execute_'):].partition('_')
			if name and group in ('list', 'string', 'dict', 'any'):
				groups.setdefault(group, []).append(name)
	return groups


TYPE_TO_GROUP = {'lista': 'list', 'string': 'string', 'dicionário': 'dict'}


def builtin_member_items(group=None):
	groups = builtin_groups()
	wanted = ['any'] + ([group] if group else [g for g in groups if g != 'any'])
	label = {'list': 'lista', 'string': 'string', 'dict': 'dicionário', 'any': 'qualquer valor'}
	return [item(name, METHOD, label[g], None, '3' if g == 'any' else '2') for g in wanted for name in sorted(groups.get(g, []))]


def class_member_items(ci, include_attrs=True, skip_constructor=True):
	items, seen = [], set()
	for owner in ci.chain():
		origin = '' if owner is ci else f'herdado de {owner.name}'
		for name, sym in owner.methods.items():
			if name in seen or (skip_constructor and name == 'principal'):
				continue
			seen.add(name)
			items.append(item(name, METHOD, (signature(sym) + (f'  ({origin})' if origin else '')), None, '1' if owner is ci else '2'))
		if include_attrs:
			for name in sorted(owner.attrs):
				if name not in seen:
					seen.add(name)
					items.append(item(name, FIELD, origin or 'atributo', None, '1' if owner is ci else '2'))
	return items


def class_of(type_node, scope):
	if type_node is None:
		return None
	if getattr(type_node, 'classinfo', None) is not None:
		return type_node.classinfo
	if type_node.options:
		for option in type_node.options:
			found = class_of(option, scope)
			if found is not None:
				return found
		return None
	parts = type_node.name.split('.')
	sym = lookup(scope, parts[0])
	for part in parts[1:]:
		if sym is None or sym.kind != 'module' or sym.module is None:
			return None
		sym = sym.module.exports.get(part)
	return sym.classinfo if sym is not None and sym.kind == 'class' else None


def member_items(chain, scope):
	if not chain or chain[0].isdigit():
		return []
	first = chain[0]
	if first == 'super' and len(chain) == 1:
		ms = method_scope(scope)
		parent = ms.classinfo.parent if ms is not None and ms.classinfo is not None else None
		return class_member_items(parent, include_attrs=False) if parent is not None else []
	sym = lookup(scope, first)
	if sym is None:
		return [] if first in global_symbol_table.symbols else builtin_member_items()
	if sym.kind == 'module':
		if sym.module is None or sym.module.partial:
			return []
		if len(chain) == 1:
			return exports_items(sym.module.exports)
		member = sym.module.exports.get(chain[1])
		if member is not None and member.kind == 'class' and len(chain) == 2:
			return class_member_items(member.classinfo, include_attrs=False)
		return []
	if len(chain) > 1:
		return []
	if sym.kind == 'class' and sym.classinfo is not None:
		return class_member_items(sym.classinfo, include_attrs=False)
	t = sym.type or sym.inferred
	if t is None:
		return builtin_member_items()
	ci = class_of(t, scope)
	if ci is not None:
		return class_member_items(ci)
	if t.name in TYPE_TO_GROUP:
		return builtin_member_items(TYPE_TO_GROUP[t.name])
	return builtin_member_items()


# --------------------------------------------------------------------------- tipos
def type_items(word, scope):
	if '.' in word:
		module_name = word.rsplit('.', 1)[0]
		sym = lookup(scope, module_name)
		if sym is not None and sym.kind == 'module' and sym.module is not None:
			return exports_items(sym.module.exports, only_classes=True, sort='1')
		return []
	items = [item(name, STRUCT, 'tipo', None, '3') for name in sorted(set(PRIMITIVES) | set(SPECIAL))]
	for name, sym in sorted(visible_classes(scope).items()):
		items.append(item(name, CLASS, 'classe', None, '1'))
	s = scope
	while s is not None:
		for name, sym in s.symbols.items():
			if sym.kind == 'module' and sym.module is not None and not sym.module.partial:
				for cname, csym in sym.module.exports.items():
					if csym.kind == 'class':
						items.append(item(f'{name}.{cname}', CLASS, f'classe do módulo {name}', None, '2', filter_text=f'{name}.{cname}'))
		s = s.parent
	return items


# --------------------------------------------------------------------------- principal
def complete(analysis, line_text, col, scope_pos, filename=None):
	"""Itens de completar. `scope_pos` é a posição (linha, coluna) a consultar na análise (pode diferir do cursor se a análise é antiga)."""
	prefix = line_text[:col]
	state = lexical_state(prefix)
	if state != 'code':
		return []
	scope = analysis.scope_at(*scope_pos) if analysis is not None else None

	# importar ...
	match = IMPORT_NAMES_RE.match(prefix)
	if match:
		module_after = re.search(r'^\s*de\s+(' + IDENT + r'+)', line_text[col:]) or re.search(r'\sde\s+(' + IDENT + r'+)', line_text[col:])
		if module_after:  # estamos escolhendo nomes de `importar … de modulo`
			return exports_items(module_exports_by_name(module_after.group(1), filename), sort='1')
	match = IMPORT_MODULE_RE.match(prefix)
	if match and re.match(r'^\s*importar\b', prefix):
		return [item(name, MODULE, label, None, '1') for name, label in sorted(available_modules(filename).items())]

	# anotações de tipo
	for regex in TYPE_CONTEXTS:
		match = regex.search(prefix)
		if match:
			word = re.search(r'([\w.À-ÿ]*)$', match.group(1)).group(1)
			return type_items(word, scope)
	match = EXTENDE_RE.search(prefix)
	if match:
		word = match.group(1)
		if '.' in word:
			return type_items(word, scope)
		return [item(name, CLASS, 'classe', None, '1') for name in sorted(visible_classes(scope))]

	# onde se escolhe um nome novo: não sugerir nada
	if any(r.search(prefix) for r in NAMING_RES):
		return []
	match = DECLARAR_RE.search(prefix)
	if match:
		return [item('constante', KEYWORD, 'declarar constante', None, '1')] if 'constante'.startswith(match.group(1)) else []

	# algo.
	match = MEMBER_RE.search(prefix)
	if match and match.group(1).strip():
		chain = [p.strip() for p in match.group(1).split('.') if p.strip()]
		return member_items(chain, scope)

	# geral
	items, seen, depth = [], set(), 0
	s = scope
	while s is not None:
		for name, sym in s.symbols.items():
			if name not in seen:
				seen.add(name)
				items.append(symbol_item(sym, str(depth)))
		s = s.parent
		depth += 1
	for name, value in global_symbol_table.symbols.items():
		if name not in seen:
			seen.add(name)
			is_function = getattr(value, 'executable', False)
			items.append(item(name, FUNCTION if is_function else CONSTANT, 'nativo', None, '5'))
	for word in KEYWORDS:
		if word not in seen:
			items.append(item(word, KEYWORD, '', None, '6'))
	for label, trigger, body in SNIPPETS:
		items.append(item(label, SNIPPET, 'trecho de código', None, '7', insert=body, snippet=True, filter_text=trigger))
	return items
