"""Valores da linguagem (Número, String, Lista, Classe, Função...)."""

from typing import Literal, Optional

from .config import STATE
from .errors import RTError
from .context import Context, RTResult, SymbolTable, global_symbol_table


class Value:
	executable = False
	properties = {}

	def __init__(self):
		self.executable = False
		self.properties = {}
		self.set_pos()
		self.set_context()

	def set_pos(self, pos_start=None, pos_end=None):
		self.pos_start = pos_start
		self.pos_end = pos_end
		return self

	def set_context(self, context=None):
		self.context = context
		return self

	def added_to(self, other):
		return None, self.illegal_operation(other)

	def subbed_by(self, other):
		return None, self.illegal_operation(other)

	def multed_by(self, other):
		return None, self.illegal_operation(other)

	def dived_by(self, other):
		return None, self.illegal_operation(other)

	def powed_by(self, other):
		return None, self.illegal_operation(other)

	def mod_by(self, other):
		return None, self.illegal_operation(other)

	def get_comparison_eq(self, other):
		return None, self.illegal_operation(other)

	def get_comparison_ne(self, other):
		return None, self.illegal_operation(other)

	def get_comparison_lt(self, other):
		return None, self.illegal_operation(other)

	def get_comparison_gt(self, other):
		return None, self.illegal_operation(other)

	def get_comparison_lte(self, other):
		return None, self.illegal_operation(other)

	def get_comparison_gte(self, other):
		return None, self.illegal_operation(other)

	def anded_by(self, other):
		return Boolean(int(self.is_true() and other.is_true())).set_context(self.context), None

	def ored_by(self, other):
		return (self if self.is_true() else other).set_context(self.context), None

	def notted(self):
		return Boolean(int(0 if self.is_true() else 1)).set_context(self.context), None
	
	def included_in(self, other):
		return None, self.illegal_operation(other)

	def execute(self, args):
		return RTResult().failure(self.illegal_operation(exec_=True))

	def copy(self):
		raise Exception('Nenhum ".copy()" metódo encontrado -> relatar esse erro ao dev.')

	def is_true(self):
		return False

	def illegal_operation(self, other=None, exec_=None):
		if not other: other = self
		if not other.pos_end: other.pos_end = self.pos_end
		if exec_:
			return RTError(
				self.pos_start, other.pos_end,
				f'Operação ilegal, tentativa de execução de {self}',
				self.context
			)
		return RTError(
			self.pos_start, other.pos_end,
			f'Operação Ilegal entre {repr(self)} e {repr(other)}',
			self.context
		)


class Number(Value):

	def __init__(self, value):
		self.value = value
		self.set_pos()
		self.set_context()

	def set_pos(self, pos_start=None, pos_end=None):
		self.pos_start = pos_start
		self.pos_end = pos_end
		return self

	def set_context(self, context=None):
		self.context = context
		return self

	def added_to(self, other):
		if isinstance(other, Number):
			return Number(self.value + other.value).set_context(self.context), None
		return super().added_to(other)

	def subbed_by(self, other):
		if isinstance(other, Number):
			return Number(self.value - other.value).set_context(self.context), None
		return super().added_to(other)

	def multed_by(self, other):
		if isinstance(other, Number):
			return Number(self.value * other.value).set_context(self.context), None
		return super().added_to(other)

	def dived_by(self, other):
		if isinstance(other, Number):
			if other.value == 0:
				return None, RTError(
					other.pos_start, other.pos_end,
					f'Divisão por zero ({other}) não pode ser aceita',
					self.context
				)

			return Number(self.value / other.value).set_context(self.context), None
		return super().added_to(other)

	def powed_by(self, other):
		if isinstance(other, Number):
			return Number(self.value ** other.value).set_context(self.context), None
		return super().powed_by(other)

	def mod_by(self, other):
		if isinstance(other, Number):
			return Number(self.value % other.value).set_context(self.context), None
		return super().mod_by(other)

	def get_comparison_eq(self, other):
		if isinstance(other, Number):
			return Boolean(int(self.value == other.value)).set_context(self.context), None
		else:
			return Boolean(0).set_context(self.context), None
	
	def get_comparison_ne(self, other):
		if isinstance(other, Number):
			return Boolean(int(self.value != other.value)).set_context(self.context), None
		else:
			return Boolean(1).set_context(self.context), None
	
	def get_comparison_lt(self, other):
		if isinstance(other, Number):
			return Boolean(int(self.value < other.value)).set_context(self.context), None
		return super().get_comparison_gt(other)

	def get_comparison_lte(self, other):
		if isinstance(other, Number):
			return Boolean(int(self.value <= other.value)).set_context(self.context), None
		return super().get_comparison_gt(other)

	def get_comparison_gt(self, other):
		if isinstance(other, Number):
			return Boolean(int(self.value > other.value)).set_context(self.context), None
		return super().get_comparison_gt(other)
	
	def get_comparison_gte(self, other):
		if isinstance(other, Number):
			return Boolean(int(self.value >= other.value)).set_context(self.context), None
		return super().get_comparison_gt(other)

	def anded_by(self, other):
		return Boolean(int(self.is_true() and other.is_true())).set_context(self.context), None
	
	def ored_by(self, other):
		return (self if self.is_true() else other).set_context(self.context), None
	
	def notted(self):
		return Boolean(int(0 if self.is_true() else 1)).set_context(self.context), None
	
	def is_true(self):
		return (int(True if self.value > 0 else False))
	
	def included_in(self, other):
		if isinstance(other, (List, Set, Tuple)):
			for elem in other.elements:
				if isinstance(elem, Number) and elem.value == self.value:
					return Boolean(1).set_context(self.context), None
			return Boolean(0).set_context(self.context), None
		elif isinstance(other, String):
			return Boolean(int(str(self.value) in other.value)).set_context(self.context), None
		return Boolean(0).set_context(self.context), None
	
	def copy(self):
		copy = Number(self.value)
		copy.set_pos(self.pos_start, self.pos_end)
		copy.set_context(self.context)
		copy.properties = self.properties
		return copy
	
	def __repr__(self):
		return str(self.value)

	def __str__(self):
		return repr(self)


class Boolean(Value):
	def __init__(self, value: Literal["verdadeiro", "falso", 1, 0]):
		self.value = value

		if self.value == 1: self.value = 'verdadeiro'
		elif self.value == 0: self.value = 'falso'

		self.set_pos()
		self.set_context()
	
	def copy(self):
		copy = Boolean(self.value)
		copy.set_pos(self.pos_start, self.pos_end)
		copy.set_context(self.context)
		copy.properties = self.properties
		return copy

	def get_comparison_eq(self, other):
		return Boolean(int(self.is_true() == other.is_true())).set_context(self.context), None
	
	def get_comparison_ne(self, other):
		return Boolean(int(self.is_true() != other.is_true())).set_context(self.context), None
	
	def ored_by(self, other):
		return (self if self.is_true() else other).set_context(self.context), None
	
	def anded_by(self, other):
		return Boolean(int(self.is_true() and other.is_true())).set_context(self.context), None
	
	def notted(self):
		return Boolean(int(0 if self.is_true() else 1)).set_context(self.context), None

	def included_in(self, other):
		if isinstance(other, (List, Set, Tuple)):
			for elem in other.elements:
				if isinstance(elem, Boolean) and elem.value == self.value:
					return Boolean(1).set_context(self.context), None
			return Boolean(0).set_context(self.context), None
		elif isinstance(other, String):
			return Boolean(int(str(self.value).lower() in other.value.lower())).set_context(self.context), None
		return Boolean(0).set_context(self.context), None

	def is_true(self):
		return 1 if self.value == 'verdadeiro' else 0
	
	def __repr__(self):
		return str(self)
	
	def __str__(self):
		return str(self.value)


class Nulo(Value):
	def __init__(self):
		self.value = None
		super().__init__()
	
	def copy(self):
		copy = Nulo()
		copy.set_pos(self.pos_start, self.pos_end)
		copy.set_context(self.context)
		copy.properties = self.properties
		return copy
	
	def is_true(self):
		return False
	
	def get_comparison_eq(self, other):
		return Boolean(int(self.is_true() == other.is_true())).set_context(self.context), None
	
	def get_comparison_ne(self, other):
		return Boolean(int(self.is_true() != other.is_true())).set_context(self.context), None
	
	def ored_by(self, other):
		return (self if self.is_true() else other).set_context(self.context), None
	
	def anded_by(self, other):
		return Boolean(int(self.is_true() and other.is_true())).set_context(self.context), None
	
	def notted(self):
		return Boolean(int(0 if self.is_true() else 1)).set_context(self.context), None
	
	def included_in(self, other):

		if isinstance(other, (List, Set, Tuple)):
			for elem in other.elements:
				if isinstance(elem, Nulo):
					return Boolean(1).set_context(self.context), None
				
		return Boolean(0).set_context(self.context), None
	
	def __repr__(self):
		return "Nulo"
	
	def __str__(self):
		return "nulo"


class Set(Value):
	def __init__(self, elements):
		super().__init__()
		self.elements = elements
	
	def copy(self):
		copy = Set(self.elements)
		copy.set_context(self.context)
		copy.set_pos(self.pos_start, self.pos_end)
		copy.properties = self.properties
		return copy
	
	def is_true(self):
		return True
	
	def get_comparison_eq(self, other):
		return Boolean(int(self.elements == other.elements)).set_context(self.context).set_pos(self.pos_start, self.pos_end), None
	
	def get_comparison_ne(self, other):
		return Boolean(int(self.elements != other.elements)).set_context(self.context).set_pos(self.pos_start, self.pos_end), None
	
	def get_comparison_eq(self, other):
		return Boolean(int(self.elements == other.elements)).set_context(self.context).set_pos(self.pos_start, self.pos_end), None
	
	def anded_by(self, other):
		return Boolean(int(self.is_true() and other.is_true())).set_context(self.context).set_pos(self.pos_start, self.pos_end), None

	def ored_by(self, other):
		return (self if self.is_true() else other).set_context(self.context), None
	
	def notted(self):
		return Boolean(int(not self.is_true())).set_context(self.context).set_pos(self.pos_start, self.pos_end), None
	
	def included_in(self, other):
		if isinstance(other, (List, Set, Tuple)):
			for elem in other.elements:
				if isinstance(elem, Set) and [str(x) for x in elem.elements] == [str(x) for x in self.elements]:
					return Boolean(1).set_context(self.context), None
					
		return Boolean(0).set_context(self.context), None

	def __repr__(self):
		return f'Mesa({", ".join(self.elements)})'
	
	def __str__(self):
		reprs = f'{", ".join([str(x) for x in self.elements])}'
		return "{" + reprs + "}"


Number.true = Boolean(1)


Number.false = Boolean(0)


Number.null = Nulo()


class String(Value):
	def __init__(self, value):
		super().__init__()
		if isinstance(value, list):
			self.parts = value
			self.value = self._combine_parts()
		else:
			self.value = str(value)
			self.parts = [('TEXT', self.value)]

	def _combine_parts(self):
		combined = ""
		for part_type, part_value in self.parts:
			if part_type == 'TEXT':
				combined += part_value
			elif part_type == 'EXPR':
				combined += str(part_value)
		return combined
	
	def added_to(self, other):
		if isinstance(other, String):
			return String(self.value + str(other.value)).set_context(self.context), None
		elif isinstance(other, List):
			return String(self.value + ", ".join(str(x) for x in other.elements)).set_context(self.context), None
		elif isinstance(other, Number):
			return String(self.value + str(other.value)).set_context(self.context), None
		else:
			return String(self.value + repr(other)).set_context(self.context), None

	def multed_by(self, other):
		if isinstance(other, Number):
			return String(self.value * int(other.value)).set_context(self.context), None
		return None, self.illegal_operation(other)
	
	def notted(self):
		return Boolean(int(0 if self.is_true() else 1)).set_context(self.context), None
	
	def anded_by(self, other):
		return Boolean(int(self.is_true() and other.is_true())).set_context(self.context), None
	
	def ored_by(self, other):
		return (self if self.is_true() else other).set_context(self.context), None
	def get_comparison_eq(self, other):
		if isinstance(other, String):
			return Boolean(int(self.value == other.value)).set_context(self.context), None
		return Number.false, None
	
	def get_comparison_ne(self, other):
		if isinstance(other, String):
			return Boolean(int(self.value != other.value)).set_context(self.context), None
		return Number.true, None
		
	def copy(self):
		copy = String(self.value)
		copy.set_pos(self.pos_start, self.pos_end)
		copy.set_context(self.context)
		copy.properties = self.properties
		return copy

	def is_true(self):
		return len(self.value) > 0 and self.value
	
	def included_in(self, other):
		if isinstance(other, (List, Set, Tuple)):
			for elem in other.elements:
				if isinstance(elem, String) and elem.value == self.value:
					return Boolean(1).set_context(self.context), None
			return Boolean(0).set_context(self.context), None
		elif isinstance(other, String):
			return Boolean(int(self.value in other.value)).set_context(self.context), None
		return Boolean(0).set_context(self.context), None

	
	def __str__(self):
		return self.value
	
	def __repr__(self):
		return f'"{self.value}"'


class List(Value):
	def __init__(self, elements):
		super().__init__()
		self.elements = elements
	
	def added_to(self, other):
		new_list = self.copy()
		new_list.elements.append(other)
		return new_list, None
	
	def multed_by(self, other):
		if isinstance(other, List):
			new_list = self.copy()
			new_list.elements.extend(other.elements)
			return new_list, None
		return None, self.illegal_operation(other)
	
	def get_comparison_eq(self, other):
		if isinstance(other, List):
			return Boolean(int(self.elements == other.elements)).set_context(self.context), None
		return Number.false, None
	
	def get_comparison_ne(self, other):
		if isinstance(other, List):
			return Boolean(int(self.elements != other.elements)).set_context(self.context), None
		return Number.true, None
	
	def notted(self):
		return Boolean(int(0 if self.is_true() else 1)).set_context(self.context), None
	
	def anded_by(self, other):
		return Boolean(int(self.is_true() and other.is_true())).set_context(self.context), None
	
	def _ored_by(self, other):
		return Boolean(int(self.is_true() or other.is_true())).set_context(self.context), None
	
	def is_true(self):
		return len(self.elements) > 0
	
	def included_in(self, other):
		if isinstance(other, (List, Set, Tuple)):
			for elem in other.elements:
				if isinstance(elem, List) and [str(x) for x in elem.elements] == [str(x) for x in self.elements]:
					return Boolean(1).set_context(self.context), None
					
		return Boolean(0).set_context(self.context), None
	
	def copy(self):
		copy = List(self.elements)
		copy.set_pos(self.pos_start, self.pos_end)
		copy.set_context(self.context)
		copy.properties = self.properties
		return copy
	
	def __sstr__(self):
		return f'{", ".join([str(x) for x in self.elements])}'

	def __str__(self):
		return f'{", ".join([repr(x) for x in self.elements])}'
	
	def __repr__(self):
		return f'[{", ".join([repr(x) for x in self.elements])}]'


class Tuple(Value):
	def __init__(self, elements):
		super().__init__()
		self.elements = elements

	def added_to(self, other):
		if isinstance(other, Tuple):
			return Tuple(self.elements + other.elements), None
		return None, self.illegal_operation(other)

	def get_comparison_eq(self, other):
		if isinstance(other, Tuple):
			return Number(int(self.elements == other.elements)), None
		return Number.false, None
	
	def is_true(self):
		return len(self.elements) > 0
	
	def ored_by(self, other):
		return (self if self.is_true() else other).set_context(self.context), None
	
	def anded_by(self, other):
		return Boolean(int(self.is_true() and other.is_true())).set_context(self.context), None
	
	def notted(self):
		return Boolean(int(0 if self.is_true() else 1)).set_context(self.context), None
	
	def included_in(self, other):
		if isinstance(other, (List, Set, Tuple)):
			for elem in other.elements:
				if isinstance(elem, Tuple) and elem.elements == self.elements:
					return Boolean(1).set_context(self.context), None
		return Boolean(0).set_context(self.context), None

	def copy(self):
		new_tup = Tuple(self.elements)
		new_tup.set_pos(self.pos_start, self.pos_end)
		new_tup.set_context(self.context)
		new_tup.properties = self.properties
		return new_tup

	def __repr__(self):
		return f'({", ".join([str(e) for e in self.elements])})'


class Dict(Value):
	def __init__(self, elements: Optional[list]):
		super().__init__()
		self.elements = elements # [(k, v)...]
		
	def added_to(self, other):
		if isinstance(other, Dict):
			new_dict = self.copy()
			for key, value in other.elements:
				new_dict.elements.append((key.copy(), value.copy()))
			return new_dict, None
		return None, self.illegal_operation(other)
	
	def change_val(self, key, value):
		for i, (k, v) in enumerate(self.elements):
			if k.value == key.value:
				self.elements[i] = (k, value)
				return
	
	def copy(self):
		copy = Dict([(k, v.copy()) for k, v in self.elements])
		copy.set_pos(self.pos_start, self.pos_end)
		copy.set_context(self.context)
		copy.properties = self.properties
		return copy
	
	def __str__(self):
		pairs = [f"{str(k.value)}: {repr(v.copy())}" for k, v in self.elements]
		return ", ".join(pairs)
	
	def __repr__(self):
		return "{" + self.__str__() + "}"
	
	def keys(self):
		return List([String(k.value) if isinstance(k.value, str) else Number(k.value) for k, v in self.elements])
	
	def values(self):
		return List([v.copy() for k, v in self.elements])
	
	def items(self):
		return List([self.values(), self.keys()])
	
	def update(self, other):
		
		if isinstance(other, Dict):
			for key, value in other.elements:
				found = False
				for i, (k, v) in enumerate(self.elements):
					if k.value == key.value:
						self.elements[i] = (k, value)
						found = True
						break
				if not found:
					self.elements.append((key, value))
			return self
		return None, self.illegal_operation(other)


class BaseFunction(Value):
	def __init__(self, name):
		super().__init__()
		self.executable = True
		self.name = name or "<anônima>"
	
	def generate_new_context(self):
		new_context = Context(self.name, self.context, self.pos_start)
		new_context.symbol_table = SymbolTable(new_context.parent.symbol_table if new_context.parent else global_symbol_table)
		return new_context

	def check_args(self, arg_names, args):
		res = RTResult()

		if len(args) > len(arg_names):
			return res.failure(RTError(
				self.pos_start, self.pos_end,
				f"{len(args) - len(arg_names)} a mais de argumentos foram passados a função '{self.name}'",
				self.context
			))
		
		if len(args) < len(arg_names):
			return res.failure(RTError(
				self.pos_start, self.pos_end,
				f"{len(arg_names) - len(args)} a menos de argumentos foram passados a função '{self.name}'",
				self.context
			))
		
		return res.success(Number.null)
	
	def populate_args(self, arg_names, args, exec_ctx):
		for i in range(len(args)):
			arg_name = arg_names[i]
			arg_value = args[i]
			try:
				arg_value.set_context(exec_ctx)
			except Exception as e:
				pass
			exec_ctx.symbol_table.set(arg_name, arg_value)
	
	def check_and_populate_args(self, arg_names, args, exec_ctx):
		res = RTResult()
		res.register(self.check_args(arg_names, args))
		if res.should_return(): return res
		self.populate_args(arg_names, args, exec_ctx)
		return res.success(Number.null)
	
	def __repr__(self):
		return f"<função {self.name} em {STATE.filename}>"


class Class(BaseFunction):
	def __init__(self, name, parent=False):
		super().__init__(name)
		self.arg_names = []
		self.parent = parent
		self.symbol_table = SymbolTable(
			parent.symbol_table if parent else self.context.symbol_table if self.context else global_symbol_table
		)

	def execute(self, args):
		res = RTResult()
			
		instance = Instance(self).set_context(self.context).set_pos(self.pos_start, self.pos_end)
		instance.symbol_table = SymbolTable(self.symbol_table)
		instance.symbol_table.set("esse", instance) 
	
		constructor = self.find_member("principal")
		if isinstance(constructor, Function):
			bound = constructor.copy()
			bound.obj = instance
			res.register(bound.execute(args))
			if res.should_return(): return res
		
		return res.success(instance)

	def find_member(self, name):
		"""Procura um membro (método ou atributo de classe) nesta classe e depois nas superclasses."""
		cls = self
		while cls:
			value = cls.symbol_table.symbols.get(name)
			if value is not None:
				return value
			cls = cls.parent
		return None

	def inherits_from(self, other):
		"""True se esta classe é `other` ou descende dela (compara a tabela de símbolos, que as cópias compartilham)."""
		cls = self
		while cls:
			if cls.symbol_table is other.symbol_table:
				return True
			cls = cls.parent
		return False

	def is_subclass_of(self, other_name):
		cls = self
		while cls:
			if cls.name == other_name:
				return True
			cls = cls.parent
		return False

	def copy(self):
		copy = Class(self.name, self.parent)
		copy.definition_scope = getattr(self, 'definition_scope', None)
		copy.symbol_table = self.symbol_table
		copy.set_context(self.context)
		copy.set_pos(self.pos_start, self.pos_end)
		copy.properties = self.properties
		return copy

	def __str__(self):
		return f"<classe {self.name} em {STATE.filename}>"


class Instance(Value):
	def __init__(self, class_):
		super().__init__()
		self.class_ = class_
		self.symbol_table = SymbolTable(parent=class_.parent.symbol_table if class_.parent else class_.symbol_table)
		if not self.symbol_table.get('esse'): self.symbol_table.set('esse', self)
		if not self.context:
			self.context = Context(f"instance_of_{self.class_.name}", parent=self.class_.name)
		self.context.symbol_table = self.symbol_table
		self.obj = None
		self.type_name = class_.name 

	def get_member(self, name):
		"""Atributo da instância ou método/atributo de classe (método vem ligado a esta instância). None se não existe."""
		own = self.symbol_table.symbols
		if name in own:
			return own[name]
		member = self.class_.find_member(name)
		if isinstance(member, Function):
			bound = member.copy()
			bound.obj = self
			return bound
		return member

	def get(self, name):
		value = self.get_member(name)
		if value is not None:
			return value
		return Nulo().set_context(self.context).set_pos(self.pos_start, self.pos_end)

	def set(self, name, value, constant=False):
		self.symbol_table.set(name, value, constant)

	def copy(self):
		copy = Instance(self.class_)
		copy.symbol_table = self.symbol_table
		copy.set_context(self.context)
		copy.set_pos(self.pos_start, self.pos_end)
		copy.properties = self.properties
		return copy
	
	def execute(self, args):
		return self.class_.execute(args)
	
	def is_true(self):
		return True

	# Sobrecarga de operadores: defina métodos com esses nomes na sua classe Nebula.
	OPERATOR_METHODS = {
		'added_to': 'somar', 'subbed_by': 'subtrair', 'multed_by': 'multiplicar',
		'dived_by': 'dividir', 'mod_by': 'resto', 'powed_by': 'potência',
		'get_comparison_lt': 'menor_que', 'get_comparison_gt': 'maior_que',
		'get_comparison_lte': 'menor_ou_igual', 'get_comparison_gte': 'maior_ou_igual',
	}

	def _same_instance(self, other):
		# variáveis guardam cópias da instância; a identidade real é a tabela de símbolos compartilhada
		return isinstance(other, Instance) and self.symbol_table is other.symbol_table

	def _bound_method(self, name):
		method = self.get(name)
		if isinstance(method, Function):
			bound = method.copy()
			bound.obj = self
			return bound
		return None

	def _call_operator(self, python_name, other):
		method = self._bound_method(self.OPERATOR_METHODS[python_name])
		if method:
			res = method.execute([other])
			if res.error: return None, res.error
			value = res.value if res.value is not None else Number.null
			return value, None
		return None, self.illegal_operation(other)

	def added_to(self, other): return self._call_operator('added_to', other)
	def subbed_by(self, other): return self._call_operator('subbed_by', other)
	def multed_by(self, other): return self._call_operator('multed_by', other)
	def dived_by(self, other): return self._call_operator('dived_by', other)
	def mod_by(self, other): return self._call_operator('mod_by', other)
	def powed_by(self, other): return self._call_operator('powed_by', other)
	def get_comparison_lt(self, other): return self._call_operator('get_comparison_lt', other)
	def get_comparison_gt(self, other): return self._call_operator('get_comparison_gt', other)
	def get_comparison_lte(self, other): return self._call_operator('get_comparison_lte', other)
	def get_comparison_gte(self, other): return self._call_operator('get_comparison_gte', other)

	def get_comparison_eq(self, other):
		method = self._bound_method('igual_a')
		if method:
			res = method.execute([other])
			if res.error: return None, res.error
			return (res.value if res.value is not None else Number.null), None
		return Boolean(int(self._same_instance(other))).set_context(self.context).set_pos(self.pos_start, self.pos_end), None
	
	def get_comparison_ne(self, other):
		method = self._bound_method('igual_a')
		if method:
			res = method.execute([other])
			if res.error: return None, res.error
			value = res.value if res.value is not None else Number.null
			return Boolean(int(not value.is_true())).set_context(self.context).set_pos(self.pos_start, self.pos_end), None
		return Boolean(int(not self._same_instance(other))).set_context(self.context).set_pos(self.pos_start, self.pos_end), None

	def __repr__(self):
		return f"<instância de {self.class_.name}>"
	
	def __str__(self):
		# Se a classe define o método `texto`, ele decide como a instância vira string (como o __str__ do Python).
		method = self._bound_method('texto')
		if method:
			res = method.execute([])
			if not res.error and res.value is not None:
				return str(res.value)
		return f"<instância de {self.class_.name} em {STATE.filename}>"


class SuperRef(Value):
	"""Resultado de `super`: enxerga os métodos da superclasse, já ligados à instância atual."""
	def __init__(self, instance, parent):
		super().__init__()
		self.instance = instance
		self.parent = parent
		self.executable = True

	def get(self, name):
		member = self.parent.find_member(name)
		if isinstance(member, Function):
			bound = member.copy()
			bound.obj = self.instance
			return bound
		return member

	def execute(self, args):
		# super(args) == chamar o construtor (`principal`) da superclasse
		constructor = self.get('principal')
		if constructor is None:
			return RTResult().success(Number.null)
		return constructor.execute(args)

	def copy(self):
		return SuperRef(self.instance, self.parent).set_context(self.context).set_pos(self.pos_start, self.pos_end)

	def __repr__(self):
		return f"<super de {self.parent.name}>"

	__str__ = __repr__


class Function(BaseFunction):
	def __init__(self, name, body_node, arg_names, should_auto_return=True, arg_defaults=False, arg_types=None, return_type=None):
		super().__init__(name)
		self.body_node = body_node
		self.arg_names = arg_names
		self.should_auto_return = should_auto_return
		self.obj = None
		self.owner = None  # classe onde o método foi definido
		self.arg_defaults = arg_defaults or []
		self.arg_types = arg_types or []
		self.return_type = return_type
	
	def set_obj(self, obj):
		self.obj = obj
		return obj

	def execute(self, args):
		from .interpreter import Interpreter  # import tardio (evita ciclo)
		res = RTResult()
		interpreter = Interpreter()

		if self.obj:
			# escopo léxico: os nomes soltos vêm de onde a classe foi definida (e dos globais),
			# NÃO dos membros da instância (assim um método chamado `str` não esconde a função `str`).
			scope = getattr(self.owner, 'definition_scope', None) or global_symbol_table
			new_context = Context(self.name, parent=self.obj.context)
			new_context.symbol_table = SymbolTable(scope)
			new_context.self_obj = self.obj
			new_context.defining_class = self.owner
			args = [self.obj] + args
		else:
			new_context = self.generate_new_context()
		
		evaluated_args = []
		for i in range(len(self.arg_names)):
			if i < len(args):
				evaluated_args.append(args[i])
			else:
				if i < len(self.arg_defaults) and self.arg_defaults[i][1] is not None:
					default_value = res.register(interpreter.visit(
						self.arg_defaults[i][1], new_context
					))
					if res.error: return res
					evaluated_args.append(default_value)
				else:
					return res.failure(RTError(
						self.pos_start, self.pos_end,
						f"Faltando argumento para '{self.arg_names[i]}'",
						new_context
					))
		

		if self.arg_types:
			from .typesystem import check_value_type  # import tardio (evita ciclo)
			for i, arg_type in enumerate(self.arg_types):
				if arg_type is not None and i < len(evaluated_args):
					message = check_value_type(
						evaluated_args[i], arg_type, new_context.symbol_table,
						f"Argumento '{self.arg_names[i]}' de '{self.name or 'função anônima'}'"
					)
					if message:
						return res.failure(RTError(self.pos_start, self.pos_end, message, new_context, 'Erro de Tipo'))

		res.register(self.check_and_populate_args(self.arg_names, evaluated_args, new_context))
		if res.should_return():
			return res

		value = res.register(interpreter.visit(self.body_node, new_context))

		if res.should_return():
			if res.func_return_value is not None:
				error = self._check_return(res.func_return_value, new_context)
				if error: return res.failure(error)
				return res.success(res.func_return_value)
			return res

		# corpo em bloco sem `retornar` devolve nulo (antes devolvia a lista com o valor de cada comando)
		result_value = value if (self.should_auto_return and value) else Number.null
		error = self._check_return(result_value, new_context)
		if error: return res.failure(error)
		return res.success(result_value)

	def _check_return(self, value, exec_ctx):
		"""RTError se o valor devolvido não combina com o tipo de retorno declarado (`-> tipo`)."""
		if self.return_type is None:
			return None
		from .typesystem import check_value_type  # import tardio (evita ciclo)
		message = check_value_type(value, self.return_type, exec_ctx.symbol_table,
			f"Retorno de '{self.name or 'função anônima'}'")
		if message:
			return RTError(self.pos_start, self.pos_end, message, exec_ctx, 'Erro de Tipo')
		return None

	def copy(self):
		copy = Function(self.name, self.body_node, self.arg_names, self.should_auto_return, self.arg_defaults, self.arg_types, self.return_type)
		copy.set_context(self.context)
		copy.set_pos(self.pos_start, self.pos_end)
		copy.obj = self.obj
		copy.owner = self.owner
		copy.arg_types = self.arg_types
		copy.return_type = self.return_type
		copy.properties = self.properties
		return copy


def python_to_value(obj):
	"""Converte um objeto Python em um valor Nebula."""
	if isinstance(obj, Value): return obj
	if obj is None: return Number.null
	if isinstance(obj, bool): return Boolean(int(obj))
	if isinstance(obj, (int, float)): return Number(obj)
	if isinstance(obj, str): return String(obj)
	if isinstance(obj, (list, set, frozenset)): return List([python_to_value(x) for x in obj])
	if isinstance(obj, tuple): return Tuple([python_to_value(x) for x in obj])
	if isinstance(obj, dict): return Dict([(String(str(k)), python_to_value(v)) for k, v in obj.items()])
	return String(str(obj))
