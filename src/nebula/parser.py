"""Análise sintática: tokens -> AST."""

from .errors import InvalidSyntaxError
from .tokens import (
	TT_ARROW,
	TT_COLON,
	TT_COMMA,
	TT_DIV,
	TT_DOT,
	TT_EE,
	TT_EOF,
	TT_EQ,
	TT_FLOAT,
	TT_GT,
	TT_GTE,
	TT_IDENTIFIER,
	TT_INT,
	TT_KEYWORD,
	TT_LBRACE,
	TT_LBRACKET,
	TT_LPAREN,
	TT_LT,
	TT_LTE,
	TT_ME,
	TT_MINUS,
	TT_MUL,
	TT_NE,
	TT_NEWLINE,
	TT_PE,
	TT_PERCENT,
	TT_PLUS,
	TT_POW,
	TT_RARROW,
	TT_RBRACE,
	TT_RBRACKET,
	TT_RPAREN,
	TT_STRING,
	Token,
)
from .nodes import (
	ArrayAccessNode,
	ArrayAssignNode,
	AttrAccessNode,
	AttrAssignNode,
	BinOpNode,
	BoolNode,
	BreakNode,
	CallNode,
	CheckNode,
	ClassNode,
	ContinueNode,
	DictCompNode,
	DictNode,
	FStringNode,
	ForEachNode,
	ForNode,
	FuncDefNode,
	IfNode,
	ImportNamespaceNode,
	ImportNode,
	ListNode,
	NumberNode,
	RaiseNode,
	ReturnNode,
	SetNode,
	StringNode,
	SuperNode,
	SwitchNode,
	TryCatchNode,
	TupleNode,
	TypeNode,
	UnaryOpNode,
	VarAccessNode,
	VarAssignNode,
	WhileNode,
)


# Guarda o erro de sintaxe que chegou mais longe no texto. Quando o parser desiste e volta atrás
# (backtracking), o erro "genérico" lá do começo do bloco esconderia o erro de verdade;
# no final preferimos o que ocorreu mais adiante.
_FURTHEST = {'error': None}


def _note_error(error):
	pos = getattr(error, 'pos_start', None)
	if pos is None:
		return
	current = _FURTHEST['error']
	if current is None or pos.idx > current.pos_start.idx or (
		pos.idx == current.pos_start.idx
		and current.details == 'Syntaxe Inválida' and error.details != 'Syntaxe Inválida'
	):
		_FURTHEST['error'] = error


class ParseResult:
	def __init__(self):
		self.error = None
		self.node = None
		self.advance_count = 0
		self.to_reverse_count = 0

	def register_advancement(self):
		self.advance_count += 1

	def register(self, res):
		self.advance_count += res.advance_count
		if res.error: self.error = res.error
		return res.node
	
	def try_register(self, res):
		if res.error:
			self.to_reverse_count = res.advance_count
			return None
		return self.register(res)

	def success(self, node):
		self.node = node
		return self

	def failure(self, error):
		_note_error(error)
		if not self.error or self.advance_count == 0:
			self.error = error
		return self


class Parser:
	def __init__(self, tokens):
		self.tokens = tokens
		self.tok_idx = -1
		self.stack = []
		self.advance()
	
	def peek(self):
		return self.tokens[self.tok_idx + 1] if len(self.tokens) > self.tok_idx + 1 else None

	def advance(self, res=None):
		if res: res.register_advancement()
		self.tok_idx += 1
		self.update_current_tok()
		return self.current_tok
	
	def reverse(self, amount=1):
		self.tok_idx -= amount
		self.update_current_tok()
		return self.current_tok

	def update_current_tok(self):
		
		if self.tok_idx >= 0 and self.tok_idx < len(self.tokens):
			self.current_tok = self.tokens[self.tok_idx]
		
		if not isinstance(self.current_tok, Token):
			raise SyntaxError(f"Token inválido: {self.current_tok}")

	def parse(self):
		saved = _FURTHEST['error']
		_FURTHEST['error'] = None  # parse aninhado (strings com ${...}) não pode bagunçar o do pai
		try:
			if all(tok.type in (TT_NEWLINE, TT_EOF) for tok in self.tokens):  # arquivo vazio / só linhas em branco e comentários
				empty = ParseResult()
				return empty.success(ListNode([], self.tokens[0].pos_start.copy(), self.tokens[-1].pos_end.copy()))
			res = self.statements()
			if not res.error and self.current_tok.type != TT_EOF:
				res.failure(InvalidSyntaxError(
					self.current_tok.pos_start, self.current_tok.pos_end,
					"Syntaxe Inválida"
				))
			furthest = _FURTHEST['error']
			if res.error and furthest is not None and furthest is not res.error \
					and furthest.pos_start.idx > res.error.pos_start.idx:
				res.error = furthest
			return res
		finally:
			_FURTHEST['error'] = saved
	
	def skip_newline(self, res):
		if self.current_tok.type == TT_NEWLINE:
			res.register_advancement()
			self.advance()
			return True

	###################################

	def statements(self):
		res = ParseResult()
		statements = []
		pos_start = self.current_tok.pos_start.copy()

		while self.current_tok.type == TT_NEWLINE:
			res.register_advancement()
			self.advance()

		statement = res.register(self.statement())
		if res.error: return res
		statements.append(statement)

		more_statements = True

		while True:
			newline_count = 0
			while self.current_tok.type == TT_NEWLINE:
				res.register_advancement()
				self.advance()
				newline_count += 1
			if newline_count == 0:
				more_statements = False
			
			if not more_statements: break
			statement = res.try_register(self.statement())
			if not statement:
				self.reverse(res.to_reverse_count)
				more_statements = False
				continue
			statements.append(statement)

		return res.success(ListNode(
			statements,
			pos_start,
			self.current_tok.pos_end.copy()
		))
	
	def statement(self):
		res = ParseResult()
		pos_start = self.current_tok.pos_start.copy()

		if self.current_tok.matches(TT_KEYWORD, 'retornar'):
			self.advance(res)

			return_values = []

			expr = res.try_register(self.expr())
			if not expr:
				self.reverse(res.to_reverse_count)

			return_values.append(expr)

			while self.current_tok.type == TT_COMMA:
				res.register_advancement()
				self.advance()

				expr = res.register(self.expr())
				if res.error: return res

				return_values.append(expr)
			return res.success(ReturnNode(return_values, pos_start, self.current_tok.pos_start.copy()))
	
		elif self.current_tok.matches(TT_KEYWORD, 'conferir'):
			self.advance(res)

			condition = res.register(self.expr())
			if res.error: return res

			error_to_raise = None
			details = None

			if self.current_tok.matches(TT_KEYWORD, 'usando'):
				self.advance(res)

				error_to_raise = res.register(self.expr())
				if res.error: return res

			if self.current_tok.matches(TT_KEYWORD, 'detalhes'):
				self.advance(res)

				details = res.register(self.expr())
				if res.error: return res

			return res.success(CheckNode(condition, error_to_raise, details, pos_start, self.current_tok.pos_start.copy()))
		
		elif self.current_tok.matches(TT_KEYWORD, 'levantar'):
			self.advance(res)

			error_to_raise = res.register(self.expr())
			if res.error: return res

			if not self.current_tok.matches(TT_KEYWORD, 'detalhes'):
				return res.failure(InvalidSyntaxError(
					self.current_tok.pos_start, self.current_tok.pos_end,
					"Esperava-se 'detalhes'"
				))
			
			self.advance(res)

			details = res.register(self.expr())
			if res.error: return res

			return res.success(RaiseNode(error_to_raise, details, pos_start, self.current_tok.pos_start.copy()))
		
		elif self.current_tok.matches(TT_KEYWORD, 'importar'):
			self.advance(res)
			
			if not self.current_tok.type == TT_IDENTIFIER:
				return res.failure(InvalidSyntaxError(
					self.current_tok.pos_start, self.current_tok.pos_end,
					"Esperava-se um identificador"
				))
			
			functions = []
			functions.append(self.current_tok)

			self.advance(res)
			
			while self.current_tok.type == TT_COMMA:
				self.advance(res)
				
				if not self.current_tok.type == TT_IDENTIFIER:
					return res.failure(InvalidSyntaxError(
						self.current_tok.pos_start, self.current_tok.pos_end,
						"Esperava-se um identificador"
					))
				
				functions.append(self.current_tok)
				self.advance(res)

			if not self.current_tok.matches(TT_KEYWORD, 'de'):
				if len(functions) > 1:
					return res.failure(InvalidSyntaxError(
						self.current_tok.pos_start, self.current_tok.pos_end,
						"Esperava-se 'de' para importar mais de uma função"
					))
				return res.success(ImportNamespaceNode(functions[0], pos_start, self.current_tok.pos_start.copy()))
			
			self.advance(res)
			
			if not self.current_tok.type == TT_IDENTIFIER:
				return res.failure(InvalidSyntaxError(
					self.current_tok.pos_start, self.current_tok.pos_end,
					"Esperava-se um identificador"
				))
			
			module_path = self.current_tok

			self.advance(res)

			return res.success(ImportNode(module_path, functions, pos_start, self.current_tok.pos_start.copy()))

		elif self.current_tok.matches(TT_KEYWORD, 'continuar'):
			self.advance(res)
			return res.success(ContinueNode(pos_start, self.current_tok.pos_start.copy()))
		
		elif self.current_tok.matches(TT_KEYWORD, 'parar'):
			self.advance(res)
			return res.success(BreakNode(pos_start, self.current_tok.pos_start.copy()))
		
		expr = res.register(self.expr())
		if res.error:
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				"Syntaxe Inválida"
			))
		return res.success(expr)

	def if_expr(self):
		res = ParseResult()
		all_cases = res.register(self.if_expr_cases('se'))
		if res.error: return res
		cases, else_case = all_cases
		return res.success(IfNode(cases, else_case))

	def if_expr_b(self):
		return self.if_expr_cases('mas')
	
	def if_expr_c(self):
		res = ParseResult()
		else_case = None

		if self.current_tok.matches(TT_KEYWORD, 'senão'):
			res.register_advancement()
			self.advance()

			if self.current_tok.type == TT_NEWLINE:
				res.register_advancement()
				self.advance()

				statements = res.register(self.statements())
				if res.error: return res
				else_case = (statements, True)

				if self.current_tok.matches(TT_KEYWORD, 'fim'):
					res.register_advancement()
					self.advance()
				else:
					return res.failure(InvalidSyntaxError(
						self.current_tok.pos_start, self.current_tok.pos_end,
						"Esperava-se 'fim'"
					))
			else:
				expr = res.register(self.statement())
				if res.error: return res
				else_case = (expr, False)

		return res.success(else_case)

	def if_expr_b_or_c(self):
		res = ParseResult()
		cases, else_case = [], None

		if self.current_tok.matches(TT_KEYWORD, 'mas'):
			all_cases = res.register(self.if_expr_b())
			if res.error: return res
			cases, else_case = all_cases
		elif self.current_tok.matches(TT_KEYWORD, 'senão'):
			else_case = res.register(self.if_expr_c())
			if res.error: return res
			
		return res.success((cases, else_case))

	def if_expr_cases(self, case_keyword):
		res = ParseResult()
		cases = []
		else_case = None

		if not self.current_tok.matches(TT_KEYWORD, case_keyword):
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				f"Esperava-se '{case_keyword}'"
			))

		res.register_advancement()
		self.advance()

		condition = res.register(self.expr())
		if res.error: return res

		if not self.current_tok.matches(TT_KEYWORD, 'então'):
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				f"Esperava-se 'então'"
			))

		res.register_advancement()
		self.advance()

		if self.current_tok.type == TT_NEWLINE:
			res.register_advancement()
			self.advance()

			statements = res.register(self.statements())
			if res.error: return res
			cases.append((condition, statements, True))

			if self.current_tok.matches(TT_KEYWORD, 'fim'):
				res.register_advancement()
				self.advance()

		else:
			expr = res.register(self.statement())
			if res.error: return res
			cases.append((condition, expr, False))

		all_cases = res.register(self.if_expr_b_or_c())
		if res.error: return res
		new_cases, else_case = all_cases
		cases.extend(new_cases)

		return res.success((cases, else_case))
	
	def try_expr(self):
		res = ParseResult()

		if not self.current_tok.matches(TT_KEYWORD, 'tentar'):
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				f"Esperava-se 'tentar'"
			))

		res.register_advancement()
		self.advance()

		if self.current_tok.type == TT_NEWLINE:
			res.register_advancement()
			self.advance()

			try_body = res.register(self.statements())
			if res.error: return res
		elif self.current_tok.type == TT_ARROW:
			res.register_advancement()
			self.advance()

			try_body = res.register(self.statement())
			if res.error: return res
		else:
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				f"Esperava-se 'nova	linha' ou '=>'"
			))

		if not self.current_tok.matches(TT_KEYWORD, 'caso'):
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				f"Esperava-se 'caso'"
			))
		
		res.register_advancement()
		self.advance()

		if self.current_tok.type != TT_IDENTIFIER:
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				"Esperava-se um identificador"
			))
		
		catch_var_name = self.current_tok
		res.register_advancement()
		self.advance()

		if not self.current_tok.matches(TT_KEYWORD, 'faça'):
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				f"Esperava-se 'faça'"
			))

		res.register_advancement()
		self.advance()

		if self.current_tok.type == TT_NEWLINE:
			res.register_advancement()
			self.advance()

			exception_body = res.register(self.statements())
			if res.error: return res
		elif self.current_tok.type == TT_ARROW:
			res.register_advancement()
			self.advance()

			exception_body = res.register(self.statement())
			if res.error: return res
		else:
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				f"Esperava-se 'nova	linha' ou '=>'"
			))

		if not self.current_tok.matches(TT_KEYWORD, 'fim'):
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				f"Esperava-se 'fim'"
			))

		res.register_advancement()
		self.advance()

		return res.success(TryCatchNode(try_body, catch_var_name, exception_body))
	
	def switch_expr(self):
		res = ParseResult()
		pos_start = self.current_tok.pos_start.copy()

		if not self.current_tok.matches(TT_KEYWORD, 'comparar'):
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				f"Esperava-se 'comparar'"
			))

		res.register_advancement()
		self.advance()

		expr_to_compare = res.register(self.expr())
		if res.error: return res

		if self.current_tok.type != TT_NEWLINE:
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				f"Esperava-se nova linha"
			))

		res.register_advancement()
		self.advance()

		cases = []
		default_case = None

		while self.current_tok.matches(TT_KEYWORD, 'caso'):
			case_start_pos = self.current_tok.pos_start.copy()
			
			res.register_advancement()
			self.advance()

			case_value = res.register(self.expr())
			if res.error: return res

			if not self.current_tok.matches(TT_KEYWORD, 'faça'):
				return res.failure(InvalidSyntaxError(
					self.current_tok.pos_start, self.current_tok.pos_end,
					f"Esperava-se 'faça'"
				))
			
			res.register_advancement()
			self.advance()

			if self.current_tok.type == TT_NEWLINE:
				res.register_advancement()
				self.advance()

				body = res.register(self.statements())
				if res.error: return res
				cases.append((case_value, body, True, case_start_pos))
			else:
				expr = res.register(self.statement())
				if res.error: return res
				cases.append((case_value, expr, False, case_start_pos))

		if self.current_tok.matches(TT_KEYWORD, 'senão'):
			else_start_pos = self.current_tok.pos_start.copy()
			res.register_advancement()
			self.advance()

			if not self.current_tok.matches(TT_KEYWORD, 'então'):
				return res.failure(InvalidSyntaxError(
					self.current_tok.pos_start, self.current_tok.pos_end,
					f"Esperava-se 'então'"
				))
			
			res.register_advancement()
			self.advance()

			if self.current_tok.type == TT_NEWLINE:
				res.register_advancement()
				self.advance()

				statements = res.register(self.statements())
				if res.error: return res
				default_case = (statements, True, else_start_pos)
			else:
				expr = res.register(self.statement())
				if res.error: return res
				default_case = (expr, False, else_start_pos)
			
			

		if not self.current_tok.matches(TT_KEYWORD, 'fim'):
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				f"Esperava-se 'fim'"
			))

		res.register_advancement()
		self.advance()

		return res.success(SwitchNode(
			expr_to_compare, 
			cases, 
			default_case,
			pos_start,
			self.current_tok.pos_end.copy()
		))
			
	def atom(self):
		res = ParseResult()
		tok = self.current_tok
		pos_start = self.current_tok.pos_start.copy()

		if tok.type in (TT_INT, TT_FLOAT):
			res.register_advancement()
			self.advance()
			return res.success(NumberNode(tok))

		elif self.current_tok.matches(TT_KEYWORD, 'verdadeiro') or self.current_tok.matches(TT_KEYWORD, 'falso'):
			self.advance(res)
			return res.success(BoolNode(tok))
		
		elif tok.type == TT_STRING:
			parts = []
			pos_start = tok.pos_start.copy()
			
			for part_type, part_value in tok.parts[0]:
				if part_type == 'TEXT':
					parts.append(StringNode(Token(TT_STRING, part_value, pos_start, pos_start)))
				elif part_type == 'EXPR':
					expr_parser = Parser(part_value)
					expr_node = expr_parser.parse()
					if expr_node.error:
						return res.failure(expr_node.error)
					parts.append(expr_node.node)
			
			self.advance(res)
			return res.success(FStringNode(parts, pos_start, tok.pos_end))
		
		elif tok.type == TT_LBRACE:
			dict_expr = res.register(self.dict_expr())
			if res.error: return res
			return res.success(dict_expr)

		elif tok.type == TT_IDENTIFIER:
			res.register_advancement()
			self.advance()

			if self.current_tok.type in (TT_EQ, TT_ARROW, TT_PE, TT_ME):
				current_tok_type = self.current_tok.type
				res.register_advancement()
				self.advance()
				value = res.register(self.expr())
				if res.error: return res

				if current_tok_type in (TT_PE, TT_ME):
					target = tok
					op_type = TT_PLUS if current_tok_type == TT_PE else TT_MINUS
					op_tok = Token(op_type, pos_start=target.pos_start.copy(), pos_end=value.pos_end.copy())
					bin_op_node = BinOpNode(VarAccessNode(tok), op_tok, value)
					bin_op_node.pos_start = target.pos_start
					bin_op_node.pos_end = value.pos_end
					value = bin_op_node

				return res.success(VarAssignNode(tok, value, change_value=True))
			else:
				return res.success(VarAccessNode(tok))
		
		elif tok.matches(TT_KEYWORD, 'se'):
			if_expr = res.register(self.if_expr())
			if res.error: return res
			return res.success(if_expr)

		elif tok.matches(TT_KEYWORD, 'enquanto'):
			while_expr = res.register(self.while_expr())
			if res.error: return res
			return res.success(while_expr)
	
		elif tok.matches(TT_KEYWORD, 'função'):
			func_def = res.register(self.func_def())
			if res.error: return res
			return res.success(func_def)

		elif tok.matches(TT_KEYWORD, 'caminhando'):
			for_expr = res.register(self.for_expr())		
			if res.error: return res
			return res.success(for_expr)
		
		elif tok.matches(TT_KEYWORD, 'para'):
			for_each_expr = res.register(self.for_each_expr())
			if res.error: return res
			return res.success(for_each_expr)
		
		elif tok.matches(TT_KEYWORD, 'classe'):
			class_def = res.register(self.class_def())
			if res.error: return res
			return res.success(class_def)
		
		elif tok.matches(TT_KEYWORD, 'tentar'):
			try_expr = res.register(self.try_expr())
			if res.error: return res
			return res.success(try_expr)
		
		elif tok.matches(TT_KEYWORD, 'comparar'):
			switch_expr = res.register(self.switch_expr())
			if res.error: return res
			return res.success(switch_expr)

		elif tok.type == TT_LPAREN:
			pos_start = tok.pos_start.copy()
			res.register_advancement()
			self.advance()
			elements = []

			if self.current_tok.type == TT_RPAREN:
				res.register_advancement()
				self.advance()
				return res.success(TupleNode(elements, pos_start, self.current_tok.pos_end.copy()))

			expr = res.register(self.expr())
			if res.error: return res
			if self.current_tok.type == TT_RPAREN:
				res.register_advancement()
				self.advance()
				return res.success(expr)
			
			elif self.current_tok.type == TT_COMMA:
				res.register_advancement()
				self.advance()
				elements.append(expr)
				elements.append(res.register(self.expr()))
				if res.error: return res

				while self.current_tok.type == TT_COMMA:
					res.register_advancement()
					self.advance()
					elements.append(res.register(self.expr()))
					if res.error: return res

				if self.current_tok.type != TT_RPAREN:
					return res.failure(InvalidSyntaxError(
						self.current_tok.pos_start, self.current_tok.pos_end,
						"Esperava-se ')'"
					))
				res.register_advancement()
				self.advance()

				return res.success(TupleNode(elements, pos_start, self.current_tok.pos_end.copy()))
			else:
				return res.failure(InvalidSyntaxError(
					self.current_tok.pos_start, self.current_tok.pos_end,
					"Esperava-se ')' ou ','"
				))
		
		elif tok.type == TT_LBRACKET:
			list_expr = res.register(self.list_expr())
			if res.error: return res
			return res.success(list_expr)
		
		elif tok.matches(TT_KEYWORD, 'super'):
			pos_start = tok.pos_start.copy()
			
			self.advance(res)

			return res.success(SuperNode(pos_start, self.current_tok.pos_end.copy()))

		return res.failure(InvalidSyntaxError(
			tok.pos_start, tok.pos_end,
			"Syntaxe Inválida"
		))
	
	def list_expr(self):
		res = ParseResult()
		element_nodes = []
		pos_start = self.current_tok.pos_start.copy()

		if self.current_tok.type != TT_LBRACKET:
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				"Esperava-se '['"
			))
		
		self.advance(res)

		if self.current_tok.type == TT_RBRACKET:
			self.advance(res)
			return res.success(ListNode(element_nodes, pos_start, self.current_tok.pos_end.copy()))
		else:
			if self.current_tok.type == TT_NEWLINE:
				self.advance(res)
			element_nodes.append(res.register(self.expr()))
			if res.error:
				return res.failure(InvalidSyntaxError(
					self.current_tok.pos_start, self.current_tok.pos_end,
					"Syntaxe Inválida"
				))

			while self.current_tok.type == TT_COMMA:
				res.register_advancement()
				self.advance()

				
				if self.current_tok.type == TT_NEWLINE:
					self.advance(res)

				element_nodes.append(res.register(self.expr()))
				if res.error: return res

			
			if self.current_tok.type == TT_NEWLINE:
				self.advance(res)

			if self.current_tok.type != TT_RBRACKET:
				return res.failure(InvalidSyntaxError(
					self.current_tok.pos_start, self.current_tok.pos_end,
					"Esperava-se ']' ou ','"
				))

			res.register_advancement()
			self.advance()
			return res.success(ListNode(element_nodes, pos_start, self.current_tok.pos_end.copy()))
	
	def set_expr(self):
		res = ParseResult()
		elements = []
		pos_start = self.current_tok.pos_start.copy()

		while True:
			if self.current_tok.type == TT_NEWLINE:
				self.advance(res)
			
			if self.current_tok.type == TT_RBRACE:
				return res.failure(InvalidSyntaxError(
					pos_start, self.current_tok.pos_end.copy(),
					"Não se pode ter uma Mesa vazia, esperava-se elemento (depois de ',' ou '{')\nSe está tentando criar um dicionário, faltou um identificador."
				))
			
			expr = res.register(self.expr())
			if res.error: return res
			elements.append(expr)

			if self.current_tok.type == TT_COMMA:
				self.advance(res)
				continue

			if self.current_tok.type == TT_NEWLINE:
				self.advance(res)

			if not self.current_tok.type == TT_RBRACE:
				return res.failure(InvalidSyntaxError(
					pos_start, self.current_tok.pos_end.copy(),
					"Esperava-se um '}' após fim de Mesa."
				))
			
			self.advance(res)

			return res.success(SetNode(elements, pos_start, self.current_tok.pos_end.copy()))
	
	def dict_comprehension(self, pos_start):
		res = ParseResult()

		self.advance(res)

		if not self.current_tok.matches(TT_KEYWORD, 'cada'):
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				"Esperava-se 'cada'"
			))

		res.register_advancement()
		self.advance()

		if not self.current_tok.type == TT_IDENTIFIER:
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				"Esperava-se identificador para variável de iteração"
			))

		var_name = self.current_tok
		res.register_advancement()
		self.advance()

		if not self.current_tok.type == TT_COLON:
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				"Esperava-se ':'"
			))

		res.register_advancement()
		self.advance()

		if not self.current_tok.type == TT_IDENTIFIER:
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				"Esperava-se identificador para variável de iteração"
			))
		
		value_expr = self.current_tok

		res.register_advancement()
		self.advance()

		if not self.current_tok.matches(TT_KEYWORD, 'em'):
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				"Esperava-se 'em'"
			))
		
		res.register_advancement()
		self.advance()
		
		if not self.current_tok.type == TT_IDENTIFIER:
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				"Esperava-se identificador para variável de iteração"
			))
		
		iterable = self.current_tok

		res.register_advancement()
		self.advance()

		if not self.current_tok.type == TT_RBRACE:
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				"Esperava-se '}'"
			))

		res.register_advancement()
		self.advance()

		return res.success(DictCompNode(var_name, value_expr, iterable, pos_start, self.current_tok.pos_end.copy()))
	
	def dict_expr(self):
		res = ParseResult()
		pairs = []
		pos_start = self.current_tok.pos_start.copy()
		
		res.register_advancement()
		self.advance()
		
		if self.current_tok.type == TT_NEWLINE:
			self.advance(res)
		
		if self.current_tok.type == TT_RBRACE:
			res.register_advancement()
			self.advance()
			return res.success(DictNode([], pos_start, self.current_tok.pos_end.copy()))
		
		while True:
			if self.current_tok.type == TT_NEWLINE:
				self.advance(res)

			if self.current_tok.matches(TT_KEYWORD, 'para'):
				dictcomp = res.register(self.dict_comprehension(pos_start))
				if res.error: return res
				return res.success(dictcomp)

			if not self.current_tok.type in (TT_IDENTIFIER, TT_STRING):
				set_expr = res.register(self.set_expr())
				if res.error: return res
				return res.success(set_expr)
			
			key = self.current_tok
			if res.error: return res

			self.advance(res)
			
			if self.current_tok.type != TT_COLON:
				if key.type == TT_STRING:
					set_expr = res.register(self.set_expr())
					if res.error: return res
					return res.success(set_expr)
				return res.failure(InvalidSyntaxError(
					self.current_tok.pos_start, self.current_tok.pos_end,
					"Esperava-se ':' depois de 'chave' de um dicionário"
				))
			
			res.register_advancement()
			self.advance()
			
			value = res.register(self.expr())
			if res.error: return res
			
			pairs.append((key, value))
			
			if self.current_tok.type != TT_COMMA:
				break
				
			res.register_advancement()
			self.advance()
		
		
		if self.current_tok.type == TT_NEWLINE:
			self.advance(res)
		
		if self.current_tok.type != TT_RBRACE:
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				"Esperava-se ',' ou '}'"
			))
		
		res.register_advancement()
		self.advance()
		return res.success(DictNode(pairs, pos_start, self.current_tok.pos_end.copy()))


	def class_def(self):
		res = ParseResult()
		
		if not self.current_tok.matches(TT_KEYWORD, 'classe'):
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				f"Esperava-se 'classe'"
			))
		
		res.register_advancement()
		self.advance()
		
		if self.current_tok.type != TT_IDENTIFIER:
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				"Esperava-se um identificador para o nome da classe"
			))
		
		class_name_tok = self.current_tok
		res.register_advancement()
		self.advance()

		parent_name = None
		if self.current_tok.matches(TT_KEYWORD, 'extende'):
			self.advance(res)

			if self.current_tok.type != TT_IDENTIFIER:
				return res.failure(InvalidSyntaxError(
					self.current_tok.pos_start, self.current_tok.pos_end,
					"Esperava-se um identificador para o nome da classe pai"
				))
			
			parent_name = self.current_tok
			res.register_advancement()
			self.advance()
		
		if self.current_tok.type != TT_NEWLINE:
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				"Esperava-se nova linha"
			))
		
		res.register_advancement()
		self.advance()
		
		while self.current_tok.type == TT_NEWLINE:
			self.advance(res)
		if self.current_tok.matches(TT_KEYWORD, 'fim'):  # classe sem corpo
			body = ListNode([], self.current_tok.pos_start.copy(), self.current_tok.pos_start.copy())
		else:
			body = res.register(self.statements())
			if res.error: return res
		
		if not self.current_tok.matches(TT_KEYWORD, 'fim'):
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				f"Esperava-se 'fim' para fechar a classe '{class_name_tok.value}' (aberta na linha {class_name_tok.pos_start.ln + 1})"
			))
		
		res.register_advancement()
		self.advance()
		
		return res.success(ClassNode(class_name_tok, body, parent_name))

	TYPE_KEYWORDS = ('lista', 'tupla', 'mesa', 'dicionário', 'string', 'número', 'função')

	def type_expr(self):
		"""tipo := atomo ('ou' atomo)*"""
		res = ParseResult()
		first = res.register(self.type_atom())
		if res.error: return res
		options = [first]
		while self.current_tok.matches(TT_KEYWORD, 'ou'):
			self.advance(res)
			option = res.register(self.type_atom())
			if res.error: return res
			options.append(option)
		if len(options) == 1:
			return res.success(first)
		return res.success(TypeNode(options=options, pos_start=first.pos_start, pos_end=options[-1].pos_end))

	def type_atom(self):
		"""atomo := NOME ['[' tipo (',' tipo)* ']']"""
		res = ParseResult()
		tok = self.current_tok
		is_name = tok.type == TT_IDENTIFIER or (tok.type == TT_KEYWORD and tok.value in self.TYPE_KEYWORDS)
		if not is_name:
			return res.failure(InvalidSyntaxError(
				tok.pos_start, tok.pos_end,
				"Esperava-se um tipo (ex.: número, string, lista[número], MinhaClasse, número ou nulo)"
			))
		self.advance(res)
		name = tok.value
		pos_end = tok.pos_end
		while self.current_tok.type == TT_DOT:  # modulo.Classe (importar modulo)
			self.advance(res)
			if self.current_tok.type != TT_IDENTIFIER:
				return res.failure(InvalidSyntaxError(
					self.current_tok.pos_start, self.current_tok.pos_end,
					"Esperava-se o nome de uma classe depois do '.' no tipo"
				))
			name += '.' + self.current_tok.value
			pos_end = self.current_tok.pos_end
			self.advance(res)
		args = []
		if self.current_tok.type == TT_LBRACKET:
			self.advance(res)
			args.append(res.register(self.type_expr()))
			if res.error: return res
			while self.current_tok.type == TT_COMMA:
				self.advance(res)
				args.append(res.register(self.type_expr()))
				if res.error: return res
			if self.current_tok.type != TT_RBRACKET:
				return res.failure(InvalidSyntaxError(
					self.current_tok.pos_start, self.current_tok.pos_end,
					"Esperava-se ']' para fechar o tipo"
				))
			pos_end = self.current_tok.pos_end
			self.advance(res)
		return res.success(TypeNode(name=name, pos_start=tok.pos_start, pos_end=pos_end, args=args))

	def func_def(self):
		res = ParseResult()
		if not self.current_tok.matches(TT_KEYWORD, 'função'):
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				'Esperava-se "função"'
			))
		
		self.advance(res)
		is_private = False

		if self.current_tok.matches(TT_KEYWORD, 'privada'):
			self.advance(res)
			is_private = True

		if self.current_tok.type == TT_IDENTIFIER:
			var_name_tok = self.current_tok
			self.advance(res)
			if not self.current_tok.matches(TT_KEYWORD, 'usando'):
				return res.failure(InvalidSyntaxError(
					self.current_tok.pos_start, self.current_tok.pos_end,
					"Esperava-se 'usando'"
				))
			self.advance(res)
			if self.current_tok.type != TT_LPAREN:
				return res.failure(InvalidSyntaxError(
					self.current_tok.pos_start, self.current_tok.pos_end,
					"Esperava-se '('"
				))
		else:
			var_name_tok = None
			if self.current_tok.type != TT_LPAREN:
				return res.failure(InvalidSyntaxError(
					self.current_tok.pos_start, self.current_tok.pos_end,
					"Esperava-se '('"
				))
		
		self.advance(res)
		arg_name_toks = []
		arg_types = []
		default_value_pairs = []

		if self.current_tok.type == TT_IDENTIFIER:
			tok = self.current_tok
			arg_name_toks.append(self.current_tok)
			self.advance(res)

			arg_types.append(None)
			if self.current_tok.type == TT_COLON:
				self.advance(res)
				arg_types[-1] = res.register(self.type_expr())
				if res.error: return res

			if self.current_tok.type == TT_EQ:
					self.advance(res)
					default_value_pairs.append((tok.value, res.register(self.expr())))
					if res.error: return res
			else:
				default_value_pairs.append((None, None))

			while self.current_tok.type == TT_COMMA:
				self.advance(res)
				if not self.current_tok.type == TT_IDENTIFIER:
					return res.failure(InvalidSyntaxError(
						self.current_tok.pos_start, self.current_tok.pos_end,
						'Esperava-se um identificador'
					))
				
				arg_name_toks.append(self.current_tok)
				tok = self.current_tok
				self.advance(res)

				arg_types.append(None)
				if self.current_tok.type == TT_COLON:
					self.advance(res)
					arg_types[-1] = res.register(self.type_expr())
					if res.error: return res

				if self.current_tok.type == TT_EQ:
					self.advance(res)
					default_value_pairs.append((tok.value, res.register(self.expr())))
					if res.error: return res
				else:
					default_value_pairs.append((None, None))


			if self.current_tok.type != TT_RPAREN:
				return res.failure(InvalidSyntaxError(
					self.current_tok.pos_start, self.current_tok.pos_end,
					"Esperava-se ',' ou ')'"
				))
		
		else:
			if self.current_tok.type != TT_RPAREN:
				return res.failure(InvalidSyntaxError(
					self.current_tok.pos_start, self.current_tok.pos_end,
					"Esperava-se ')'"
				))
		
		self.advance(res)

		return_type = None
		if self.current_tok.type == TT_RARROW:
			self.advance(res)
			return_type = res.register(self.type_expr())
			if res.error: return res

		if self.current_tok.type == TT_ARROW:
			self.advance(res)
			node_to_return = res.register(self.expr())
			if res.error: return res

			return res.success(FuncDefNode(var_name_tok, arg_name_toks, node_to_return, True, 
		is_private, default_vals=default_value_pairs, arg_types=arg_types, return_type=return_type))
		
		elif self.current_tok.type != TT_NEWLINE:
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				f"Esperava-se '=>' ou NOVA_LINHA"
			))

		res.register_advancement()
		self.advance()

		while self.current_tok.type == TT_NEWLINE:
			self.advance(res)
		if self.current_tok.matches(TT_KEYWORD, 'fim'):  # corpo vazio
			body = ListNode([], self.current_tok.pos_start.copy(), self.current_tok.pos_start.copy())
		else:
			body = res.register(self.statements())
			if res.error: return res

		if not self.current_tok.matches(TT_KEYWORD, 'fim'):
			what = f"a função '{var_name_tok.value}'" if var_name_tok else "a função"
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				f"Esperava-se 'fim' para fechar {what} (aberta na linha {(var_name_tok or self.current_tok).pos_start.ln + 1})"
			))

		res.register_advancement()
		self.advance()

		
		return res.success(FuncDefNode(
		var_name_tok,
		arg_name_toks,
		body,
		False,
		is_private,
		default_vals=default_value_pairs,
		arg_types=arg_types,
		return_type=return_type
		))

	def for_expr(self):
		res = ParseResult()
		
		if not self.current_tok.matches(TT_KEYWORD, 'caminhando'):
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				f"Esperava-se 'caminhando'"
			))

		res.register_advancement()
		self.advance()

		if self.current_tok.type != TT_IDENTIFIER:
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				"Esperava-se um identificador para a variável do loop"
			))

		var_name_tok = self.current_tok
		res.register_advancement()
		self.advance()

		if not self.current_tok.type in (TT_EQ, TT_ARROW) and not self.current_tok.matches(TT_KEYWORD, 'de'):
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				"Esperava-se '=', '=>' ou 'de' após o identificador"
			))

		res.register_advancement()
		self.advance()

		start_value = res.register(self.expr())
		if res.error: return res

		if not self.current_tok.matches(TT_KEYWORD, 'até'):
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				"Esperava-se 'até'"
			))

		res.register_advancement()
		self.advance()

		end_value = res.register(self.expr())
		if res.error: return res

		step_value = None
		if self.current_tok.matches(TT_KEYWORD, 'mudando'):
			res.register_advancement()
			self.advance()
			step_value = res.register(self.expr())
			if res.error: return res

		if not self.current_tok.matches(TT_KEYWORD, 'faça'):
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				"Esperava-se 'faça'"
			))

		res.register_advancement()
		self.advance()

		if self.current_tok.type == TT_NEWLINE:
			res.register_advancement()
			self.advance()

			body = res.register(self.statements())
			if res.error: return res

			if not self.current_tok.matches(TT_KEYWORD, 'fim'):
				return res.failure(InvalidSyntaxError(
					self.current_tok.pos_start, self.current_tok.pos_end,
					"Esperava-se 'fim' para fechar o bloco 'caminhando'"
				))

			res.register_advancement()
			self.advance()
			return res.success(ForNode(var_name_tok, start_value, end_value, step_value, body, True))
		else:
			body = res.register(self.statement())
			if res.error: return res
			return res.success(ForNode(var_name_tok, start_value, end_value, step_value, body, False))
	
	def for_each_expr(self):
		res = ParseResult()
		
		if not self.current_tok.matches(TT_KEYWORD, 'para'):
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				f"Esperava-se 'para'"
			))

		self.advance()
		res.register_advancement()

		if not self.current_tok.matches(TT_KEYWORD, 'cada'):
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				f"Esperava-se 'cada' após 'para'"
			))

		res.register_advancement()
		self.advance()

		if self.current_tok.type == TT_IDENTIFIER and self.peek().type == TT_COLON:
			# dict compreehension
			pass

		if self.current_tok.type != TT_IDENTIFIER:
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				"Esperava-se identificador para variável de iteração"
			))

		var_name_tok = [self.current_tok]
		res.register_advancement()
		self.advance()

		while self.current_tok.type == TT_COMMA:
			res.register_advancement()
			self.advance()

			if self.current_tok.type != TT_IDENTIFIER:
				return res.failure(InvalidSyntaxError(
					self.current_tok.pos_start, self.current_tok.pos_end,
					"Esperava-se identificador para variável de iteração após ','"
				))

			var_name_tok.append(self.current_tok)
			res.register_advancement()
			self.advance()

		if not self.current_tok.matches(TT_KEYWORD, 'em'):
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				f"Esperava-se 'em' após identificador"
			))

		res.register_advancement()
		self.advance()

		iterable_node = res.register(self.expr())
		if res.error: return res

		if not self.current_tok.matches(TT_KEYWORD, 'faça'):
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				f"Esperava-se 'faça'"
			))

		res.register_advancement()
		self.advance()

		if self.current_tok.type == TT_NEWLINE:
			res.register_advancement()
			self.advance()

			body_node = res.register(self.statements())
			if res.error: return res

			if not self.current_tok.matches(TT_KEYWORD, 'fim'):
				return res.failure(InvalidSyntaxError(
					self.current_tok.pos_start, self.current_tok.pos_end,
					f"Esperava-se 'fim'"
				))

			res.register_advancement()
			self.advance()
			return res.success(ForEachNode(var_name_tok, iterable_node, body_node, True))
		else:
			body_node = res.register(self.statement())
			if res.error: return res
			return res.success(ForEachNode(var_name_tok, iterable_node, body_node, False))

	def while_expr(self):
		res = ParseResult()
		if not self.current_tok.matches(TT_KEYWORD, 'enquanto'):
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start.copy(), self.current_tok.pos_end.copy(),
				'Esperava-se "enquanto"'
			))

		self.advance(res)
		condition = res.register(self.expr())
		if res.error: return res

		if not self.current_tok.matches(TT_KEYWORD, 'faça'):
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start.copy(), self.current_tok.pos_end.copy(),
				'Esperava-se "faça"'
			))

		res.register_advancement()
		self.advance()

		if self.current_tok.type == TT_NEWLINE:
			res.register_advancement()
			self.advance()

			body = res.register(self.statements())
			if res.error: return res

			if not self.current_tok.matches(TT_KEYWORD, 'fim'):
				return res.failure(InvalidSyntaxError(
					self.current_tok.pos_start, self.current_tok.pos_end,
					"Esperava-se 'fim'"
				))

			res.register_advancement()
			self.advance()

			return res.success(WhileNode(condition, body, True))
		else:
			body = res.register(self.statement())
			if res.error: return res
			return res.success(WhileNode(condition, body, False))


	def power(self):
		return self.bin_op(self.call, (TT_POW, ), self.factor)
	
	def call(self):
		res = ParseResult()
		node = res.register(self.atom())
		if res.error: return res

		while True:
			if self.current_tok.type == TT_LPAREN:
				res.register_advancement()
				self.advance()
				arg_nodes = []

				if self.current_tok.type == TT_RPAREN:
					res.register_advancement()
					self.advance()
				else:
					self.skip_newline(res)
					arg_nodes.append(res.register(self.expr()))
					if res.error: return res

					while self.current_tok.type == TT_COMMA:
						res.register_advancement()
						self.advance()
						self.skip_newline(res)

						arg_nodes.append(res.register(self.expr()))
						if res.error: return res
					
					self.skip_newline(res)

					if self.current_tok.type != TT_RPAREN:
						return res.failure(InvalidSyntaxError(
							self.current_tok.pos_start, self.current_tok.pos_end,
							"Esperava-se ')' ou ','"
						))
					res.register_advancement()
					self.advance()
				node = CallNode(node, arg_nodes)
			elif self.current_tok.type == TT_DOT:
				res.register_advancement()
				self.advance()

				if self.current_tok.type != TT_IDENTIFIER:
					return res.failure(InvalidSyntaxError(
						self.current_tok.pos_start, self.current_tok.pos_end,
						"Esperava-se um identificador"
					))

				attr_name = self.current_tok
				res.register_advancement()
				self.advance()
				node = AttrAccessNode(node, attr_name)
			elif self.current_tok.type == TT_LBRACKET:
				# array sla
				res.register_advancement()
				self.advance()

				index_expr = res.register(self.expr())
				if res.error: return res

				if self.current_tok.type != TT_RBRACKET:
					return res.failure(InvalidSyntaxError(
						self.current_tok.pos_start, self.current_tok.pos_end,
						"Esperava-se ']'"
					))

				res.register_advancement()
				self.advance()
				node = ArrayAccessNode(node, index_expr)
			else:
				break
		
		if self.current_tok.type == TT_EQ:
			res.register_advancement()
			self.advance()
			expr = res.register(self.expr())
			if res.error: return res
			if isinstance(node, AttrAccessNode):
				node = AttrAssignNode(node.obj_node, node.attr_name_tok, expr)
			elif isinstance(node, ArrayAccessNode):
				node = ArrayAssignNode(node.obj_node, node.index_node, expr)

		return res.success(node)

	def factor(self):
		res = ParseResult()
		tok = self.current_tok

		if tok.type in (TT_PLUS, TT_MINUS):
			res.register_advancement()
			self.advance()
			factor = res.register(self.factor())
			if res.error: return res
			return res.success(UnaryOpNode(tok, factor))

		return self.power()

	def term(self):
		return self.bin_op(self.factor, (TT_MUL, TT_DIV, TT_PERCENT))

	def comp_expr(self):
		res = ParseResult()

		if self.current_tok.matches(TT_KEYWORD, 'não'):
			op_tok = self.current_tok
			self.advance(res)

			node = res.register(self.comp_expr())
			if res.error: return res
			return res.success(UnaryOpNode(op_tok, node))
		
		node = res.register(self.bin_op(self.arith_expr, (TT_EE, TT_NE, TT_GT, TT_GTE, TT_LT, TT_LTE, (TT_KEYWORD, 'igual'), (TT_KEYWORD, 'em'))))
		if res.error:
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				"Syntaxe Inválida, esperava-se 'não', '==', '!=', '<', '<=', '>', '>='..."
			))

		return res.success(node)
	
	def arith_expr(self):
		return self.bin_op(self.term, (TT_PLUS, TT_MINUS))

	def expr(self):
		res = ParseResult()
		constant = False
		is_private = False

		var_name_toks = []
		type_ = None

		if self.current_tok.matches(TT_KEYWORD, 'declarar'):
			res.register_advancement()
			self.advance()

			if self.current_tok.matches(TT_KEYWORD, 'constante'):
				res.register_advancement()
				self.advance()
				constant = True

			if self.current_tok.matches(TT_KEYWORD, 'privada'):
				self.advance(res)
				is_private = True

			if self.current_tok.type != TT_IDENTIFIER:
				return res.failure(InvalidSyntaxError(
					self.current_tok.pos_start, self.current_tok.pos_end,
					"Esperava-se um identificador"
				))

			var_name = self.current_tok
			res.register_advancement()
			self.advance()

			var_name_toks.append(var_name)

			while self.current_tok.type == TT_COMMA:
				res.register_advancement()
				self.advance()

				if self.current_tok.type != TT_IDENTIFIER:
					return res.failure(InvalidSyntaxError(
						self.current_tok.pos_start, self.current_tok.pos_end,
						"Esperava-se um identificador"
					))

				var_name = self.current_tok
				var_name_toks.append(var_name)
				res.register_advancement()
				self.advance()
			
			if self.current_tok.type == TT_COLON:
				self.advance(res)
				type_ = res.register(self.type_expr())
				if res.error: return res

			if self.current_tok.type == TT_NEWLINE:
				return res.success(VarAssignNode(var_name, None, constant=constant, private=is_private, type_=type_))
			elif not (self.current_tok.matches(TT_KEYWORD, 'como') or self.current_tok.type in (TT_EQ, TT_ARROW)):
				return res.failure(InvalidSyntaxError(
					self.current_tok.pos_start, self.current_tok.pos_end,
					"Esperava-se '=' ou '=>' ou ';'",
				))

			res.register_advancement()
			self.advance()
			expr = res.register(self.expr())
			if res.error: return res
			return res.success(VarAssignNode(var_name_toks, expr, constant=constant, private=is_private, type_=type_))

		node = res.register(self.bin_op(self.comp_expr, ((TT_KEYWORD, 'e'), (TT_KEYWORD, 'ou'))))

		if res.error:
			return res.failure(InvalidSyntaxError(
				self.current_tok.pos_start, self.current_tok.pos_end,
				'Syntaxe Inválida'
			))

		return res.success(node)

	###################################

	def bin_op(self, func_a, ops, func_b=None):
		if func_b == None:
			func_b = func_a
		
		res = ParseResult()
		if res.error: return res

		left = res.register(func_a())
		if res.error: return res

		while self.current_tok.type in ops or (self.current_tok.type, self.current_tok.value) in ops:
			op_tok = self.current_tok
			res.register_advancement()
			self.advance()
			right = res.register(func_b())
				
			left = BinOpNode(left, op_tok, right)

		return res.success(left)
