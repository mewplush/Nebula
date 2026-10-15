"""Anotações de tipo: validação e checagem em tempo de execução.

Tipos aceitos:  número, string, booleano, nulo, lista, tupla, mesa, dicionário, função, classe, qualquer,
nomes de classes próprias (aceita subclasses; `modulo.Classe` para `importar modulo`), `lista[número]` (elementos), `dicionário[string, número]`
(chaves, valores), e uniões com `ou`:  `número ou nulo`.
"""
from .values import BaseFunction, Boolean, Class, Dict, Instance, List, Nulo, Number, Set, String, Tuple

PRIMITIVES = {
	'número': Number, 'string': String, 'lista': List, 'tupla': Tuple, 'mesa': Set,
	'dicionário': Dict, 'booleano': Boolean, 'nulo': Nulo,
}
SPECIAL = ('qualquer', 'função', 'classe')
GENERIC_ARITY = {'lista': (1,), 'tupla': (1,), 'mesa': (1,), 'dicionário': (1, 2)}


def value_type_name(value):
	if isinstance(value, Instance):
		return value.class_.name
	if isinstance(value, Class):
		return 'classe'
	if isinstance(value, BaseFunction):
		return 'função'
	for name, cls in PRIMITIVES.items():
		if isinstance(value, cls):
			return name
	return type(value).__name__.lower()


def resolve_class(name, scope):
	"""Acha a classe de um nome de tipo, inclusive `modulo.Classe` (módulo importado como namespace). None se não achar."""
	if scope is None:
		return None
	parts = name.split('.')
	found = scope.get(parts[0])
	for part in parts[1:]:
		if not isinstance(found, Dict):
			return None
		found = next((v for k, v in found.elements if getattr(k, 'value', None) == part), None)
	return found if isinstance(found, Class) else None


def validate_type(t, scope):
	"""Devolve uma mensagem de erro se o tipo é inválido (nome desconhecido, parâmetros demais...), senão None."""
	if t.options:
		for option in t.options:
			error = validate_type(option, scope)
			if error:
				return error
		return None
	name = t.name
	if name not in PRIMITIVES and name not in SPECIAL:
		if resolve_class(name, scope) is None:
			return f"tipo desconhecido '{name}'"
	if t.args:
		if name not in GENERIC_ARITY:
			return f"o tipo '{name}' não aceita parâmetros de tipo"
		if len(t.args) not in GENERIC_ARITY[name]:
			return f"o tipo '{name}' espera {' ou '.join(map(str, GENERIC_ARITY[name]))} parâmetro(s) de tipo"
		for arg in t.args:
			error = validate_type(arg, scope)
			if error:
				return error
	return None


def matches(value, t, scope):
	if t.options:
		return any(matches(value, option, scope) for option in t.options)
	name = t.name
	if name == 'qualquer':
		return True
	if name == 'função':
		return isinstance(value, BaseFunction) and not isinstance(value, Class)
	if name == 'classe':
		return isinstance(value, Class)
	if name in PRIMITIVES:
		if not isinstance(value, PRIMITIVES[name]):
			return False
		return _items_match(value, name, t.args, scope) if t.args else True
	if not isinstance(value, Instance):
		return False
	expected = resolve_class(name, scope)
	if expected is not None:
		return value.class_.inherits_from(expected)
	return value.class_.is_subclass_of(name.split('.')[-1])


def _items_match(value, name, args, scope):
	if name == 'dicionário':
		key_type = args[0] if len(args) == 2 else None
		value_type = args[-1]
		return all((key_type is None or matches(k, key_type, scope)) and matches(v, value_type, scope)
				for k, v in value.elements)
	return all(matches(element, args[0], scope) for element in value.elements)


def check_value_type(value, t, scope, what):
	"""None se o valor combina com o tipo; senão, a mensagem de erro (prefixada por `what`)."""
	error = validate_type(t, scope)
	if error:
		return f"{what}: {error}"
	if matches(value, t, scope):
		return None
	return f"{what}: esperado '{t}', obtido '{value_type_name(value)}'"
