"""Linter estático da Nebula (não executa o código).

Analisa a árvore sintática e aponta: nomes não declarados, imports/variáveis sem uso, código inalcançável,
tipos incompatíveis (usando as anotações), chamadas com argumentos errados, uso inválido de `super`,
atributos/métodos inexistentes e mais. Segue os `importar` para outros arquivos (.neb/.modneb).

Uso:
    from nebula.linter import lint_text, lint_file
    for d in lint_file('programa.neb'): print(d.line, d.code, d.message)

Supressão: `# neb-ignore` (linha inteira) ou `# neb-ignore: NEB202, NEB204` no fim da linha;
`# neb-ignore-file: NEB202` em qualquer linha ignora o código no arquivo todo.
"""
import difflib
import os
import re
from pathlib import Path

from .context import global_symbol_table
from .modules import resolve_module_path
from .nodes import (
	ArrayAccessNode, ArrayAssignNode, AttrAccessNode, AttrAssignNode, BinOpNode, BoolNode, BreakNode, CallNode,
	ClassNode, ContinueNode, DictCompNode, DictNode, FStringNode, ForEachNode, ForNode, FuncDefNode, IfNode,
	ImportNamespaceNode, ImportNode, ListNode, NumberNode, RaiseNode, ReturnNode, SetNode, StringNode, SuperNode,
	TryCatchNode, TupleNode, TypeNode, UnaryOpNode, VarAccessNode, VarAssignNode, WhileNode,
)
from .lexer import Lexer
from .runtime import parse_text
from .tokens import (
	TT_ARROW, TT_DIV, TT_EE, TT_EOF, TT_GT, TT_GTE, TT_KEYWORD, TT_LT, TT_LTE, TT_MINUS, TT_MUL, TT_NE, TT_NEWLINE, TT_PERCENT,
	TT_PLUS, TT_POW, Token,
)
from .typesystem import GENERIC_ARITY, PRIMITIVES, SPECIAL

# --------------------------------------------------------------------------------------
# Regras
# --------------------------------------------------------------------------------------
RULES = {
	'NEB001': ('erro', 'erro de sintaxe'),
	'NEB101': ('erro', 'nome não declarado'),
	'NEB102': ('erro', 'atribuição a uma constante'),
	'NEB104': ('erro', 'nome inexistente (ou privado) no módulo importado'),
	'NEB105': ('erro', 'módulo não encontrado'),
	'NEB106': ('erro', 'o módulo não tem esse membro'),
	'NEB107': ('aviso', 'módulo importado com erros de sintaxe (análise limitada)'),
	'NEB201': ('aviso', 'código inalcançável'),
	'NEB202': ('aviso', 'variável ou função local nunca usada'),
	'NEB203': ('dica', 'parâmetro nunca usado'),
	'NEB204': ('aviso', 'importação nunca usada'),
	'NEB205': ('aviso', 'função/classe definida duas vezes no mesmo escopo'),
	'NEB206': ('dica', 'nome sombreia uma função nativa'),
	'NEB207': ('dica', 'variável criada por atribuição, sem "declarar"'),
	'NEB209': ('aviso', 'atribuição dentro de função cria variável local (a global não muda)'),
	'NEB210': ('dica', 'em métodos, "declarar x" cria o atributo esse.x (não uma variável local)'),
	'NEB301': ('erro', 'tipo desconhecido ou inválido na anotação'),
	'NEB302': ('erro', 'valor incompatível com o tipo da variável'),
	'NEB303': ('erro', 'quantidade de argumentos incorreta'),
	'NEB304': ('erro', 'argumento incompatível com o tipo do parâmetro'),
	'NEB305': ('erro', 'retorno incompatível com o tipo declarado'),
	'NEB306': ('aviso', 'função com tipo de retorno pode terminar sem retornar'),
	'NEB401': ('erro', 'uso inválido de super'),
	'NEB402': ('erro', 'método sem "esse" como primeiro parâmetro'),
	'NEB403': ('erro', 'superclasse inválida'),
	'NEB404': ('aviso', 'atributo ou método inexistente na classe'),
	'NEB501': ('erro', '"retornar" fora de uma função'),
	'NEB502': ('erro', '"parar"/"continuar" fora de um laço'),
}

IGNORE_RE = re.compile(r'#\s*neb-ignore(-file)?\s*(?::\s*([A-Za-z0-9_,\s]+))?')
ARITH = (TT_PLUS, TT_MINUS, TT_MUL, TT_DIV, TT_PERCENT, TT_POW)
COMPARE = (TT_EE, TT_NE, TT_LT, TT_GT, TT_LTE, TT_GTE)
BUILTIN_RETURNS = {
	'str': 'string', 'len': 'número', 'int': 'número', 'raiz': 'número', 'quadrado': 'número', 'cubo': 'número',
	'tipo': 'string', 'pegar': 'string', 'perguntar': 'string', 'input_int': 'número', 'aleatório': 'número',
}
TERMINATORS = (ReturnNode, BreakNode, ContinueNode, RaiseNode)


class Diagnostic:
	def __init__(self, code, severity, message, line, col, end_line=None, end_col=None, file='', fixes=None, meta=None):
		self.code, self.severity, self.message = code, severity, message
		self.line, self.col = line, col
		self.end_line, self.end_col = end_line or line, end_col or col + 1
		self.file = file
		self.fixes = fixes or []   # correções rápidas: dict(title, preferred, edits=[((l0, c0, l1, c1), texto)]) (0-based, code points)
		self.meta = meta or {}

	def to_dict(self):
		return {'file': self.file, 'line': self.line, 'column': self.col, 'end_line': self.end_line,
				'end_column': self.end_col, 'code': self.code, 'severity': self.severity, 'message': self.message,
				'fixes': [{'title': f['title'], 'preferred': f.get('preferred', False),
						'edits': [{'start_line': r[0] + 1, 'start_column': r[1] + 1, 'end_line': r[2] + 1,
								'end_column': r[3] + 1, 'new_text': text} for r, text in f['edits']]}
						for f in self.fixes]}

	def __repr__(self):
		return f'{self.file}:{self.line}:{self.col}: {self.severity} {self.code}: {self.message}'


# --------------------------------------------------------------------------------------
# Modelo de símbolos
# --------------------------------------------------------------------------------------
class Param:
	def __init__(self, name, has_default, type_):
		self.name, self.has_default, self.type = name, has_default, type_


class Symbol:
	def __init__(self, name, kind, tok=None, constant=False, private=False, type_=None):
		self.name, self.kind, self.tok = name, kind, tok  # kind: variable parameter function class module import loopvar catchvar unknown
		self.constant, self.private, self.type = constant, private, type_
		self.used = False
		self.inferred = None      # TypeNode quando o tipo é conhecido
		self.params = None        # list[Param] (funções)
		self.return_type = None
		self.is_method = False
		self.classinfo = None
		self.module = None
		self.imported = False
		self.hoisted = False
		self.import_stmt = None  # {'line': n, 'kind': 'names'|'module'} para nomes importados
		self.file = None      # arquivo onde foi definido (preenchido pelo Linter)
		self.origin = None    # Symbol original quando é um nome importado de outro módulo
		self.module_path = None
		self.line = tok.pos_start.ln + 1 if tok is not None and getattr(tok, 'pos_start', None) else 0


class ClassInfo:
	def __init__(self, name, parent_tok=None):
		self.name = name
		self.parent_tok = parent_tok
		self.parent = None
		self.parent_known = parent_tok is None  # False quando a superclasse não pôde ser resolvida
		self.methods = {}
		self.attrs = set()

	def chain(self):
		ci = self
		while ci is not None:
			yield ci
			ci = ci.parent

	def find_method(self, name):
		for ci in self.chain():
			if name in ci.methods:
				return ci.methods[name]
		return None

	def has_attr(self, name):
		return any(name in ci.attrs for ci in self.chain())

	def fully_known(self):
		return all(ci.parent_known for ci in self.chain())

	def inherits(self, other):
		return any(ci is other for ci in self.chain())


class ModuleInfo:
	def __init__(self, path, exports=None, partial=False):
		self.path = path
		self.exports = exports or {}
		self.partial = partial  # True: não deu para analisar; aceita qualquer membro


class Scope:
	def __init__(self, kind, parent=None, func=None, classinfo=None, is_method=False):
		self.kind = kind  # module | function | class
		self.parent = parent
		self.symbols = {}
		self.deferred = []
		self.func = func              # Symbol da função em análise
		self.classinfo = classinfo    # classe dona (em class e em métodos)
		self.is_method = is_method
		self.loop_depth = 0


class Analysis:
	"""Resultado completo de uma análise: diagnósticos + índice de definições/referências + estrutura (outline)."""
	def __init__(self, filename, text):
		self.filename = filename
		self.text = text
		self.diagnostics = []
		self.syntax_error = False
		self.outline = []   # entradas: dict(name, kind, detail, range, sel, children)
		self.defs = []      # (range, Symbol)   range = (ln0, col0, ln1, col1), 0-based, em code points
		self.refs = []      # (range, Symbol)
		self.scopes = []    # (range, Scope): para saber quais nomes valem em cada posição (completar)
		self.lines = text.split('\n')

	def scope_at(self, line, col):
		"""Escopo mais interno que contém a posição (0-based; o fim do intervalo é exclusivo)."""
		best = None
		for (l0, c0, l1, c1), scope in self.scopes:
			if (l0, c0) <= (line, col) < (l1, c1):
				size = (l1 - l0, c1 - c0)
				if best is None or size < best[1]:
					best = (scope, size)
		return best[0] if best else None

	def exports(self):
		"""Símbolos públicos do módulo (funções, classes, variáveis não privadas e não importadas)."""
		if not self.scopes:
			return {}
		scope = self.scopes[0][1]
		return {n: sym for n, sym in scope.symbols.items()
				if not sym.private and sym.kind in ('function', 'class', 'variable') and not sym.imported}

	def organize_import_edits(self, linter_cls=None):
		"""Edições que removem TODAS as importações sem uso (um conjunto por linha de `importar`)."""
		by_line = {}
		for d in self.diagnostics:
			if d.code == 'NEB204' and d.meta.get('import_line') is not None:
				by_line.setdefault(d.meta['import_line'], []).append(d.meta)
		edits = []
		for line_no, metas in sorted(by_line.items()):
			if any(m['kind'] == 'module' for m in metas):
				found = import_line_edits(self.lines, line_no, None)
			else:
				found = import_line_edits(self.lines, line_no, {m['name'] for m in metas})
			if found:
				edits.extend(found)
		return edits

	def symbol_at(self, line, col):
		"""Symbol cuja definição ou uso cobre a posição (0-based). Devolve (Symbol, range) ou None."""
		best = None
		for rng, sym in self.refs + self.defs:
			(l0, c0, l1, c1) = rng
			if (l0, c0) <= (line, col) < (l1, c1) or ((l0, c0) <= (line, col) <= (l1, c1) and (line, col) == (l1, c1) and l0 == l1):
				size = (l1 - l0, c1 - c0)
				if best is None or size < best[2]:
					best = (sym, rng, size)
		return (best[0], best[1]) if best else None


def describe_symbol(sym):
	"""Texto (markdown) mostrado no hover."""
	def fmt_params(params):
		out = []
		for p in params or []:
			text = p.name + (f': {p.type}' if p.type is not None else '')
			out.append(text + (' = …' if p.has_default else ''))
		return ', '.join(out)

	if sym.origin is not None:
		sym = sym.origin
	if sym.kind == 'function':
		prefix = 'método' if sym.is_method else 'função'
		ret = f' -> {sym.return_type}' if sym.return_type is not None else ''
		return f'```nebula\n{prefix} {sym.name}({fmt_params(sym.params)}){ret}\n```'
	if sym.kind == 'class':
		ci = sym.classinfo
		head = f'classe {sym.name}' + (f' extende {ci.parent_tok.value}' if ci is not None and ci.parent_tok is not None else '')
		body = ''
		if ci is not None and ci.methods:
			body = '\n\nMétodos: ' + ', '.join(f'`{n}`' for n in ci.methods)
		if ci is not None and ci.attrs:
			body += '\n\nAtributos: ' + ', '.join(f'`{n}`' for n in sorted(ci.attrs))
		return f'```nebula\n{head}\n```' + body
	if sym.kind == 'module':
		names = sorted(sym.module.exports) if sym.module is not None else []
		return f'```nebula\nmódulo {sym.name}\n```' + ('\n\nExporta: ' + ', '.join(f'`{n}`' for n in names) if names else '')
	declared = sym.type or sym.inferred
	kind = {'parameter': 'parâmetro', 'loopvar': 'variável de laço', 'catchvar': 'variável de erro'}.get(sym.kind)
	if kind is None:
		kind = 'declarar constante' if sym.constant else 'declarar'
	return f'```nebula\n{kind} {sym.name}' + (f': {declared}' if declared is not None else '') + '\n```'


class Shared:
	"""Estado compartilhado entre o arquivo principal e os módulos que ele importa."""
	def __init__(self):
		self.modules = {}
		self.loading = set()


# --------------------------------------------------------------------------------------
# Utilitários
# --------------------------------------------------------------------------------------
IMPORT_LINE_RE = re.compile(r'^(\s*)importar\s+(.+?)\s+de\s+(\S+?)\s*(#.*)?$')
IMPORT_MODULE_RE = re.compile(r'^\s*importar\s+\S+\s*(#.*)?$')


def delete_lines_edit(lines, first, last):
	if last + 1 < len(lines):
		return ((first, 0, last + 1, 0), '')
	return ((first, 0, last, len(lines[last].rstrip('\r'))), '')


def import_line_edits(lines, line_no, remove_names):
	"""Edições para tirar nomes de `importar a, b de modulo` (remove_names=None: remove a linha toda)."""
	if line_no >= len(lines):
		return None
	line = lines[line_no].rstrip('\r')
	if remove_names is None:
		return [delete_lines_edit(lines, line_no, line_no)] if IMPORT_MODULE_RE.match(line) else None
	match = IMPORT_LINE_RE.match(line)
	if not match:
		return None
	indent, names, module, comment = match.groups()
	kept = [n.strip() for n in names.split(',') if n.strip() and n.strip() not in remove_names]
	if not kept:
		return [delete_lines_edit(lines, line_no, line_no)]
	text = f"{indent}importar {', '.join(kept)} de {module}" + (f'  {comment}' if comment else '')
	return [((line_no, 0, line_no, len(line)), text)]


def _is_node(value):
	return type(value).__module__.endswith('.nodes') and not isinstance(value, TypeNode)


def iter_children(node):
	"""Filhos (nós) de um nó, ignorando tokens, posições e anotações de tipo."""
	for key, value in vars(node).items():
		if key in ('pos_start', 'pos_end'):
			continue
		stack = [value]
		while stack:
			item = stack.pop(0)
			if isinstance(item, (list, tuple)):
				stack = list(item) + stack
			elif _is_node(item):
				yield item


def terminates(node):
	"""True se executar este nó sempre encerra o bloco (retornar/parar/continuar/levantar...)."""
	if isinstance(node, TERMINATORS):
		return True
	if isinstance(node, ListNode):
		return any(terminates(e) for e in node.element_nodes)
	if isinstance(node, IfNode):
		if node.else_case is None:
			return False
		bodies = [case[1] for case in node.cases] + [node.else_case[0]]
		return all(terminates(b) for b in bodies)
	return False


def type_name(t):
	return str(t)


def T(name, args=None, classinfo=None):
	t = TypeNode(name=name, args=args or [])
	t.classinfo = classinfo
	return t


class Linter:
	def __init__(self, filename, text, ignore=(), hints=False, shared=None, is_module=False):
		self.filename = str(filename)
		self.text = text
		self.ignore = set(ignore)
		self.hints = hints
		self.shared = shared or Shared()
		self.is_module = is_module
		self.diagnostics = []
		self.builtins = set(global_symbol_table.symbols)
		self.module_scope = None
		self.syntax_error = False
		self.defs = []
		self.refs = []
		self.scope_records = []
		self.outline = []
		self.current_outline = self.outline
		self.lines = text.split('\n')

	# ----------------------------------------------------------------- diagnósticos
	# ----------------------------------------------------------------- correções rápidas
	def fix(self, title, edits, preferred=False):
		return {'title': title, 'preferred': preferred, 'edits': edits}

	def replace_fix(self, tok, new, title=None, preferred=False):
		rng = self.range_of(tok)
		return self.fix(title or f"Trocar por '{new}'", [(rng, new)], preferred) if rng else None

	def suggestion_fixes(self, tok, candidates, n=3, cutoff=0.6):
		close = difflib.get_close_matches(tok.value, sorted(set(candidates) - {tok.value}), n=n, cutoff=cutoff)
		fixes = [self.replace_fix(tok, c, preferred=(i == 0)) for i, c in enumerate(close)]
		return [f for f in fixes if f]

	def insert_before_fix(self, tok, text, title, preferred=False):
		start = getattr(tok, 'pos_start', None)
		if start is None:
			return None
		return self.fix(title, [((start.ln, start.col, start.ln, start.col), text)], preferred)

	def rename_unused_fix(self, tok):
		return self.replace_fix(tok, '_' + tok.value, f"Renomear para '_{tok.value}' (marca como não usado de propósito)")

	def visible_classes(self, scope):
		names = set()
		while scope is not None:
			names |= {n for n, sym in scope.symbols.items() if sym.kind == 'class'}
			scope = scope.parent
		return names

	def report(self, code, node, message, severity=None, fixes=None, meta=None):
		sev = severity or RULES[code][0]
		if sev == 'dica' and not self.hints:
			return
		if code in self.ignore:
			return
		start = getattr(node, 'pos_start', None)
		end = getattr(node, 'pos_end', None)
		line = start.ln + 1 if start else 1
		col = start.col + 1 if start else 1
		end_line = end.ln + 1 if end else line
		end_col = end.col + 1 if end else col + 1
		self.diagnostics.append(Diagnostic(code, sev, message, line, col, end_line, end_col, self.filename,
											fixes=[f for f in (fixes or []) if f], meta=meta))

	@staticmethod
	def range_of(node):
		start, end = getattr(node, 'pos_start', None), getattr(node, 'pos_end', None)
		if start is None:
			return None
		end = end or start
		return (start.ln, start.col, end.ln, end.col)

	def add_def(self, sym, tok=None):
		tok = tok or sym.tok
		if sym.file is None:
			sym.file = self.filename
		rng = self.range_of(tok) if tok is not None else None
		if rng is not None:
			self.defs.append((rng, sym))

	def add_ref(self, sym, node):
		rng = self.range_of(node)
		if sym is not None and rng is not None:
			self.refs.append((rng, sym))

	def add_outline(self, name, kind, node, sel_tok, detail=''):
		rng, sel = self.range_of(node), self.range_of(sel_tok)
		if rng is None or sel is None:
			return None
		entry = {'name': name, 'kind': kind, 'detail': detail, 'range': rng, 'sel': sel, 'children': []}
		self.current_outline.append(entry)
		return entry

	def analysis(self):
		result = Analysis(self.filename, self.text)
		result.diagnostics = self.diagnostics
		result.syntax_error = self.syntax_error
		result.outline, result.defs, result.refs = self.outline, self.defs, self.refs
		result.scopes = self.scope_records
		return result

	# ----------------------------------------------------------------- entrada
	def lint(self):
		node, error = parse_text(self.filename, self.text)
		if error is not None:
			pos = error.pos_start
			self.diagnostics.append(Diagnostic(
				'NEB001', 'erro', error.details,
				pos.ln + 1 if pos else 1, pos.col + 1 if pos else 1,
				error.pos_end.ln + 1 if error.pos_end else None, error.pos_end.col + 1 if error.pos_end else None,
				self.filename))
			self.syntax_error = True
			self._apply_suppressions()
			return self.diagnostics
		self.syntax_error = False
		self.module_scope = Scope('module')
		self.scope_records.append(((0, 0, 10 ** 9, 0), self.module_scope))
		self.visit(node, self.module_scope)
		self.run_deferred(self.module_scope)
		self.report_unused(self.module_scope)
		self._apply_suppressions()
		self.diagnostics.sort(key=lambda d: (d.line, d.col, d.code))
		return self.diagnostics

	def _apply_suppressions(self):
		per_line, whole_file = {}, set()
		for number, line in enumerate(self.text.split('\n'), 1):
			for match in IGNORE_RE.finditer(line):
				codes = {c.strip() for c in (match.group(2) or '').split(',') if c.strip()}
				if match.group(1):  # -file
					whole_file |= codes or set(RULES)
				else:
					per_line.setdefault(number, set()).update(codes or set(RULES))
		self.diagnostics = [d for d in self.diagnostics
							if d.code not in whole_file and d.code not in per_line.get(d.line, ())]

	def exports(self):
		scope = self.module_scope
		if scope is None:
			return {}
		return {n: s for n, s in scope.symbols.items()
				if not s.private and s.kind in ('function', 'class', 'variable') and not s.imported}

	# ----------------------------------------------------------------- escopos
	def lookup(self, name, scope):
		while scope is not None:
			if name in scope.symbols:
				return scope.symbols[name]
			scope = scope.parent
		return None

	def method_scope(self, scope):
		while scope is not None:
			if scope.kind == 'function' and scope.is_method:
				return scope
			scope = scope.parent
		return None

	def enclosing_function(self, scope):
		while scope is not None:
			if scope.kind == 'function':
				return scope
			scope = scope.parent
		return None

	def run_deferred(self, scope):
		while scope.deferred:
			job = scope.deferred.pop(0)
			job()

	def declare(self, scope, symbol, node=None, duplicate_check=False):
		existing = scope.symbols.get(symbol.name)
		if duplicate_check and existing is not None and existing.kind in ('function', 'class') \
				and symbol.kind in ('function', 'class'):
			self.report('NEB205', node or symbol.tok,
						f"'{symbol.name}' já foi definido na linha {existing.line} deste escopo")
		if symbol.name in self.builtins and scope.kind != 'class' and symbol.kind in ('variable', 'function', 'class') \
				and not symbol.imported:
			self.report('NEB206', node or symbol.tok, f"'{symbol.name}' sombreia a função nativa de mesmo nome")
		scope.symbols[symbol.name] = symbol
		self.add_def(symbol)
		return symbol

	def report_unused(self, scope):
		for sym in scope.symbols.values():
			if sym.used or sym.name.startswith('_'):
				continue
			if sym.imported and sym.import_stmt is not None:
				line_no = sym.import_stmt['line']
				edits = import_line_edits(self.lines, line_no, {sym.name})
				only = edits is not None and edits[0][1] == ''
				fixes = [self.fix(f"Remover a importação de '{sym.name}'" if only else f"Remover '{sym.name}' da importação",
								edits, preferred=True)] if edits else []
				self.report('NEB204', sym.tok, f"'{sym.name}' foi importado mas nunca é usado", fixes=fixes,
							meta={'import_line': line_no, 'kind': 'names', 'name': sym.name})
			elif sym.imported:
				self.report('NEB204', sym.tok, f"'{sym.name}' foi importado mas nunca é usado")
			elif sym.kind == 'module':
				line_no = sym.import_stmt['line'] if sym.import_stmt else None
				edits = import_line_edits(self.lines, line_no, None) if line_no is not None else None
				fixes = [self.fix(f"Remover a importação de '{sym.name}'", edits, preferred=True)] if edits else []
				self.report('NEB204', sym.tok, f"o módulo '{sym.name}' foi importado mas nunca é usado", fixes=fixes,
							meta={'import_line': line_no, 'kind': 'module', 'name': sym.name})
			elif scope.kind == 'function' and not sym.hoisted:
				if sym.kind == 'variable':
					self.report('NEB202', sym.tok, f"a variável '{sym.name}' nunca é usada", fixes=[self.rename_unused_fix(sym.tok)])
				elif sym.kind == 'function':
					self.report('NEB202', sym.tok, f"a função local '{sym.name}' nunca é usada", fixes=[self.rename_unused_fix(sym.tok)])
				elif sym.kind == 'parameter' and sym.name != 'esse':
					self.report('NEB203', sym.tok, f"o parâmetro '{sym.name}' nunca é usado", fixes=[self.rename_unused_fix(sym.tok)])

	# ----------------------------------------------------------------- tipos
	def class_of_type_name(self, name, scope):
		"""ClassInfo do nome de tipo (inclusive `modulo.Classe`), ou None."""
		sym = self.resolve_type_symbol(name, scope)
		return sym.classinfo if sym is not None else None

	def resolve_type_symbol(self, name, scope):
		parts = name.split('.')
		sym = self.lookup(parts[0], scope)
		for part in parts[1:]:
			if sym is None or sym.kind != 'module' or sym.module is None:
				return None
			sym.used = True
			sym = sym.module.exports.get(part)
		if sym is not None and sym.kind == 'class':
			sym.used = True
			return sym
		return None

	def type_name_fixes(self, t, parts, scope):
		start = getattr(t, 'pos_start', None)
		if start is None or t.pos_end.ln != start.ln:
			return []
		if len(parts) == 1:
			candidates = set(PRIMITIVES) | set(SPECIAL) | self.visible_classes(scope)
			prefix = ''
		else:
			base = self.lookup(parts[0], scope)
			if base is None or base.kind != 'module' or base.module is None:
				return []
			candidates = {n for n, s in base.module.exports.items() if s.kind == 'class'}
			prefix = '.'.join(parts[:-1]) + '.'
		close = difflib.get_close_matches(parts[-1], sorted(candidates - {parts[-1]}), n=3, cutoff=0.6)
		col = start.col + len(prefix)
		return [self.fix(f"Trocar por '{prefix}{c}'", [((start.ln, col, start.ln, col + len(parts[-1])), c)], i == 0)
				for i, c in enumerate(close)]

	def check_type_node(self, t, scope):
		if t is None:
			return
		if t.options:
			for option in t.options:
				self.check_type_node(option, scope)
			return
		name = t.name
		if name not in PRIMITIVES and name not in SPECIAL:
			parts = name.split('.')
			sym = self.lookup(parts[0], scope)
			if sym is not None and sym.kind in ('import', 'unknown'):
				sym.used = True
			elif sym is not None and sym.kind == 'module' and (sym.module is None or sym.module.partial):
				sym.used = True
			elif self.resolve_type_symbol(name, scope) is not None:
				self.add_ref(self.resolve_type_symbol(name, scope), t)
			else:
				fixes = self.type_name_fixes(t, parts, scope)
				if sym is not None and len(parts) == 1:
					sym.used = True
					self.report('NEB301', t, f"'{name}' não é uma classe, então não pode ser usado como tipo", fixes=fixes)
				else:
					self.report('NEB301', t, f"tipo desconhecido '{name}'", fixes=fixes)
		if t.args:
			if name not in GENERIC_ARITY:
				self.report('NEB301', t, f"o tipo '{name}' não aceita parâmetros de tipo")
			elif len(t.args) not in GENERIC_ARITY[name]:
				self.report('NEB301', t, f"o tipo '{name}' espera {' ou '.join(map(str, GENERIC_ARITY[name]))} parâmetro(s) de tipo")
			for arg in t.args:
				self.check_type_node(arg, scope)

	def compatible(self, actual, expected, scope):
		"""False só quando temos certeza de que `actual` não cabe em `expected`."""
		if actual is None or expected is None:
			return True
		if expected.options:
			return any(self.compatible(actual, o, scope) for o in expected.options)
		if actual.options:
			return any(self.compatible(a, expected, scope) for a in actual.options)
		en, an = expected.name, actual.name
		if en == 'qualquer' or an == 'qualquer':
			return True
		if en in PRIMITIVES or en in ('função', 'classe'):
			if an != en:
				return False
			if expected.args and actual.args:
				if en == 'dicionário':
					return self.compatible(actual.args[-1], expected.args[-1], scope)
				return self.compatible(actual.args[0], expected.args[0], scope)
			return True
		expected_ci = self.class_of_type_name(en, scope)
		if an in PRIMITIVES or an in ('função', 'classe'):
			return expected_ci is None  # primitivo onde se espera uma classe conhecida
		actual_ci = getattr(actual, 'classinfo', None) or self.class_of_type_name(an, scope)
		if expected_ci is None or actual_ci is None:
			return True
		return actual_ci.inherits(expected_ci)

	def infer(self, node, scope):
		"""Tipo (TypeNode) de uma expressão quando dá para saber estaticamente; senão None."""
		if isinstance(node, NumberNode):
			return T('número')
		if isinstance(node, (StringNode, FStringNode)):
			return T('string')
		if isinstance(node, BoolNode):
			return T('booleano')
		if isinstance(node, ListNode):
			return self._infer_collection('lista', node.element_nodes, scope)
		if isinstance(node, TupleNode):
			return T('tupla')
		if isinstance(node, SetNode):
			return T('mesa')
		if isinstance(node, (DictNode, DictCompNode)):
			return T('dicionário')
		if isinstance(node, FuncDefNode):
			return T('função')
		if isinstance(node, VarAccessNode):
			name = node.var_name_tok.value
			sym = self.lookup(name, scope)
			if sym is None:
				return T('nulo') if name == 'nulo' else None
			if sym.kind == 'function':
				return T('função')
			if sym.kind == 'class':
				return T('classe')
			return sym.type or sym.inferred
		if isinstance(node, UnaryOpNode):
			if node.op_tok.matches(TT_KEYWORD, 'não'):
				return T('booleano')
			inner = self.infer(node.node, scope)
			return inner if inner is not None and inner.name == 'número' else None
		if isinstance(node, BinOpNode):
			op = node.op_tok
			if op.type in COMPARE or op.matches(TT_KEYWORD, 'igual') or op.matches(TT_KEYWORD, 'em'):
				return T('booleano')
			if op.matches(TT_KEYWORD, 'e') or op.matches(TT_KEYWORD, 'ou'):
				return None
			if op.type in ARITH:
				left, right = self.infer(node.left_node, scope), self.infer(node.right_node, scope)
				if left is None or right is None or left.options or right.options:
					return None
				if left.name == 'número' and right.name == 'número':
					return T('número')
				if op.type == TT_PLUS and left.name == 'string' and right.name == 'string':
					return T('string')
				if op.type == TT_MUL and {left.name, right.name} == {'string', 'número'}:
					return T('string')
			return None
		if isinstance(node, CallNode):
			return self._infer_call(node, scope)
		return None

	def _infer_collection(self, name, elements, scope):
		kinds = [self.infer(e, scope) for e in elements]
		if kinds and all(k is not None and not k.options and not k.args and k.name == kinds[0].name
						and getattr(k, 'classinfo', None) is getattr(kinds[0], 'classinfo', None) for k in kinds):
			return T(name, [kinds[0]])
		return T(name)

	def _infer_call(self, node, scope):
		sym = self._callee_symbol(node.node_to_call, scope)
		if sym is not None:
			if sym.kind == 'class':
				return T(sym.name, classinfo=sym.classinfo)
			if sym.kind == 'function':
				return sym.return_type
		callee = node.node_to_call
		if isinstance(callee, VarAccessNode) and self.lookup(callee.var_name_tok.value, scope) is None \
				and callee.var_name_tok.value in BUILTIN_RETURNS:
			return T(BUILTIN_RETURNS[callee.var_name_tok.value])
		return None

	def _callee_symbol(self, callee, scope, mark=False):
		"""Symbol da função/classe chamada, quando resolvível estaticamente."""
		if isinstance(callee, VarAccessNode):
			return self.lookup(callee.var_name_tok.value, scope)
		if isinstance(callee, AttrAccessNode):
			obj = callee.obj_node
			attr = callee.attr_name_tok.value
			if isinstance(obj, VarAccessNode):
				base = self.lookup(obj.var_name_tok.value, scope)
				if base is not None and base.kind == 'module' and base.module is not None:
					return base.module.exports.get(attr)
				ci = self._instance_class(obj, scope)
				if ci is not None:
					return ci.find_method(attr)
			if isinstance(obj, SuperNode):
				ms = self.method_scope(scope)
				if ms is not None and ms.classinfo is not None and ms.classinfo.parent is not None:
					return ms.classinfo.parent.find_method(attr)
		return None

	def _instance_class(self, obj, scope):
		"""ClassInfo da instância que `obj` representa (esse ou variável de tipo conhecido), ou None."""
		if not isinstance(obj, VarAccessNode):
			return None
		sym = self.lookup(obj.var_name_tok.value, scope)
		if sym is None:
			return None
		t = sym.type or sym.inferred
		if t is None or t.options or t.name in PRIMITIVES or t.name in SPECIAL:
			return None
		return getattr(t, 'classinfo', None) or self.class_of_type_name(t.name, scope)

	# ----------------------------------------------------------------- visita
	def line_opens_block(self, line_text):
		"""True se a linha abre um bloco (termina em `então`/`faça`, ou é `tentar`/`classe`/`função` sem `=>`)."""
		tokens, error = Lexer('<linha>', line_text).make_tokens()
		if error or not tokens:
			return True  # na dúvida, não mexe
		tokens = [t for t in tokens if t.type not in (TT_NEWLINE, TT_EOF)]
		if not tokens:
			return False
		first, last = tokens[0], tokens[-1]
		if last.type == TT_KEYWORD and last.value in ('então', 'faça'):
			return True
		if first.matches(TT_KEYWORD, 'tentar') or first.matches(TT_KEYWORD, 'classe'):
			return True
		return first.matches(TT_KEYWORD, 'função') and not any(t.type == TT_ARROW for t in tokens)

	def remove_statement_fix(self, element):
		"""Remove a linha do comando inalcançável. Só para comandos de UMA linha (as posições dos nós de bloco não são precisas)."""
		rng = self.range_of(element)
		if rng is None:
			return None
		l0, _, l1, _ = rng
		if l0 != l1 or l0 >= len(self.lines):
			return None
		line = self.lines[l0].rstrip('\r')
		if not line.strip() or self.line_opens_block(line):
			return None
		return self.fix('Remover código inalcançável', [delete_lines_edit(self.lines, l0, l0)], preferred=True)

	def visit(self, node, scope):
		if isinstance(node, (list, tuple)):
			for item in node:
				self.visit(item, scope)
			return
		if not _is_node(node):
			return
		method = getattr(self, 'v_' + type(node).__name__, None)
		if method is not None:
			return method(node, scope)
		for child in iter_children(node):
			self.visit(child, scope)

	def v_ListNode(self, node, scope):
		terminated = False
		for element in node.element_nodes:
			if terminated:
				self.report('NEB201', element, 'código inalcançável (vem depois de retornar/parar/continuar/levantar)',
							fixes=[self.remove_statement_fix(element)])
				terminated = False
			self.visit(element, scope)
			if terminates(element):
				terminated = True

	def v_VarAccessNode(self, node, scope):
		name = node.var_name_tok.value
		sym = self.lookup(name, scope)
		if sym is not None:
			sym.used = True
			self.add_ref(sym, node.var_name_tok)
			return
		if name in self.builtins:
			return
		ms = self.method_scope(scope)
		if ms is not None and ms.classinfo is not None:  # `this` implícito: atributo/método da instância
			ci = ms.classinfo
			if ci.has_attr(name) or ci.find_method(name) is not None or not ci.fully_known():
				return
		message = f"'{name}' não foi declarado"
		names = set(self.builtins)
		scope_it = scope
		while scope_it is not None:
			names |= set(scope_it.symbols)
			scope_it = scope_it.parent
		close = difflib.get_close_matches(name, names, n=1, cutoff=0.7)
		if close:
			message += f". Você quis dizer '{close[0]}'?"
		self.report('NEB101', node.var_name_tok, message, fixes=self.suggestion_fixes(node.var_name_tok, names, cutoff=0.7))

	def v_SuperNode(self, node, scope):
		ms = self.method_scope(scope)
		if ms is None or ms.classinfo is None:
			self.report('NEB401', node, "'super' só pode ser usado dentro de métodos de classe")
		elif ms.classinfo.parent_tok is None:
			self.report('NEB401', node, f"a classe '{ms.classinfo.name}' não possui superclasse (falta 'extende')")

	def v_VarAssignNode(self, node, scope):
		self.visit(node.value_node, scope) if node.value_node is not None else None
		value_type = self.infer(node.value_node, scope) if node.value_node is not None else None
		if node.type is not None:
			self.check_type_node(node.type, scope)
		for tok in node.var_name_toks:
			name = tok.value
			existing = self.lookup(name, scope)
			ms = self.method_scope(scope)

			if ms is not None and ms.classinfo is not None and 'esse' in ms.symbols:
				# no interpretador, atribuição dentro de método com `esse` vira atributo da instância
				ms.classinfo.attrs.add(name)
				if not node.change_value:
					fixes = []
					before = self.lines[tok.pos_start.ln][:tok.pos_start.col] if tok.pos_start.ln < len(self.lines) else ''
					after = self.lines[tok.pos_end.ln][tok.pos_end.col:].lstrip() if tok.pos_end.ln < len(self.lines) else ''
					match = re.search(r'declarar\s+$', before)
					if match and not after.startswith(':'):
						fixes.append(self.fix(f"Trocar por 'esse.{name}' (atributo da instância)",
											[((tok.pos_start.ln, match.start(), tok.pos_end.ln, tok.pos_end.col), f'esse.{name}')], True))
					self.report('NEB210', tok, f"dentro de métodos, 'declarar {name}' cria o atributo 'esse.{name}', não uma variável local", fixes=fixes)
				continue

			if existing is not None and existing.constant and (node.change_value or existing in scope.symbols.values()):
				self.report('NEB102', tok, f"'{name}' é uma constante e não pode ser alterada")
				continue

			declared = node.type or (existing.type if existing is not None else None)
			if declared is not None and value_type is not None and not self.compatible(value_type, declared, scope):
				self.report('NEB302', node.value_node,
							f"'{name}' é do tipo '{type_name(declared)}', mas o valor é '{type_name(value_type)}'")

			if name in scope.symbols:
				sym = scope.symbols[name]
				self.add_ref(sym, tok)
				if sym.hoisted:
					self.add_def(sym, tok)
				sym.hoisted = False
				if node.type is not None:
					sym.type = node.type
				sym.inferred = value_type if (sym.type is None and sym.inferred is None and not sym.used) else None
				if sym.kind in ('function', 'class', 'import', 'unknown'):
					sym.kind = 'variable'
				if node.constant:
					sym.constant = True
				continue

			if node.change_value and existing is not None and scope.kind == 'function' \
					and existing.kind in ('variable', 'loopvar', 'catchvar', 'parameter'):
				self.report('NEB209', tok, f"esta atribuição cria uma variável local '{name}'; a variável de fora não será alterada",
							fixes=[self.insert_before_fix(tok, 'declarar ', f"Escrever 'declarar {name}' (deixa claro que é uma variável local)")])
			elif node.change_value and existing is None and name not in self.builtins:
				self.report('NEB207', tok, f"'{name}' foi criada por atribuição; considere usar 'declarar {name}'",
							fixes=[self.insert_before_fix(tok, 'declarar ', f"Usar 'declarar {name}'", True)])

			sym = Symbol(name, 'variable', tok, constant=node.constant, private=node.private, type_=node.type)
			sym.inferred = value_type if node.type is None else None
			self.declare(scope, sym, tok)
			if scope.kind in ('module', 'class'):
				detail = type_name(node.type or value_type) if (node.type or value_type) is not None else ''
				self.add_outline(name, 'constant' if node.constant else ('field' if scope.kind == 'class' else 'variable'), tok, tok, detail)

	def v_AttrAccessNode(self, node, scope):
		self.visit(node.obj_node, scope)
		attr = node.attr_name_tok.value
		obj = node.obj_node
		if isinstance(obj, VarAccessNode):
			base = self.lookup(obj.var_name_tok.value, scope)
			if base is not None and base.kind == 'module':
				base.used = True
				module = base.module
				if module is not None and not module.partial:
					member = module.exports.get(attr)
					if member is None:
						self.report('NEB106', node.attr_name_tok, f"o módulo '{base.name}' não tem '{attr}' (ou ele é privado)",
									fixes=self.suggestion_fixes(node.attr_name_tok, module.exports))
					else:
						self.add_ref(member, node.attr_name_tok)
				return
			if obj.var_name_tok.value == 'esse':
				ms = self.method_scope(scope)
				ci = ms.classinfo if ms is not None else None
				if ci is not None and ci.fully_known() and not ci.has_attr(attr) and ci.find_method(attr) is None:
					members = {a for c in ci.chain() for a in c.attrs} | {m for c in ci.chain() for m in c.methods}
					self.report('NEB404', node.attr_name_tok, f"'{ci.name}' não define o atributo ou método '{attr}'",
								fixes=self.suggestion_fixes(node.attr_name_tok, members))
				elif ci is not None and ci.find_method(attr) is not None:
					self.add_ref(ci.find_method(attr), node.attr_name_tok)

	def v_AttrAssignNode(self, node, scope):
		self.visit(node.obj_node, scope)
		self.visit(node.value_node, scope)
		obj = node.obj_node
		if isinstance(obj, VarAccessNode) and obj.var_name_tok.value == 'esse':
			ms = self.method_scope(scope)
			if ms is not None and ms.classinfo is not None:
				ms.classinfo.attrs.add(node.attr_name_tok.value)

	def v_CallNode(self, node, scope):
		self.visit(node.node_to_call, scope)
		for arg in node.arg_nodes:
			self.visit(arg, scope)
		callee = node.node_to_call
		sym = self._callee_symbol(callee, scope)
		bound = isinstance(callee, AttrAccessNode)  # método chamado como obj.metodo(...): `esse` implícito

		if isinstance(callee, SuperNode):
			ms = self.method_scope(scope)
			if ms is not None and ms.classinfo is not None and ms.classinfo.parent is not None:
				ctor = ms.classinfo.parent.find_method('principal')
				self._check_args(node, 'principal', ctor.params[1:] if ctor is not None and ctor.params else [], ctor is not None, scope)
			return

		if isinstance(callee, AttrAccessNode) and isinstance(callee.obj_node, SuperNode):
			ms = self.method_scope(scope)
			parent = ms.classinfo.parent if ms is not None and ms.classinfo is not None else None
			if parent is not None and parent.fully_known() and sym is None and not parent.has_attr(callee.attr_name_tok.value):
				self.report('NEB404', callee.attr_name_tok, f"a superclasse '{parent.name}' não tem o método '{callee.attr_name_tok.value}'",
							fixes=self.suggestion_fixes(callee.attr_name_tok, {m for c in parent.chain() for m in c.methods}))

		if isinstance(callee, AttrAccessNode) and isinstance(callee.obj_node, VarAccessNode):
			ci = self._instance_class(callee.obj_node, scope)
			if ci is not None and ci.fully_known() and sym is None and not ci.has_attr(callee.attr_name_tok.value) \
					and callee.obj_node.var_name_tok.value != 'esse':
				self.report('NEB404', callee.attr_name_tok, f"'{ci.name}' não tem o método '{callee.attr_name_tok.value}'",
							fixes=self.suggestion_fixes(callee.attr_name_tok, {m for c in ci.chain() for m in c.methods}))

		if sym is None:
			return
		if isinstance(callee, AttrAccessNode):
			self.add_ref(sym, callee.attr_name_tok)
		name = callee.var_name_tok.value if isinstance(callee, VarAccessNode) else callee.attr_name_tok.value
		if sym.kind == 'function' and sym.params is not None:
			params = sym.params[1:] if (bound and sym.is_method) else sym.params
			self._check_args(node, name, params, True, scope)
		elif sym.kind == 'class' and sym.classinfo is not None and sym.classinfo.fully_known():
			ctor = sym.classinfo.find_method('principal')
			if ctor is None:
				self._check_args(node, name, [], True, scope, no_ctor=True)
			elif ctor.params is not None:
				self._check_args(node, name, ctor.params[1:], True, scope)

	def _check_args(self, node, name, params, known, scope, no_ctor=False):
		if not known:
			return
		given = len(node.arg_nodes)
		required = sum(1 for p in params if not p.has_default)
		if given < required or given > len(params):
			expected = str(required) if required == len(params) else f'{required} a {len(params)}'
			extra = ' (a classe não tem construtor "principal")' if no_ctor else ''
			self.report('NEB303', node, f"'{name}' espera {expected} argumento(s), mas recebeu {given}{extra}")
			return
		for param, arg in zip(params, node.arg_nodes):
			if param.type is None:
				continue
			actual = self.infer(arg, scope)
			if actual is not None and not self.compatible(actual, param.type, scope):
				self.report('NEB304', arg, f"o argumento '{param.name}' de '{name}' espera '{type_name(param.type)}', mas recebeu '{type_name(actual)}'")

	def v_ForNode(self, node, scope):
		for part in (node.start_value_node, node.end_value_node, node.step_value_node):
			if part is not None:
				self.visit(part, scope)
		self._loop(node, [node.var_name_tok], node.body_node, scope)

	def v_ForEachNode(self, node, scope):
		self.visit(node.iterable_node, scope)
		toks = node.var_name_tok if isinstance(node.var_name_tok, list) else [node.var_name_tok]
		self._loop(node, toks, node.body_node, scope)

	def v_WhileNode(self, node, scope):
		self._loop(node, [], node.body_node, scope, condition=node.condition_node)

	def _loop(self, node, var_toks, body, scope, condition=None):
		self._hoist_assignments(body, scope)
		if condition is not None:
			self.visit(condition, scope)
		for tok in var_toks:
			sym = Symbol(tok.value, 'loopvar', tok)
			sym.used = True
			scope.symbols[tok.value] = sym
			self.add_def(sym)
		scope.loop_depth += 1
		self.visit(body, scope)
		scope.loop_depth -= 1

	def _hoist_assignments(self, body, scope):
		"""Dentro de laços um nome pode ser lido antes (no texto) de ser atribuído, e valer na volta seguinte."""
		stack = [body]
		while stack:
			current = stack.pop()
			if isinstance(current, (FuncDefNode, ClassNode)):
				continue
			if isinstance(current, VarAssignNode):
				for tok in current.var_name_toks:
					if self.lookup(tok.value, scope) is None:
						sym = Symbol(tok.value, 'variable', tok)
						sym.hoisted = True
						scope.symbols[tok.value] = sym
			stack.extend(iter_children(current))

	def v_BreakNode(self, node, scope):
		if scope.loop_depth == 0:
			self.report('NEB502', node, "'parar' só pode ser usado dentro de um laço")

	def v_ContinueNode(self, node, scope):
		if scope.loop_depth == 0:
			self.report('NEB502', node, "'continuar' só pode ser usado dentro de um laço")

	def v_TryCatchNode(self, node, scope):
		self.visit(node.try_body, scope)
		sym = Symbol(node.catch_var_tok.value, 'catchvar', node.catch_var_tok)
		sym.used = True
		scope.symbols[sym.name] = sym
		self.add_def(sym)
		self.visit(node.catch_body, scope)

	def v_DictCompNode(self, node, scope):
		sym = self.lookup(node.iterator.value, scope)
		if sym is not None:
			sym.used = True
			self.add_ref(sym, node.iterator)
		elif node.iterator.value not in self.builtins:
			self.report('NEB101', node.iterator, f"'{node.iterator.value}' não foi declarado")

	def v_ReturnNode(self, node, scope):
		values = node.node_to_return
		values = [] if values is None else (values if isinstance(values, list) else [values])
		values = [v for v in values if v is not None]  # `retornar` sem valor vem como [None]
		for value in values:
			self.visit(value, scope)
		fscope = self.enclosing_function(scope)
		if fscope is None:
			self.report('NEB501', node, "'retornar' só pode ser usado dentro de uma função")
			return
		func = fscope.func
		if func is None or func.return_type is None:
			return
		if len(values) > 1:
			actual = T('tupla')
		elif values:
			actual = self.infer(values[0], scope)
		else:
			actual = T('nulo')
		if actual is not None and not self.compatible(actual, func.return_type, scope):
			target = values[0] if values else node
			self.report('NEB305', target, f"'{func.name}' declara retorno '{type_name(func.return_type)}', mas retorna '{type_name(actual)}'")

	def v_ImportNode(self, node, scope):
		name_tok = node.file_path
		info = self.load_module(name_tok.value, name_tok)
		for tok in node.functions:
			if info is None or info.partial:
				sym = Symbol(tok.value, 'import', tok)
				sym.imported = True
				sym.import_stmt = {'line': name_tok.pos_start.ln, 'kind': 'names'}
				sym.used = info is None  # módulo inexistente já foi reportado (NEB105)
				self.declare(scope, sym, tok)
				continue
			export = info.exports.get(tok.value)
			if export is None:
				self.report('NEB104', tok, f"'{tok.value}' não existe (ou é privado) no módulo '{name_tok.value}'",
							fixes=self.suggestion_fixes(tok, info.exports))
				sym = Symbol(tok.value, 'import', tok)
				sym.used = True
				sym.imported = True
				self.declare(scope, sym, tok)
				continue
			sym = Symbol(tok.value, export.kind, tok, constant=export.constant, type_=export.type)
			sym.params, sym.return_type, sym.classinfo = export.params, export.return_type, export.classinfo
			sym.is_method, sym.inferred = export.is_method, export.inferred
			sym.imported = True
			sym.import_stmt = {'line': name_tok.pos_start.ln, 'kind': 'names'}
			sym.origin = export
			self.declare(scope, sym, tok)

	def v_ImportNamespaceNode(self, node, scope):
		tok = node.module_path
		info = self.load_module(tok.value, tok)
		sym = Symbol(tok.value, 'module', tok)
		sym.module = info
		sym.import_stmt = {'line': tok.pos_start.ln, 'kind': 'module'}
		sym.module_path = info.path if info is not None else None
		sym.used = info is None  # já reportado como NEB105
		self.declare(scope, sym, tok)

	def load_module(self, name, tok):
		path = resolve_module_path(name, self.filename)
		if path is None:
			self.report('NEB105', tok, f"módulo '{name}' não encontrado")
			return None
		key = os.path.normcase(os.path.abspath(path))
		if key in self.shared.modules:
			return self.shared.modules[key]
		if key in self.shared.loading:
			return ModuleInfo(path, partial=True)  # importação circular: não dá para analisar
		self.shared.loading.add(key)
		try:
			try:
				text = Path(path).read_text(encoding='utf-8-sig')
			except OSError:
				info = ModuleInfo(path, partial=True)
			else:
				sub = Linter(path, text, ignore=self.ignore, hints=False, shared=self.shared, is_module=True)
				sub.lint()
				if sub.syntax_error:
					self.report('NEB107', tok, f"o módulo '{name}' tem erro de sintaxe; a análise dele é limitada")
					info = ModuleInfo(path, partial=True)
				else:
					info = ModuleInfo(path, sub.exports())
		finally:
			self.shared.loading.discard(key)
		self.shared.modules[key] = info
		return info

	# ----------------------------------------------------------------- funções e classes
	def v_FuncDefNode(self, node, scope):
		name_tok = node.var_name_tok
		name = name_tok.value if name_tok is not None else '<anônima>'
		params = []
		defaults = node.default_vals or []
		for i, tok in enumerate(node.arg_name_toks):
			has_default = i < len(defaults) and defaults[i][0] is not None
			params.append(Param(tok.value, has_default, node.arg_types[i] if i < len(node.arg_types) else None))
		sym = Symbol(name, 'function', name_tok, private=node.private)
		sym.params, sym.return_type = params, node.return_type
		in_class = scope.kind == 'class' and name_tok is not None
		sym.is_method = in_class

		# valores padrão são avaliados no escopo de quem define
		for _, default in defaults:
			if default is not None:
				self.visit(default, scope)

		if name_tok is not None:
			detail = f"({', '.join(p.name for p in params)})" + (f' -> {node.return_type}' if node.return_type is not None else '')
			if scope.kind in ('module', 'class'):
				self.add_outline(name, 'method' if in_class else 'function', node, name_tok, detail)
			if in_class:
				if not node.arg_name_toks or node.arg_name_toks[0].value != 'esse':
					self.report('NEB402', name_tok, f"o método '{name}' precisa declarar 'esse' como primeiro parâmetro",
								fixes=[self.esse_fix(name_tok)])
				if name in scope.symbols and scope.symbols[name].kind == 'function':
					self.report('NEB205', name_tok, f"o método '{name}' já foi definido na linha {scope.symbols[name].line}")
				scope.classinfo.methods[name] = sym
				scope.symbols[name] = sym
				self.add_def(sym)
			else:
				self.declare(scope, sym, name_tok, duplicate_check=True)

		defining_scope = scope.parent if in_class else scope
		classinfo = scope.classinfo if in_class else None
		scope.deferred.append(lambda: self.analyze_function(node, sym, defining_scope, classinfo, in_class))

	def esse_fix(self, name_tok):
		ln = name_tok.pos_end.ln
		if ln >= len(self.lines):
			return None
		line = self.lines[ln]
		start = name_tok.pos_end.col
		paren = line.find('(', start)
		if paren < 0 or 'usando' not in line[start:paren]:
			return None
		rest = line[paren + 1:].lstrip()
		text = 'esse' if rest.startswith(')') else 'esse, '
		return self.fix("Adicionar 'esse' como primeiro parâmetro", [((ln, paren + 1, ln, paren + 1), text)], True)

	def analyze_function(self, node, sym, defining_scope, classinfo, is_method):
		fscope = Scope('function', parent=defining_scope, func=sym, classinfo=classinfo, is_method=is_method)
		rng = self.range_of(node)
		if rng is not None:
			self.scope_records.append((rng, fscope))
		for i, tok in enumerate(node.arg_name_toks):
			t = node.arg_types[i] if i < len(node.arg_types) else None
			self.check_type_node(t, defining_scope)
			psym = Symbol(tok.value, 'parameter', tok, type_=t)
			if is_method and i == 0 and tok.value == 'esse' and classinfo is not None:
				psym.inferred = T(classinfo.name, classinfo=classinfo)
				psym.used = True
			fscope.symbols[tok.value] = psym
			self.add_def(psym)
		self.check_type_node(node.return_type, defining_scope)

		self.visit(node.body_node, fscope)
		if node.should_auto_return and node.return_type is not None:  # corpo `=> expressão`
			actual = self.infer(node.body_node, fscope)
			if actual is not None and not self.compatible(actual, node.return_type, defining_scope):
				self.report('NEB305', node.body_node,
							f"'{sym.name}' declara retorno '{type_name(node.return_type)}', mas retorna '{type_name(actual)}'")
		elif node.return_type is not None and not terminates(node.body_node):
			if not self.compatible(T('nulo'), node.return_type, defining_scope):
				self.report('NEB306', sym.tok or node.body_node,
							f"'{sym.name}' declara retorno '{type_name(node.return_type)}', mas pode terminar sem 'retornar'")
		self.run_deferred(fscope)
		self.report_unused(fscope)

	def v_ClassNode(self, node, scope):
		name_tok = node.class_name_tok
		ci = ClassInfo(name_tok.value, node.inheritance)
		if node.inheritance is not None:
			parent_sym = self.lookup(node.inheritance.value, scope)
			if parent_sym is None:
				if node.inheritance.value not in self.builtins:
					self.report('NEB403', node.inheritance, f"a superclasse '{node.inheritance.value}' não existe",
								fixes=self.suggestion_fixes(node.inheritance, self.visible_classes(scope)))
			elif parent_sym.kind in ('import', 'unknown') or (parent_sym.kind == 'module'):
				parent_sym.used = True
			elif parent_sym.kind != 'class' or parent_sym.classinfo is None:
				parent_sym.used = True
				self.report('NEB403', node.inheritance, f"'{node.inheritance.value}' não é uma classe")
			else:
				parent_sym.used = True
				self.add_ref(parent_sym, node.inheritance)
				ci.parent = parent_sym.classinfo
				ci.parent_known = True
		sym = Symbol(name_tok.value, 'class', name_tok)
		sym.classinfo = ci
		self.declare(scope, sym, name_tok, duplicate_check=True)

		entry = self.add_outline(name_tok.value, 'class', node, name_tok,
								f'extende {node.inheritance.value}' if node.inheritance is not None else '')
		cscope = Scope('class', parent=scope, classinfo=ci)
		crng = self.range_of(node)
		if crng is not None:
			self.scope_records.append((crng, cscope))
		saved_outline = self.current_outline
		if entry is not None:
			self.current_outline = entry['children']
		self.visit(node.body_node, cscope)
		self.current_outline = saved_outline
		for member, value in cscope.symbols.items():
			if value.kind == 'variable':
				ci.attrs.add(member)
		self._collect_self_attrs(node.body_node, ci)
		scope.deferred.extend(cscope.deferred)

	def _collect_self_attrs(self, body, ci):
		stack = [body]
		while stack:
			current = stack.pop()
			if isinstance(current, AttrAssignNode) and isinstance(current.obj_node, VarAccessNode) \
					and current.obj_node.var_name_tok.value == 'esse':
				ci.attrs.add(current.attr_name_tok.value)
			elif isinstance(current, VarAssignNode):
				pass
			stack.extend(iter_children(current))


# --------------------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------------------
def load_config(start):
	"""Lê `.neblint` (procurando da pasta do arquivo para cima): linhas `ignore=NEB202,NEB204` e `dicas=sim`."""
	config = {'ignore': set(), 'hints': False}
	folder = Path(start).resolve()
	folder = folder if folder.is_dir() else folder.parent
	for directory in [folder, *folder.parents]:
		path = directory / '.neblint'
		if path.is_file():
			for line in path.read_text(encoding='utf-8').splitlines():
				line = line.split('#')[0].strip()
				if '=' not in line:
					continue
				key, value = (p.strip() for p in line.split('=', 1))
				if key == 'ignore':
					config['ignore'] |= {c.strip() for c in value.split(',') if c.strip()}
				elif key in ('dicas', 'hints'):
					config['hints'] = value.lower() in ('sim', 'true', '1', 'yes')
			break
	return config


def lint_text(text, filename='<stdin>', ignore=(), hints=False, shared=None):
	return Linter(filename, text, ignore=ignore, hints=hints, shared=shared).lint()


def analyze_text(text, filename='<stdin>', ignore=(), hints=True, shared=None):
	"""Como lint_text, mas devolve um `Analysis` (diagnósticos + definições/referências + outline) para o servidor LSP."""
	linter = Linter(filename, text, ignore=ignore, hints=hints, shared=shared)
	linter.lint()
	return linter.analysis()


def lint_file(path, ignore=(), hints=False, shared=None, use_config=True):
	config = load_config(path) if use_config else {'ignore': set(), 'hints': False}
	text = Path(path).read_text(encoding='utf-8-sig')
	return lint_text(text, str(path), ignore=set(ignore) | config['ignore'], hints=hints or config['hints'],
					shared=shared)


def collect_files(paths):
	files = []
	for p in paths:
		path = Path(p)
		if path.is_dir():
			for ext in ('*.neb', '*.modneb'):
				files += sorted(path.rglob(ext))
		else:
			files.append(path)
	return files


def lint_paths(paths, ignore=(), hints=False):
	"""Devolve {arquivo: [Diagnostic]} para arquivos e pastas (recursivo)."""
	shared = Shared()
	return {str(f): lint_file(f, ignore=ignore, hints=hints, shared=shared) for f in collect_files(paths)}
