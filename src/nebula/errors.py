"""Classes de erro (léxico, sintaxe, execução)."""

from .string_with_arrows import string_with_arrows


class Error:
	def __init__(self, pos_start, pos_end, error_name, details):
		self.pos_start = pos_start
		self.pos_end = pos_end
		self.error_name = error_name
		self.details = details
	
	def as_string(self):
		result  = f'{self.error_name}: {self.details}\n'
		if self.pos_start:
			result += f'Arquivo {self.pos_start.fn}, linha {self.pos_start.ln + 1}'
		result += '\n\n' + string_with_arrows(self.pos_start.ftxt if self.pos_start else None, self.pos_start, self.pos_end)
		return result


class IllegalCharError(Error):
	def __init__(self, pos_start, pos_end, details):
		super().__init__(pos_start, pos_end, 'Caractere Ilegal', details)


class InvalidSyntaxError(Error):
	def __init__(self, pos_start, pos_end, details=''):
		super().__init__(pos_start, pos_end, 'Syntaxe Inválida', details)


class CheckError(Error):
	def __init__(self, pos_start, pos_end, details):
		super().__init__(pos_start, pos_end, 'Erro Conferindo Informações', details)


class RTError(Error):
	def __init__(self, pos_start, pos_end, details, context, name=None):
		super().__init__(pos_start, pos_end, name or 'Runtime Error', details)
		self.context = context

	def as_string(self):
		result  = self.generate_traceback()
		result += f'{self.error_name}: {self.details}'
		result += '\n\n' + string_with_arrows(self.pos_start.ftxt if self.pos_start else None, self.pos_start, self.pos_end)
		return result + "\n"

	def generate_traceback(self):
		result = ''
		pos = self.pos_start
		ctx = self.context

		while ctx and pos:
			result = f'  Arquivo {pos.fn}, linha {str(pos.ln + 1)}, em {ctx.display_name}\n' + result
			pos = ctx.parent_entry_pos
			ctx = ctx.parent

		return '\nErro Encontrado (Chamada mais recente):\n' + result + ""


class ValorError(RTError):
	def __init__(self, pos_start, pos_end, details, context):
		super().__init__(pos_start, pos_end, details, context, 'Erro de Valor')
