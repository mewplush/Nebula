"""Nós da árvore sintática (AST)."""


class FuncDefNode:
	def __init__(self, var_name_tok, arg_name_toks, body_node, should_auto_return, private=False, default_vals=None, arg_types=None, return_type=None):
		self.var_name_tok = var_name_tok
		self.arg_types = arg_types or [None] * len(arg_name_toks)
		self.return_type = return_type
		self.arg_name_toks = arg_name_toks
		self.body_node = body_node
		self.should_auto_return = should_auto_return
		self.private = private
		self.default_vals = default_vals

		if self.var_name_tok:
			self.pos_start = self.var_name_tok.pos_start
		elif len(self.arg_name_toks) > 0:
			self.pos_start = self.arg_name_toks[0].pos_start
		else:
			self.pos_start = self.body_node.pos_start
		
		self.pos_end = self.body_node.pos_end
	
	def __repr__(self):
		return f'FuncDefNode({self.var_name_tok}, {self.arg_name_toks}, {self.body_node}, {self.should_auto_return})'


class SuperNode:
	def __init__(self, pos_start, pos_end):
		self.pos_start = pos_start
		self.pos_end = pos_end

	def __repr__(self):
		return "super()"


class ClassNode:
	def __init__(self, class_name_tok, body_node, inheritance):
		self.class_name_tok = class_name_tok
		self.body_node = body_node
		self.inheritance = inheritance
		self.pos_start = self.class_name_tok.pos_start
		self.pos_end = self.body_node.pos_end if body_node else class_name_tok.pos_end
	
	def __repr__(self):
		return f'ClassNode({self.class_name_tok}, {self.body_node}, {self.inheritance})'


class SwitchNode:
	def __init__(self, expr_to_compare, cases, default_case, pos_start, pos_end):
		self.expr_to_compare = expr_to_compare
		self.cases = cases # [(val, body, is_block, pos_start)...]
		self.default_case = default_case # (body, is_block, pos_start) or None

		self.pos_start = pos_start
		self.pos_end = pos_end
	
	def __repr__(self):
		return f'SwitchNode({self.expr_to_compare}, {self.cases}, {self.default_case})'


class CallNode:
	def __init__(self, node_to_call, arg_nodes):
		self.node_to_call = node_to_call
		self.arg_nodes = arg_nodes

		self.pos_start = self.node_to_call.pos_start

		if len(self.arg_nodes) > 0:
			self.pos_end = self.arg_nodes[len(self.arg_nodes) - 1].pos_end
		else:
			self.pos_end = self.node_to_call.pos_end
	
	def __repr__(self):
		return f'{repr(self.node_to_call)}({[repr(arg) for arg in self.arg_nodes]})'


class NumberNode:
	def __init__(self, tok):
		self.tok = tok

		self.pos_start = self.tok.pos_start
		self.pos_end = self.tok.pos_end

	def __repr__(self):
		
		return f'{self.tok}'


class BoolNode:
	def __init__(self, tok):
		self.tok = tok

		self.pos_start = self.tok.pos_start
		self.pos_end = self.tok.pos_end
	
	def __repr__(self):
		return f'\'{self.tok}\''


class StringNode:
	def __init__(self, tok):
		self.tok = tok

		self.pos_start = tok.pos_start
		self.pos_end = tok.pos_end

	def __repr__(self):
		return f'{self.tok}'


class FStringNode:
	def __init__(self, parts, pos_start, pos_end):
		self.parts = parts

		self.pos_start = pos_start
		self.pos_end = pos_end
	
	def __repr__(self):
		return f"f'{self.parts}'"


	

class ListNode:
	def __init__(self, element_nodes, pos_start=None, pos_end=None):
		self.element_nodes = element_nodes

		self.pos_start = pos_start if pos_start else self.element_nodes.pos_start
		self.pos_end = pos_end if pos_end else self.element_nodes.pos_end

	def __repr__(self):
			return f'[{", ".join([repr(x) for x in self.element_nodes])}]'


class TupleNode:
	def __init__(self, element_nodes, pos_start=None, pos_end=None):
		self.element_nodes = element_nodes
		self.pos_start = pos_start
		self.pos_end = pos_end

	def __repr__(self):
		return f'({", ".join([repr(x) for x in self.element_nodes])})'


class DictNode:
	def __init__(self, pairs, pos_start=None, pos_end=None):
		self.pairs = pairs

		self.pos_start = pos_start if pos_start else self.pairs[0].pos_start
		self.pos_end = pos_end if pos_end else self.pairs[len(self.pairs) - 1].pos_end

	def __repr__(self):
		return f'{{{", ".join([f"{str(k.value)}: {repr(v.copy())}" for k, v in self.pairs])}}}'


class DictCompNode:
	# {chave: valor para cada chave, valor em pares}
	def __init__(self, key_expr, value_expr, iterator, pos_start, pos_end):
		self.key_expr = key_expr
		self.value_expr = value_expr
		self.iterator = iterator

		self.pos_start = pos_start
		self.pos_end = pos_end


class SetNode:
	def __init__(self, elements, pos_start=None, pos_end=None):
		self.elements = elements

		self.pos_start = pos_start if pos_start else self.elements[0].pos_start
		self.pos_end = pos_end if pos_end else self.elements[-1].pos_end
	
	def __repr__(self):
		self.reprs = [", ".join(self.elements)]
		return "{" + self.reprs + "}"


class AttrAccessNode:
	def __init__(self, obj_node, attr_name_tok):
		self.obj_node = obj_node
		self.attr_name_tok = attr_name_tok
		self.pos_start = obj_node.pos_start
		self.pos_end = attr_name_tok.pos_end
	
	def __repr__(self):
		return f'{self.obj_node}.{self.attr_name_tok}'


class AttrAssignNode:
	def __init__(self, obj_node, attr_name_tok, value_node):
		self.obj_node = obj_node
		self.attr_name_tok = attr_name_tok
		self.value_node = value_node

		self.pos_start = obj_node.pos_start
		self.pos_end = value_node.pos_end
	
	def __repr__(self):
		return f'{self.obj_node}.{self.attr_name_tok} = {self.value_node}'


class ArrayAccessNode:
	def __init__(self, obj_node, index_node):
		self.obj_node = obj_node
		self.index_node = index_node
		self.pos_start = obj_node.pos_start
		self.pos_end = index_node.pos_end
	
	def __repr__(self):
		return f'{self.obj_node}[{self.index_node}]'


class ArrayAssignNode:
	def __init__(self, obj_node, index_node, value_node):
		self.obj_node = obj_node
		self.index_node = index_node
		self.value_node = value_node

		self.pos_start = obj_node.pos_start
		self.pos_end = value_node.pos_end
	
	def __repr__(self):
		return f'{self.obj_node}[{self.index_node}] = {self.value_node}'


class IfNode:
	def __init__(self, cases, else_case):
		self.cases = cases
		self.else_case = else_case

		self.pos_start = self.cases[0][0].pos_start
		self.pos_end = (self.else_case or self.cases[-1])[0].pos_end if self.else_case or self.cases else None
	
	def __repr__(self):
		return f'IfNode({self.cases}, {self.else_case})'


	
class ForNode:
	def __init__(self, var_name_tok, start_value_node, end_value_node, step_value_node, body, should_return_null):
		self.var_name_tok = var_name_tok
		self.start_value_node = start_value_node
		self.end_value_node = end_value_node
		self.step_value_node = step_value_node
		self.body_node = body
		self.should_return_null = should_return_null

		self.pos_start = self.var_name_tok.pos_start
		self.pos_end = self.body_node.pos_end
	
	def __repr__(self):
		return f'ForNode({self.var_name_tok}, {self.start_value_node}, {self.end_value_node}, {self.step_value_node}, {self.body_node}, {self.should_return_null})'


class ForEachNode:
	def __init__(self, var_name_tok, iterable_node, body_node, should_return_null):
		self.var_name_tok = var_name_tok
		self.iterable_node = iterable_node
		self.body_node = body_node
		self.should_return_null = should_return_null

		self.pos_start = self.var_name_tok[0].pos_start
		self.pos_end = self.body_node.pos_end


class WhileNode:
	def __init__(self, condition_node, body_node, should_return_null):
		self.condition_node = condition_node
		self.body_node = body_node
		self.should_return_null = should_return_null

		self.pos_start = self.condition_node.pos_start
		self.pos_end = self.body_node.pos_end
	
	def __repr__(self):
		return f'WhileNode({self.condition_node}, {self.body_node}, {self.should_return_null})'


class VarAccessNode:
	def __init__(self, var_name_tok):
		self.var_name_tok = var_name_tok

		self.pos_start = self.var_name_tok.pos_start
		self.pos_end = self.var_name_tok.pos_end
	
	def __repr__(self):
		return f'VarAccessNode({self.var_name_tok})'


class VarAssignNode:
	def __init__(self, var_name_tok, value_node, constant=False, change_value=False, private=False, type_=None):
		self.var_name_toks = var_name_tok
		self.value_node = value_node
		self.constant = constant
		self.change_value = change_value	
		self.private = private
		self.type = type_

		if not isinstance(self.var_name_toks, list):
			self.var_name_toks = [var_name_tok]

		self.pos_start = self.var_name_toks[0].pos_start
		self.pos_end = self.value_node.pos_end if self.value_node else self.var_name_toks[-1].pos_end

	def __repr__(self):
		return f'VarAssignNode({self.var_name_toks}, {self.value_node})'


class BinOpNode:
	def __init__(self, left_node, op_tok, right_node):
		self.left_node = left_node
		self.op_tok = op_tok
		self.right_node = right_node

		self.pos_start = self.left_node.pos_start
		self.pos_end = self.right_node.pos_end if self.right_node else self.left_node.pos_end

	def __repr__(self):
		return f'({self.left_node}, {self.op_tok}, {self.right_node})'


class UnaryOpNode:
	def __init__(self, op_tok, node):
		self.op_tok = op_tok
		self.node = node

		self.pos_start = self.op_tok.pos_start
		self.pos_end = node.pos_end

	def __repr__(self):
		return f'({self.op_tok}, {self.node})'


class ReturnNode:
	def __init__(self, node_to_return, pos_start, pos_end):
		self.node_to_return = node_to_return
		
		self.pos_start = pos_start
		self.pos_end = pos_end
	
	def __repr__(self):
		return f'ReturnNode({self.node_to_return})'


class ContinueNode:
	def __init__(self, pos_start, pos_end):
		self.pos_start = pos_start
		self.pos_end = pos_end
	
	def __repr__(self):
		return f'ContinueNode()'


class BreakNode:
	def __init__(self, pos_start, pos_end):
		self.pos_start = pos_start
		self.pos_end = pos_end
	
	def __repr__(self):
		return f'BreakNode()'


class CheckNode:
	def __init__(self, condition, error_to_raise, details, pos_start, pos_end):
		self.condition_node = condition
		self.error_name = error_to_raise
		self.details = details
		
		self.pos_start = pos_start
		self.pos_end = pos_end
	
	def __repr__(self):
		return f'CheckNode({self.condition_node}, {self.error_name}, {self.details})'


class RaiseNode:
	def __init__(self, error_name, details, pos_start, pos_end):
		self.error_name = error_name
		self.details = details
		
		self.pos_start = pos_start
		self.pos_end = pos_end
	
	def __repr__(self):
		return f'RaiseNode({self.error_name}, {self.details})'


class TryCatchNode:
	def __init__(self, try_body, catch_var_tok, catch_body):
		self.try_body = try_body
		self.catch_var_tok = catch_var_tok
		self.catch_body = catch_body
		
		self.pos_start = self.try_body.pos_start
		self.pos_end = self.catch_body.pos_end
	
	def __repr__(self):
		return f'TryCatchNode({self.try_body}, {self.catch_var_tok}, {self.catch_body})'


class ImportNode:
	def __init__(self, file_path, functions, pos_start, pos_end):
		self.file_path = file_path
		self.functions = functions
		
		self.pos_start = pos_start
		self.pos_end = pos_end
	
	def __repr__(self):
		return f'ImportNode({self.file_path}, {self.functions})'


class ImportNamespaceNode:
	def __init__(self, module_path, pos_start, pos_end):
		self.module_path = module_path
		
		self.pos_start = pos_start
		self.pos_end = pos_end
	
	def __repr__(self):
		return f'ImportNamespaceNode({self.module_path})'


class TypeNode:
	"""Anotação de tipo: `número`, `Animal`, `lista[número]`, `número ou nulo` (união quando `options` existe)."""
	def __init__(self, name=None, pos_start=None, pos_end=None, args=None, options=None):
		self.name = name
		self.args = args or []
		self.options = options  # lista de TypeNode quando é uma união
		self.pos_start = pos_start
		self.pos_end = pos_end

	def __repr__(self):
		if self.options:
			return ' ou '.join(repr(o) for o in self.options)
		if self.args:
			return f"{self.name}[{', '.join(repr(a) for a in self.args)}]"
		return str(self.name)

	__str__ = __repr__
