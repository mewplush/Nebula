"""Servidor LSP da Nebula (stdio, sem dependências externas).

Etapa 1: sincronização de documentos + diagnósticos do linter em tempo real.
Etapa 2: estrutura do arquivo (outline), hover e "ir para a definição" (inclusive em módulos importados).
Enquanto o arquivo tem erro de sintaxe, os recursos usam a última análise sem erros (nas linhas que não mudaram).
Veja LSP_DESIGN.md para o plano das próximas etapas (completar, ações rápidas...).

Rodar:  nebula lsp      (o editor inicia o processo e conversa por stdin/stdout)

Regras importantes:
- stdout é SÓ para o protocolo. Qualquer print() solto corromperia a conversa, então sys.stdout
  é redirecionado para stderr enquanto o servidor roda. Logs vão para stderr.
- Posições do LSP são (linha, coluna) 0-based com a coluna em unidades UTF-16.
"""
import difflib
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from . import completion, linter
from .context import global_symbol_table

SEVERITY = {'erro': 1, 'aviso': 2, 'dica': 4}  # DiagnosticSeverity: Error, Warning, Hint
SERVER_NAME = 'nebula-lsp'
SYMBOL_KIND = {'class': 5, 'method': 6, 'function': 12, 'variable': 13, 'constant': 14, 'field': 8}
WORD_RE = re.compile(r'[\w]+', re.UNICODE)


def log(*parts):
	print(f'[{SERVER_NAME}]', *parts, file=sys.stderr, flush=True)


def uri_to_path(uri):
	"""file:///C:/x/a.neb -> C:\\x\\a.neb ; file:///home/x/a.neb -> /home/x/a.neb ; outro esquema -> None."""
	parsed = urllib.parse.urlparse(uri)
	if parsed.scheme != 'file':
		return None
	return urllib.request.url2pathname(urllib.parse.unquote(parsed.path))


def utf16_col(line_text, col):
	"""Converte um índice de caractere (code points) em unidades UTF-16, como o LSP exige."""
	return len(line_text[:col].encode('utf-16-le')) // 2


def col_from_utf16(line_text, units):
	"""Inverso de utf16_col: unidades UTF-16 -> índice de caractere (code points)."""
	total = 0
	for index, ch in enumerate(line_text):
		if total >= units:
			return index
		total += 2 if ord(ch) > 0xFFFF else 1
	return len(line_text)


def range_to_lsp(rng, lines):
	"""(ln0, col0, ln1, col1) em code points -> Range do LSP (UTF-16), limitado ao tamanho do texto."""
	def pos(line, col):
		line = max(0, min(line, len(lines) - 1))
		return {'line': line, 'character': utf16_col(lines[line].rstrip('\r'), col)}
	start, end = pos(rng[0], rng[1]), pos(rng[2], rng[3])
	if (end['line'], end['character']) < (start['line'], start['character']):
		end = dict(start)
	return {'start': start, 'end': end}


def to_lsp_diagnostics(diagnostics, text):
	lines = text.split('\n')

	def position(line, col):  # line/col 1-based do linter -> LSP 0-based
		line0 = max(0, min(line - 1, len(lines) - 1))
		return {'line': line0, 'character': utf16_col(lines[line0].rstrip('\r'), max(0, col - 1))}

	result = []
	for d in diagnostics:
		start = position(d.line, d.col)
		end = position(d.end_line, d.end_col)
		if (end['line'], end['character']) <= (start['line'], start['character']):
			end = {'line': start['line'], 'character': start['character'] + 1}
		result.append({
			'range': {'start': start, 'end': end},
			'severity': SEVERITY.get(d.severity, 2),
			'code': d.code,
			'source': 'nebula-lint',
			'message': d.message,
		})
	return result


class Server:
	def __init__(self, reader, writer):
		self.reader = reader  # arquivo binário
		self.writer = writer  # arquivo binário
		self.documents = {}   # uri -> texto
		self.analyses = {}    # uri -> (texto, Analysis) da última análise
		self.last_good = {}   # uri -> (texto, Analysis) da última análise SEM erro de sintaxe
		self.initialized = False
		self.shutdown_requested = False

	# ------------------------------------------------------------------ transporte
	def read_message(self):
		headers = {}
		while True:
			line = self.reader.readline()
			if not line:
				return None  # EOF
			line = line.decode('ascii', errors='replace').strip()
			if not line:
				break
			name, _, value = line.partition(':')
			headers[name.strip().lower()] = value.strip()
		length = int(headers.get('content-length', 0))
		body = self.reader.read(length)
		if len(body) < length:
			return None
		return json.loads(body.decode('utf-8'))

	def send(self, message):
		body = json.dumps(message, ensure_ascii=False).encode('utf-8')
		self.writer.write(f'Content-Length: {len(body)}\r\n\r\n'.encode('ascii') + body)
		self.writer.flush()

	def respond(self, request_id, result=None):
		self.send({'jsonrpc': '2.0', 'id': request_id, 'result': result})

	def respond_error(self, request_id, code, message):
		self.send({'jsonrpc': '2.0', 'id': request_id, 'error': {'code': code, 'message': message}})

	def notify(self, method, params):
		self.send({'jsonrpc': '2.0', 'method': method, 'params': params})

	# ------------------------------------------------------------------ laço principal
	def run(self):
		while True:
			message = self.read_message()
			if message is None:
				return 0 if self.shutdown_requested else 1
			method = message.get('method')
			request_id = message.get('id')
			params = message.get('params') or {}

			if method == 'exit':
				return 0 if self.shutdown_requested else 1

			if method is None:  # resposta a algo que o servidor pediu: ignoramos
				continue

			is_request = 'id' in message
			if not self.initialized and method != 'initialize':
				if is_request:
					self.respond_error(request_id, -32002, 'servidor ainda não inicializado')
				continue
			if self.shutdown_requested and is_request:
				self.respond_error(request_id, -32600, 'servidor em desligamento')
				continue

			handler = getattr(self, 'on_' + method.replace('/', '_').replace('$', 'dollar'), None)
			if handler is None:
				if is_request:
					self.respond_error(request_id, -32601, f'método não suportado: {method}')
				continue
			try:
				result = handler(params)
			except Exception as exc:  # um bug não pode derrubar o editor
				log('erro em', method, repr(exc))
				if is_request:
					self.respond_error(request_id, -32603, f'erro interno: {exc}')
				continue
			if is_request:
				self.respond(request_id, result)

	# ------------------------------------------------------------------ handlers
	def on_initialize(self, params):
		self.initialized = True
		return {
			'capabilities': {
				'textDocumentSync': {'openClose': True, 'change': 1, 'save': {'includeText': False}},  # 1 = texto completo
				'documentSymbolProvider': True,
				'hoverProvider': True,
				'definitionProvider': True,
				'completionProvider': {'triggerCharacters': ['.'], 'resolveProvider': False},
				'codeActionProvider': {'codeActionKinds': ['quickfix', 'source.organizeImports']},
			},
			'serverInfo': {'name': SERVER_NAME, 'version': '0.1.0'},
		}

	def on_initialized(self, params):
		return None

	def on_shutdown(self, params):
		self.shutdown_requested = True
		return None

	def on_dollar_cancelRequest(self, params):
		return None

	def on_textDocument_didOpen(self, params):
		doc = params['textDocument']
		self.documents[doc['uri']] = doc['text']
		self.publish(doc['uri'])

	def on_textDocument_didChange(self, params):
		uri = params['textDocument']['uri']
		changes = params.get('contentChanges') or []
		if not changes:
			return
		last = changes[-1]
		if 'range' in last and last['range'] is not None:
			log('mudança incremental recebida, mas o servidor pediu texto completo; ignorando')
			return
		self.documents[uri] = last['text']
		self.publish(uri)

	def on_textDocument_didSave(self, params):
		# módulos importados podem ter mudado em disco: reanalisa o arquivo salvo e os abertos
		for uri in list(self.documents):
			self.publish(uri)

	def on_textDocument_didClose(self, params):
		uri = params['textDocument']['uri']
		self.documents.pop(uri, None)
		self.analyses.pop(uri, None)
		self.last_good.pop(uri, None)
		self.notify('textDocument/publishDiagnostics', {'uri': uri, 'diagnostics': []})

	# ------------------------------------------------------------------ análise
	def analyze(self, uri, text):
		path = uri_to_path(uri)
		ignore = set()
		if path:
			ignore = linter.load_config(path)['ignore']
		analysis = linter.analyze_text(text, path or '<untitled>', ignore=ignore, hints=True)
		self.analyses[uri] = (text, analysis)
		if not analysis.syntax_error:
			self.last_good[uri] = (text, analysis)
		return analysis

	def publish(self, uri):
		text = self.documents.get(uri)
		if text is None:
			return
		try:
			diagnostics = to_lsp_diagnostics(self.analyze(uri, text).diagnostics, text)
		except Exception as exc:
			log('falha ao analisar', uri, repr(exc))
			diagnostics = []
		self.notify('textDocument/publishDiagnostics', {'uri': uri, 'diagnostics': diagnostics})

	# ------------------------------------------------------------------ recursos (etapa 2)
	def analysis_for(self, uri, line):
		"""Análise utilizável para uma linha: a atual, ou a última sem erro se aquela linha não mudou."""
		current = self.analyses.get(uri)
		if current is not None and not current[1].syntax_error:
			return current
		good = self.last_good.get(uri)
		if good is not None and current is not None and line is not None:
			now, before = current[0].split('\n'), good[0].split('\n')
			if line < len(now) and line < len(before) and now[line] == before[line]:
				return good
		return None

	def position_in(self, uri, params):
		text = self.documents.get(uri, '')
		lines = text.split('\n')
		line = params['position']['line']
		if line >= len(lines):
			return line, 0, lines
		return line, col_from_utf16(lines[line].rstrip('\r'), params['position']['character']), lines

	def on_textDocument_documentSymbol(self, params):
		uri = params['textDocument']['uri']
		found = self.analyses.get(uri)
		if found is None:
			return []
		text, analysis = found
		if analysis.syntax_error and uri in self.last_good:
			text, analysis = self.last_good[uri]  # estrutura da última versão válida
		lines = text.split('\n')

		def convert(entries):
			out = []
			for e in entries:
				rng = range_to_lsp(e['range'], lines)
				sel = range_to_lsp(e['sel'], lines)
				out.append({
					'name': e['name'], 'detail': e['detail'], 'kind': SYMBOL_KIND[e['kind']],
					'range': rng, 'selectionRange': sel, 'children': convert(e['children']),
				})
			return out
		return convert(analysis.outline)

	def on_textDocument_hover(self, params):
		uri = params['textDocument']['uri']
		line, col, current_lines = self.position_in(uri, params)
		found = self.analysis_for(uri, line)
		if found is None:
			return None
		text, analysis = found
		hit = analysis.symbol_at(line, col)
		if hit is not None:
			symbol, rng = hit
			return {'contents': {'kind': 'markdown', 'value': linter.describe_symbol(symbol)},
					'range': range_to_lsp(rng, text.split('\n'))}
		# nomes nativos (falar, str, máximo...) não têm definição no arquivo
		if line < len(current_lines):
			for match in WORD_RE.finditer(current_lines[line]):
				if match.start() <= col <= match.end() and match.group() in global_symbol_table.symbols:
					value = f'```nebula\n{match.group()}\n```\nnome nativo da Nebula'
					return {'contents': {'kind': 'markdown', 'value': value},
							'range': range_to_lsp((line, match.start(), line, match.end()), current_lines)}
		return None

	def on_textDocument_definition(self, params):
		uri = params['textDocument']['uri']
		line, col, _ = self.position_in(uri, params)
		found = self.analysis_for(uri, line)
		if found is None:
			return None
		text, analysis = found
		hit = analysis.symbol_at(line, col)
		if hit is None:
			return None
		symbol = hit[0]
		target = symbol.origin or symbol
		if target.kind == 'module' and target.module_path:
			zero = {'start': {'line': 0, 'character': 0}, 'end': {'line': 0, 'character': 0}}
			return {'uri': Path(target.module_path).as_uri(), 'range': zero}
		if target.tok is None:
			return None
		rng = linter.Linter.range_of(target.tok)
		if rng is None:
			return None
		if not target.file or str(target.file).startswith('<') or target.file == analysis.filename:
			return {'uri': uri, 'range': range_to_lsp(rng, text.split('\n'))}
		other = self.text_of_file(target.file)
		return {'uri': Path(target.file).as_uri(), 'range': range_to_lsp(rng, other.split('\n'))}

	def on_textDocument_codeAction(self, params):
		uri = params['textDocument']['uri']
		found = self.analyses.get(uri)
		text = self.documents.get(uri)
		if found is None or text is None or found[0] != text:
			return []  # análise desatualizada: as edições poderiam cair no lugar errado
		analysis = found[1]
		lines = text.split('\n')
		only = (params.get('context') or {}).get('only')

		def wants(kind):
			return not only or any(kind == o or kind.startswith(o + '.') for o in only)

		def code_point(position):
			line = max(0, min(position['line'], len(lines) - 1))
			return (position['line'], col_from_utf16(lines[line].rstrip('\r'), position['character']))

		request_start, request_end = code_point(params['range']['start']), code_point(params['range']['end'])

		def to_text_edits(edits):
			return [{'range': range_to_lsp(rng, lines), 'newText': new} for rng, new in edits]

		actions = []
		if wants('quickfix'):
			for d in analysis.diagnostics:
				if not d.fixes:
					continue
				d_start, d_end = (d.line - 1, d.col - 1), (d.end_line - 1, d.end_col - 1)
				if d_start > request_end or request_start > d_end:
					continue  # o diagnóstico não está na seleção/cursor
				lsp_diagnostic = to_lsp_diagnostics([d], text)[0]
				for fix in d.fixes:
					actions.append({
						'title': fix['title'], 'kind': 'quickfix', 'diagnostics': [lsp_diagnostic],
						'isPreferred': bool(fix.get('preferred')),
						'edit': {'changes': {uri: to_text_edits(fix['edits'])}},
					})
		if wants('source.organizeImports'):
			edits = analysis.organize_import_edits()
			if edits:
				actions.append({'title': 'Remover todas as importações não usadas', 'kind': 'source.organizeImports',
								'edit': {'changes': {uri: to_text_edits(edits)}}})
		return actions

	def on_textDocument_completion(self, params):
		uri = params['textDocument']['uri']
		if uri not in self.documents:
			return None
		line, col, lines = self.position_in(uri, params)
		line_text = lines[line].rstrip('\r') if line < len(lines) else ''
		analysis, scope_pos = self.analysis_for_completion(uri, line, col)
		if analysis is None:  # nunca houve análise válida (arquivo novo e com erro): ainda dá palavras-chave e nativos
			analysis = linter.analyze_text('', '<untitled>')
			scope_pos = (0, 0)
		items = completion.complete(analysis, line_text, col, scope_pos, uri_to_path(uri))
		return {'isIncomplete': False, 'items': items}

	def analysis_for_completion(self, uri, line, col):
		"""(Analysis, posição) para consultar escopos. Com erro de sintaxe, usa a última análise válida e mapeia a linha."""
		current = self.analyses.get(uri)
		if current is not None and not current[1].syntax_error:
			return current[1], (line, col)
		# 1ª tentativa: esvazia a linha que está sendo digitada e analisa o resto do texto (reflete o código atual)
		current_lines = self.documents.get(uri, '').split('\n')
		if line < len(current_lines):
			repaired = current_lines[:]
			repaired[line] = ''
			path = uri_to_path(uri)
			analysis = linter.analyze_text('\n'.join(repaired), path or '<untitled>', hints=False)
			if not analysis.syntax_error:
				return analysis, (line, col)
		# 2ª tentativa: última análise válida, mapeando a linha
		good = self.last_good.get(uri)
		if good is None:
			return None, None
		old_lines = good[0].split('\n')
		new_lines = self.documents.get(uri, '').split('\n')
		opcodes = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False).get_opcodes()
		for tag, i1, i2, j1, j2 in opcodes:
			if tag == 'equal' and j1 <= line < j2:
				return good[1], (i1 + (line - j1), col)  # linha igual à da análise: mesma posição
		best = (0, 0)
		for tag, i1, i2, j1, j2 in opcodes:  # linha nova: usa o fim da linha igual mais próxima acima
			if tag == 'equal' and j2 - 1 < line:
				best = (i2 - 1, len(old_lines[i2 - 1].rstrip('\r')))
		return good[1], best

	def text_of_file(self, path):
		"""Texto de um arquivo: do buffer aberto (se estiver aberto) ou do disco."""
		for doc_uri, doc_text in self.documents.items():
			doc_path = uri_to_path(doc_uri)
			if doc_path and os.path.normcase(os.path.abspath(doc_path)) == os.path.normcase(os.path.abspath(path)):
				return doc_text
		try:
			return Path(path).read_text(encoding='utf-8-sig')
		except OSError:
			return ''


def serve(stdin=None, stdout=None):
	"""Roda o servidor em stdio. Devolve o código de saída (0 = encerrou após `shutdown`)."""
	reader = stdin or sys.stdin.buffer
	writer = stdout or sys.stdout.buffer
	real_stdout = sys.stdout
	sys.stdout = sys.stderr  # nada de print() no canal do protocolo
	try:
		return Server(reader, writer).run()
	finally:
		sys.stdout = real_stdout
