"""Tipos de token e palavras-chave."""


TT_INT			= 'INT'


TT_STRING		= 'STRING'


TT_FLOAT    	= 'FLOAT'


TT_IDENTIFIER	= 'IDENTIFIER'


TT_KEYWORD		= 'KEYWORD'


TT_PLUS     	= 'PLUS'


TT_MINUS    	= 'MINUS'


TT_MUL      	= 'MUL'


TT_DIV      	= 'DIV'


TT_POW			= 'POW'


TT_EQ			= 'EQ'


TT_LPAREN   	= 'LPAREN'


TT_RPAREN   	= 'RPAREN'


TT_EOF			= 'EOF'


TT_GTE = 'GTE'


TT_GT = 'GT'


TT_LTE = 'LTE'


TT_LT = 'LT'


TT_NE = 'NE'


TT_EE = 'EE'


TT_ARROW = 'ARROW'


TT_SEMICOLON = 'SEMICOLON'


TT_COMMA = 'COMMA'


TT_QUOTE = 'QUOTE'


TT_SQUOTE = 'SQUOTE'


TT_LBRACKET = 'LBRACKET'


TT_RBRACKET = 'RBRACKET'


TT_NEWLINE = 'NEWLINE'


TT_COLON = 'COLON'


TT_LBRACE = 'LBRACE'


TT_RBRACE = 'RBRACE'


TT_AT = 'AT'


TT_DOT = 'DOT'


TT_FTEXT = 'FTEXT'


TT_FEXPR = 'FEXPR'


TT_PE = 'PE'


TT_ME = 'ME'
TT_RARROW = 'RARROW'  # ->  (tipo de retorno)


TT_PERCENT = 'PERCENT'


KEYWORDS = [
	'declarar',
	'constante',
	'assim',
	'também',
	'como',
	'ou',
	'e',
	'função',
	'não',
	'se',
	'então',
	'senão',
	'classe',
	'mas',
	'enquanto',
	'caminhando',
	'até',
	'para',
	'cada',
	'mudando',
	'faça',
	'igual',
	'usando',
	'fim',
	'retornar',
	'continuar',
	'parar',
	'conferir',
	'levantar',
	'detalhes',
	'importar',
	'de',
	'verdadeiro',
	'falso',
	'em',
	'privada',
	'lista',
	'tupla',
	'mesa',
	'dicionário',
	'string',
	'número',
	'extende',
	'super',
	'tentar',
	'comparar',
	'caso'
]


class Token:
	def __init__(self, type_, value=None, pos_start=None, pos_end=None, parts=None):
		
		self.type = type_
		self.value = value
		self.parts = parts

		if pos_start:
			self.pos_start = pos_start.copy()
			self.pos_end = pos_start.copy()
			self.pos_end.advance()

		if pos_end:
			self.pos_end = pos_end.copy()

	def matches(self, type_, value):
		return self.type == type_ and self.value == value
	
	def __repr__(self):
		if self.value: return f'{self.type}:{self.value}'
		return f'{self.type}'
