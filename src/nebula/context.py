"""Resultado de execução, contexto e tabela de símbolos (escopos)."""

import difflib


class RTResult:
	def __init__(self):
		self.reset()
	def reset(self):
		self.value = None
		self.error = None
		self.func_return_value = None
		self.loop_should_continue = False
		self.loop_should_break = False

	def register(self, res):
		self.func_return_value = res.func_return_value
		self.loop_should_break = res.loop_should_break
		self.loop_should_continue = res.loop_should_continue
		
		if res.error: self.error = res.error
		return res.value

	def success(self, value):
		self.reset()
		self.value = value
		return self

	def success_return(self, value):
		self.reset()
		self.func_return_value = value
		return self
	
	def success_continue(self):
		self.reset()
		self.loop_should_continue = True
		return self
	
	def success_break(self):
		self.reset()
		self.loop_should_break = True
		return self
	
	def should_return(self):
		return (
			self.error or
			self.func_return_value or
			self.loop_should_break or
			self.loop_should_continue
		)

	def failure(self, error):
		self.reset()
		self.error = error
		return self


class Context:
	def __init__(self, display_name, parent=None, parent_entry_pos=None):
		self.display_name = display_name
		self.parent = parent
		self.parent_entry_pos = parent_entry_pos
		self.symbol_table = None
		self.self_obj = None          # instância em que o método está rodando (None fora de métodos)
		self.defining_class = None    # classe onde o método em execução foi definido (usada por `super`)


class SymbolTable:
	def __init__(self, parent=None, child=None):
		self.symbols = {}
		self.constants = []
		self.privates = []
		self.types = []
		self.parent = parent
		
	def get(self, name):
		value = self.symbols.get(name, None)
		if value is None and self.parent:
			value = self.parent.get(name)
		return value

	def set(self, name, value, constant=False, private=False, type_=None):
		if name in self.constants:
			return 'error'
		if self.parent and name in self.parent.constants \
				and not getattr(self.parent.symbols.get(name), 'executable', False):
			return 'error'  # constantes de fora são protegidas; funções nativas (falar, str...) podem ser sombreadas
		
		self.symbols[name] = value
		if private: self.privates.append(name)
		if constant: self.constants.append(name)
		if type_:
			self.types = [t for t in self.types if t[0] != name]
			self.types.append((name, type_))
	
	def get_type(self, name):
		"""Tipo declarado (TypeNode) da variável, procurando nos escopos de fora. None se não tem."""
		for var_name, type_node in self.types:
			if var_name == name:
				return type_node
		if self.parent:
			return self.parent.get_type(name)
		return None
	
	def is_constant(self, name):
		val = name in self.constants or None
		if self.parent: val = val or self.parent.is_constant(name)
		return val

	def is_private(self, name):
		val = None
		if name in self.privates: return True
		if self.parent: val = val or self.parent.is_private(name)
		return val
	
	def copy(self):
		copy = SymbolTable()
		copy.symbols = self.symbols.copy()
		copy.parent = self.parent
		copy.constants = self.constants.copy()
		copy.properties = self.properties
		return copy

	def remove(self, name):
		del self.symbols[name]


global_symbol_table = SymbolTable()


def all_symbol_names(table):
	names = set()
	while table:
		names.update(table.symbols.keys())
		table = table.parent
	return names


def suggest_name(name, table):
	if table is None: return None
	matches = difflib.get_close_matches(name, all_symbol_names(table), n=1, cutoff=0.6)
	return matches[0] if matches else None
