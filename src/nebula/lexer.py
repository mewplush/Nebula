"""Análise léxica: texto -> tokens."""

from .config import DIGITS_DOT_SET, DIGITS_SET, LETTERS_DIGITS_SET, LETTERS_SET
from .errors import IllegalCharError
from .position import Position
from .tokens import (
	KEYWORDS,
	TT_ARROW,
	TT_RARROW,
	TT_AT,
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
	TT_RBRACE,
	TT_RBRACKET,
	TT_RPAREN,
	TT_SEMICOLON,
	TT_STRING,
	Token,
)


class Lexer:
	def __init__(self, fn, text):
		self.fn = fn
		self.text = text
		self.pos = Position(-1, 0, -1, fn, text)
		self.current_char = None
		self.advance()
	
	def advance(self):
		self.pos.advance(self.current_char)
		self.current_char = self.text[self.pos.idx] if self.pos.idx < len(self.text) else None
	
	def peek(self):
		peek_pos = self.pos.idx + 1
		return self.text[peek_pos] if peek_pos < len(self.text) else None


	def make_tokens(self):
		tokens = []

		# @type self.current_char: char | Literal['#', '%', '+', '@', '-', '*', ';', '/', '^', '=', '(', ')', '"', '!', '.', '<', '>', ',', '[', ']', '{', '}', ':']

		while self.current_char != None:
			if self.current_char in ' \t\r\ufeff':  # \r (arquivos CRLF do Windows) e BOM são só espaço em branco
				self.advance()
			elif self.current_char in ';\n':
				tokens.append(Token(TT_NEWLINE, pos_start=self.pos))
				self.advance()
			elif self.current_char == '#':
				self.skip_comment()
			elif self.current_char in DIGITS_SET:
				tokens.append(self.make_number())
			elif self.current_char in LETTERS_SET:
				tokens.append(self.make_identifier())
			elif self.current_char == '%':
				tokens.append(Token(TT_PERCENT, pos_start=self.pos))
				self.advance()
			elif self.current_char == '+':
				pos_start = self.pos.copy()
				self.advance()
				if self.current_char == '=':
					tokens.append(Token(TT_PE, pos_start=pos_start, pos_end=self.pos))
					self.advance()
				else:
					tokens.append(Token(TT_PLUS, pos_start=pos_start, pos_end=self.pos))
			elif self.current_char == '@':
				tokens.append(Token(TT_AT, pos_start=self.pos))
				self.advance()
			elif self.current_char == '-':
				pos_start = self.pos.copy()
				self.advance()
				if self.current_char == '=':
					tokens.append(Token(TT_ME, pos_start=pos_start, pos_end=self.pos))
					self.advance()
				elif self.current_char == '>':
					self.advance()
					tokens.append(Token(TT_RARROW, pos_start=pos_start, pos_end=self.pos))
				else:
					tokens.append(Token(TT_MINUS, pos_start=pos_start, pos_end=self.pos))
			elif self.current_char == '*':
				tokens.append(Token(TT_MUL, pos_start=self.pos))
				self.advance()
			elif self.current_char == ';':
				tokens.append(Token(TT_SEMICOLON, pos_start=self.pos))
				self.advance()
			elif self.current_char == '/':
				tokens.append(Token(TT_DIV, pos_start=self.pos))
				self.advance()
			elif self.current_char == '^':
				tokens.append(Token(TT_POW, pos_start=self.pos))
				self.advance()
			elif self.current_char == '=':
				tokens.append(self.make_equals())
			elif self.current_char == '(':
				tokens.append(Token(TT_LPAREN, pos_start=self.pos))
				self.advance()
			elif self.current_char == ')':
				tokens.append(Token(TT_RPAREN, pos_start=self.pos))
				self.advance()
			elif self.current_char == '"':
				tokens.append(self.make_string())
			elif self.current_char == '!':
				tok, error = self.make_not_equals()
				if error: return [], error
				tokens.append(tok)
			elif self.current_char == '.':
				tokens.append(Token(TT_DOT, pos_start=self.pos))
				self.advance()
			elif self.current_char == '<':
				tokens.append(self.make_less_than())
			elif self.current_char == '>':
				tokens.append(self.make_greater_than())
			elif self.current_char == ',':
				tokens.append(Token(TT_COMMA, pos_start=self.pos))
				self.advance()
			elif self.current_char == '[':
				tokens.append(Token(TT_LBRACKET, pos_start=self.pos))
				self.advance()
			elif self.current_char == ']':
				tokens.append(Token(TT_RBRACKET, pos_start=self.pos))
				self.advance()
			elif self.current_char == '{':
				tokens.append(Token(TT_LBRACE, pos_start=self.pos))
				self.advance()
			elif self.current_char == '}':
				tokens.append(Token(TT_RBRACE, pos_start=self.pos))
				self.advance()
			elif self.current_char == ':':
				tokens.append(Token(TT_COLON, pos_start=self.pos))
				self.advance()
			else:
				pos_start = self.pos.copy()
				char = self.current_char
				self.advance()
				return [], IllegalCharError(pos_start, self.pos, "'" + char + "'")

		tokens.append(Token(TT_EOF, pos_start=self.pos))
		return tokens, None

	def make_number(self):
		num_str = ''
		dot_count = 0
		pos_start = self.pos.copy()

		while self.current_char != None and self.current_char in DIGITS_DOT_SET:
			if self.current_char == '.':
				if dot_count == 1: break
				dot_count += 1
			num_str += self.current_char
			self.advance()

		if dot_count == 0:
			return Token(TT_INT, int(num_str), pos_start, self.pos)
		else:
			return Token(TT_FLOAT, float(num_str), pos_start, self.pos)

	def make_identifier(self):
		id_str = ''
		pos_start = self.pos.copy()

		while self.current_char != None and self.current_char in LETTERS_DIGITS_SET:
			id_str += self.current_char
			self.advance()

		tok_type = TT_KEYWORD if id_str in KEYWORDS else TT_IDENTIFIER
		return Token(tok_type, id_str, pos_start, self.pos)
	
	def make_not_equals(self):
		pos_start = self.pos.copy()
		self.advance()

		if self.current_char == '=':
			self.advance()
			return Token(TT_NE, pos_start=pos_start, pos_end=self.pos), None
		else:
			self.pos = pos_start
			return None, IllegalCharError(pos_start, self.pos, "Esperava-se '=' depois de '!'")
	
	def skip_comment(self):
		self.advance()

		while self.current_char != '\n' and self.current_char:
			self.advance()

	def make_equals(self):
		pos_start = self.pos.copy()
		self.advance()

		if self.current_char == '=':
			self.advance()
			return Token(TT_EE, pos_start=pos_start, pos_end=self.pos)
		elif self.current_char == '>':
			self.advance()
			return Token(TT_ARROW, pos_start=pos_start, pos_end=self.pos)
		else:
			return Token(TT_EQ, pos_start=pos_start, pos_end=self.pos)

	def make_less_than(self):
		pos_start = self.pos.copy()
		self.advance()

		if self.current_char == '=':
			self.advance()
			return Token(TT_LTE, pos_start=pos_start, pos_end=self.pos)
		else:
			return Token(TT_LT, pos_start=pos_start, pos_end=self.pos)
	
	def make_greater_than(self):
		pos_start = self.pos.copy()
		self.advance()

		if self.current_char == '=':
			self.advance()
			return Token(TT_GTE, pos_start=pos_start, pos_end=self.pos)
		else:
			return Token(TT_GT, pos_start=pos_start, pos_end=self.pos)
	
	def make_string(self):
		string_parts = []
		full_string = ""
		pos_start = self.pos.copy()
		self.advance()
		current_text = ""
		escape_char = False
		escape_characters = {
			'n': '\n', 't': '\t', 'r': '\r', 'b': '\b', 'f': '\f',
			'"': '"', '\\': '\\', '$': '$'
		}
		
		while self.current_char is not None and (self.current_char != '"' or escape_char):
			full_string += self.current_char
			if escape_char:
				current_text += escape_characters.get(self.current_char, self.current_char)
				escape_char = False
				self.advance()
			elif self.current_char == "\\":
				escape_char = True
				self.advance()
			elif self.current_char == "$" and self.peek() == "{":
				if current_text:
					string_parts.append(('TEXT', current_text))
					current_text = ""
				
				self.advance()
				self.advance()
				
				expr_tokens = []
				while self.current_char is not None and self.current_char != "}":
					full_string += self.current_char
					expr_tokens.append(self.current_char)
					self.advance()
				
				if self.current_char != "}":
					return None, IllegalCharError(pos_start, self.pos, "Expressão não fechada com }")
				
				self.advance()
				
				expr_lexer = Lexer(f"<fstring>", "".join(expr_tokens))
				tokens, error = expr_lexer.make_tokens()
				if error: return None, error
				
				string_parts.append(('EXPR', tokens))
			else:
				current_text += self.current_char
				self.advance()
		
		if current_text:
			string_parts.append(('TEXT', current_text))
		
		if self.current_char != '"':
			return None, IllegalCharError(pos_start, self.pos, "String não fechada")
		
		self.advance()
		return Token(TT_STRING, ''.join(full_string), pos_start, self.pos, parts=(string_parts, full_string))
