"""Ponto de entrada: run(), contexto novo, prelúdio e registro das funções nativas."""

import os

from .paths import STDLIB_DIR
from .config import STATE
from .errors import RTError
from .lexer import Lexer
from .parser import Parser
from .context import Context, SymbolTable, global_symbol_table
from .values import Number
from .builtin_functions import BuiltInFunction
from .interpreter import Interpreter


global_symbol_table.set("nulo", Number.null, True)


global_symbol_table.set("falar", BuiltInFunction("falar"), True)


global_symbol_table.set("pegar", BuiltInFunction("pegar"), True)


global_symbol_table.set("perguntar", BuiltInFunction("perguntar"), True)


global_symbol_table.set("input_int", BuiltInFunction("input_int"), True)


global_symbol_table.set("extender", BuiltInFunction("extender"), True)


global_symbol_table.set("int", BuiltInFunction("número"), True)


global_symbol_table.set("raiz", BuiltInFunction("raiz"), True)


global_symbol_table.set("cubo", BuiltInFunction("cubo"), True)


global_symbol_table.set("quadrado", BuiltInFunction("quadrado"), True)


global_symbol_table.set("str", BuiltInFunction("str"), True)


global_symbol_table.set("len", BuiltInFunction("len"), True)


global_symbol_table.set("é_string", BuiltInFunction("string"), True)


global_symbol_table.set("é_número", BuiltInFunction("num"), True)


global_symbol_table.set("picotar", BuiltInFunction("picotar"), True)


global_symbol_table.set("lista", BuiltInFunction("lista"), True)


global_symbol_table.set("func", BuiltInFunction("func"), True)


global_symbol_table.set("procurar", BuiltInFunction("procurar"), True)


global_symbol_table.set("colocar", BuiltInFunction("colocar"), True)


global_symbol_table.set("estourar", BuiltInFunction("estourar"), True)


global_symbol_table.set("limpar", BuiltInFunction("limpar"), True)


global_symbol_table.set("tipo", BuiltInFunction("type"), True)


global_symbol_table.set("fatiar", BuiltInFunction("fatiar"), True)


global_symbol_table.set("aleatório", BuiltInFunction("aleatório"), True)


global_symbol_table.set("ler_arquivo", BuiltInFunction("ler_arquivo"), True)


global_symbol_table.set("escrever_arquivo", BuiltInFunction("escrever_arquivo"), True)


global_symbol_table.set("executar", BuiltInFunction("clicommand"), True)


global_symbol_table.set("eval", BuiltInFunction("eval"), True)


global_symbol_table.set("python", BuiltInFunction("python"), True)


global_symbol_table.set("update", BuiltInFunction("update"), True)


global_symbol_table.set("esperar", BuiltInFunction("esperar"), True)


global_symbol_table.set("bomba_nuclear_universal", BuiltInFunction("bomba_exit"), True)


global_symbol_table.set("pode_executar", BuiltInFunction("is_callable"), True)


global_symbol_table.set("numerais", BuiltInFunction("numerais"), True)


def new_context():
	"""Cria um contexto de programa novo (use para manter estado, ex.: no shell)."""
	context = Context('<program>')
	context.symbol_table = SymbolTable(global_symbol_table)
	return context


def parse_text(fn, text):
	"""Só lexer + parser (usado por --verificar e pelo shell para detectar blocos incompletos)."""
	lexer = Lexer(fn, text)
	tokens, error = lexer.make_tokens()
	if error: return None, error
	ast = Parser(tokens).parse()
	if ast.error: return None, ast.error
	return ast.node, None


def run(fn, text, context=None):
	previous_filename = STATE.filename
	try:
		lexer = Lexer(fn, text)
		tokens, error = lexer.make_tokens()
		if error: return None, error, None

		STATE.filename = lexer.fn

		parser = Parser(tokens)
		ast = parser.parse()
		if ast.error: return None, ast.error, None

		interpreter = Interpreter()
		if context is None:
			context = new_context()
		result = interpreter.visit(ast.node, context)
		return result.value, result.error, context
	except KeyboardInterrupt:
		raise
	except RecursionError:
		error = RTError(None, None,
			'Recursão profunda demais (limite do interpretador atingido). Verifique se há uma função chamando a si mesma sem condição de parada.',
			context or new_context(), 'Erro de Recursão')
		return None, error, context
	except Exception as exc:  # bug do interpretador: mostra erro limpo (NEBULA_DEBUG=1 mostra o traceback do Python)
		if os.environ.get('NEBULA_DEBUG'):
			raise
		error = RTError(None, None, f'{type(exc).__name__}: {exc}', context or new_context(), 'Erro Interno do Interpretador')
		return None, error, context
	finally:
		STATE.filename = previous_filename


def load_prelude():
	"""Executa stdlib/prelude.neb e expõe tudo que não é privado como global."""
	path = STDLIB_DIR / 'prelude.neb'
	if not path.exists():
		return
	text = path.read_text(encoding='utf-8')
	_, error, ctx = run(str(path), text)
	if error:
		raise RuntimeError('Erro no prelúdio da Nebula:\n' + error.as_string())
	for name, value in ctx.symbol_table.symbols.items():
		if not ctx.symbol_table.is_private(name):
			global_symbol_table.symbols[name] = value
			if name in ctx.symbol_table.constants:
				global_symbol_table.constants.append(name)


load_prelude()
