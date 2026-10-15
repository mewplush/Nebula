"""Interpretador: percorre a AST e executa."""

import os

from .modules import MODULES_LOADING, MODULE_CACHE, resolve_module_path
from .errors import CheckError, Error, RTError, ValorError
from .tokens import (
	TT_DIV,
	TT_EE,
	TT_GT,
	TT_GTE,
	TT_IDENTIFIER,
	TT_KEYWORD,
	TT_LT,
	TT_LTE,
	TT_MINUS,
	TT_MUL,
	TT_NE,
	TT_PERCENT,
	TT_PLUS,
	TT_POW,
	Token,
)
from .nodes import ClassNode, DictCompNode, ImportNamespaceNode, StringNode
from .context import Context, RTResult, SymbolTable, suggest_name
from .values import (
	BaseFunction,
	Boolean,
	Class,
	Dict,
	Function,
	Instance,
	List,
	Nulo,
	Number,
	Set,
	String,
	SuperRef,
	Tuple,
)
from .typesystem import check_value_type
from .builtin_functions import BuiltInFunction


BINOP_BY_TYPE = {
	TT_PLUS: 'added_to', TT_MINUS: 'subbed_by', TT_MUL: 'multed_by', TT_DIV: 'dived_by',
	TT_PERCENT: 'mod_by', TT_POW: 'powed_by', TT_EE: 'get_comparison_eq', TT_NE: 'get_comparison_ne',
	TT_LT: 'get_comparison_lt', TT_LTE: 'get_comparison_lte', TT_GT: 'get_comparison_gt', TT_GTE: 'get_comparison_gte',
}


BINOP_BY_KEYWORD = {
	'igual': 'get_comparison_eq', 'e': 'anded_by', 'ou': 'ored_by', 'em': 'included_in',
}


class Interpreter:
	_VISIT_TABLE = {}  # classe do nó -> função visit_X (evita montar a string e usar getattr a cada nó)

	def visit(self, node, context):
		cls = node.__class__
		fn = Interpreter._VISIT_TABLE.get(cls)
		if fn is None:
			fn = getattr(Interpreter, f'visit_{cls.__name__}', None)
			if fn is None:
				return self.no_visit_method(node, context)
			Interpreter._VISIT_TABLE[cls] = fn
		return fn(self, node, context)

	def no_visit_method(self, node, context):
		raise Exception(f'Nenhum visit_{type(node).__name__} metódo encontrado')

	###################################

	def visit_NumberNode(self, node, context):
		return RTResult().success(
			Number(node.tok.value).set_context(context).set_pos(node.pos_start, node.pos_end)
		)
	
	def visit_StringNode(self, node, context):
		
		return RTResult().success(
			String(node.tok.value).set_context(context).set_pos(node.pos_start, node.pos_end)
		)
	
	def visit_BoolNode(self, node, context):
		return RTResult().success(
			Boolean(node.tok.value).set_context(context).set_pos(node.pos_start, node.pos_end)
		)
	
	def visit_SetNode(self, node, context):
		res = RTResult()
		elements = []

		for item in node.elements:
			elements.append(res.register(self.visit(item, context)))
			if res.should_return(): return res

		return res.success(
			Set(elements).set_context(context).set_pos(node.pos_start, node.pos_end)
		)
	
	def visit_FStringNode(self, node, context):
		res = RTResult()
		evaluated_parts = []
		
		for part in node.parts:
			if isinstance(part, StringNode):
				evaluated_parts.append(('TEXT', part.tok.value))
			else:
				value = res.register(self.visit(part, context))
				if res.error: return res
				evaluated_parts.append(('EXPR', value.__sstr__() if isinstance(value, List) else value))
		
		return res.success(String(evaluated_parts))

	def visit_ClassNode(self, node: ClassNode, context):
		res = RTResult()
		
		parent_class = None
		if node.inheritance:
			parent_value = context.symbol_table.get(node.inheritance.value)
			if not isinstance(parent_value, Class):
				return res.failure(RTError(
					node.pos_start, node.pos_end,
					f"Superclasse '{node.inheritance.value}' não é uma classe válida",
					context
				))
			parent_class = parent_value
			
		class_value = Class(
			node.class_name_tok.value,
			parent_class
		)
		
		class_value.definition_scope = context.symbol_table  # escopo onde a classe foi definida
		class_context = Context(class_value.name, parent=context)
		class_context.symbol_table = class_value.symbol_table
		class_value.set_context(class_context)

		res.register(self.visit(node.body_node, class_context))
		if res.error: return res

		for member in class_value.symbol_table.symbols.values():
			if isinstance(member, Function):
				member.owner = class_value  # `super` e o escopo léxico dos métodos dependem disto
		
		context.symbol_table.set(class_value.name, class_value)
		return res.success(class_value)

	def visit_VarAccessNode(self, node, context):
		res = RTResult()
		var_name = node.var_name_tok.value
		value = context.symbol_table.get(var_name)

		if value is None:
			# `this` implícito: dentro de um método, um nome solto pode ser atributo/método da instância
			ctx = context
			while ctx is not None and not isinstance(ctx, str):
				if getattr(ctx, 'self_obj', None) is not None:
					member = ctx.self_obj.get_member(var_name)
					if member is not None:
						return res.success(member.copy().set_pos(node.pos_start, node.pos_end).set_context(context))
					break
				ctx = getattr(ctx, 'parent', None)

			message = f"'{var_name}' nunca foi declarado"
			suggestion = suggest_name(var_name, context.symbol_table)
			if suggestion:
				message += f". Você quis dizer '{suggestion}'?"
			return res.failure(RTError(
				node.pos_start, node.pos_end,
				message,
				context
			))

		value = value.copy().set_pos(node.pos_start, node.pos_end).set_context(context)
		return res.success(value)

	def visit_VarAssignNode(self, node, context):
		res = RTResult()
		
		value = res.register(self.visit(node.value_node, context)) if node.value_node else Nulo().set_context(context).set_pos(node.pos_start, node.pos_end)
		if res.should_return(): return res
		
		for var_tok in node.var_name_toks:
			var_name = var_tok.value

			declared_type = node.type or context.symbol_table.get_type(var_name)
			if declared_type is not None:
				message = check_value_type(value, declared_type, context.symbol_table, f"Tipo inválido para '{var_name}'")
				if message:
					return res.failure(RTError(node.pos_start, node.pos_end, message, context, 'Erro de Tipo'))

			if 'esse' in context.symbol_table.symbols and isinstance(context.symbol_table.get('esse'), Instance):
				instance = context.symbol_table.get('esse')
				instance.set(var_name, value.copy(), node.constant)
			else:
				result = context.symbol_table.set(var_name, value.copy(), node.constant, node.private, node.type)
				if result == 'error':
					return res.failure(RTError(
						node.pos_start, node.pos_end,
						f"'{var_name}' não pode ser alterado, já que é uma constante.",
						context
					))

		value = value.copy().set_pos(node.pos_start, node.pos_end).set_context(context)
		
		return res.success(value)
	
	def visit_ListNode(self, node, context):
		res = RTResult()
		elements = []

		for element_node in node.element_nodes:
			elements.append(res.register(self.visit(element_node, context)))
			if res.should_return(): return res

		return res.success(List(elements).set_context(context).set_pos(node.pos_start, node.pos_end))
	
	def visit_TupleNode(self, node, context):
		res = RTResult()
		elements = []
		
		for element_node in node.element_nodes:
			elements.append(res.register(self.visit(element_node, context)))
			if res.error: return res
			
		return res.success(Tuple(elements))

	def visit_DictNode(self, node, context):
		res = RTResult()
		elements = []
		
		for key_node, value_node in node.pairs:
			key = String(key_node.value)
			
			if isinstance(value_node, (String, Number)):
				value = value_node
			else:
				value = res.register(self.visit(value_node, context))
			if res.error: return res
			
			elements.append((key, value))
		
		return res.success(Dict(elements).set_context(context).set_pos(node.pos_start, node.pos_end))
	
	def visit_DictCompNode(self, node: DictCompNode, context):
		res = RTResult()
		
		if (node.iterator.type == TT_IDENTIFIER):
			iterable = context.symbol_table.get(node.iterator.value)
			if iterable == None:
				return res.failure(ValorError(
					node.pos_start, node.pos_end,
					"Esperado uma lista, tupla ou mesa para compreensão de dicionários.",
				))
		else:
			iterable = res.register(self.visit(node.iterator, context))
		if res.should_return(): return res

		if not isinstance(iterable, (List, Tuple, Set)):
			return res.failure(ValorError(
				node.pos_start, node.pos_end,
				"Esperado uma lista, tupla ou mesa para compreensão de dicionários.",
			))

		loop = Context('<compreensão de dict>', context)
		loop.symbol_table = SymbolTable(context.symbol_table)

		result = []

		for item in iterable.elements:
			if not isinstance(item, (List, Tuple)):
				return res.failure(ValorError(
					node.pos_start, node.pos_end,
					"Esperado uma lista ou tupla para compreensão de dicionários.",
				))
			loop.symbol_table.set(node.key_expr.value, item.elements[0])
			loop.symbol_table.set(node.value_expr.value, item.elements[1])

			result.append((item.elements[0], item.elements[1]))

			if res.should_return(): return res
		
		return res.success(Dict(result).set_context(context).set_pos(node.pos_start, node.pos_end))

		
	
	def visit_AttrAccessNode(self, node, context: Context):
		res = RTResult()
		obj = res.register(self.visit(node.obj_node, context))
		if res.error: return res

		attr_name = node.attr_name_tok.value

		if attr_name == "pode_executar":
			func = BuiltInFunction("any_is_callable")
			func.obj = obj
			func.set_context(context)
			return res.success(func)
		elif attr_name == "tamanho":
			func = BuiltInFunction("any_tamanho")
			func.obj = obj
			func.set_context(context)
			return res.success(func)

		if isinstance(obj, Dict):
			if attr_name in ["chaves", "valores", "itens", "mudar", "extender"]:
				if attr_name == "chaves": attr_name = "keys"
				elif attr_name == "valores": attr_name = "values"
				elif attr_name == "itens": attr_name = "items"
				func = BuiltInFunction(f"dict_{attr_name}")
				func.obj = obj
				func.set_context(context)
				return res.success(func)
			else:
				for key, value in obj.elements:
					if key.value == attr_name:
						return res.success(value.copy())
				return res.failure(RTError(
					node.pos_start, node.pos_end,
					f"Chave '{attr_name}' não encontrada.",	
					context
				))
		elif isinstance(obj, List):
			if attr_name in ["invertida", "procurar", "filtrar", "algum", "todos", "reduzir", "ordenar", "colocar", "map", "estourar", "extender", "mudar", "agrupar"]:
				func = BuiltInFunction(f"list_{attr_name}")
				func.obj = obj
				func.set_context(context)
				return res.success(func)
			else:
				if attr_name in obj.properties:
					return res.success(obj.properties[attr_name].copy())
				return res.failure(RTError(
					node.pos_start, node.pos_end,
					f"Atributo '{attr_name}' para listas não encontrado, talvez tenha confudido com os métodos de dicionários?",
					context
				))
		elif isinstance(obj, String):
			if attr_name in ["fatiar", "picotar", "limpar", "maiúsculo", "minúsculo", "começa_com", "termina_com", "contem", "tamanho", "pode_executar", "tamanho", "pode_executar"]:
				func = BuiltInFunction(f"string_{attr_name}")
				func.obj = obj
				func.set_context(context)
				return res.success(func)
			else:
				if attr_name in obj.properties:
					return res.success(obj.properties[attr_name].copy())
				return res.failure(RTError(
					node.pos_start, node.pos_end,
					f"Atributo '{attr_name}' para strings não encontrado, talvez tenha confudido com os métodos de dicionários?",
					context
				))
		elif isinstance(obj, SuperRef):
			member = obj.get(attr_name)
			if member is None:
				return res.failure(RTError(
					node.pos_start, node.pos_end,
					f"A superclasse '{obj.parent.name}' não tem '{attr_name}'",
					context
				))
			return res.success(member)
		elif isinstance(obj, Instance):
			return res.success(obj.get(attr_name))
		else:
			if attr_name in obj.properties:
				return res.success(obj.properties[attr_name].copy())
		

		return res.failure(RTError(
			node.pos_start, node.pos_end,
			"Attribute access only supported for dictionaries",
			context
		))
	
	def visit_AttrAssignNode(self, node, context):
		res = RTResult()
		
		obj = res.register(self.visit(node.obj_node, context))
		if res.error: return res
		
		value = res.register(self.visit(node.value_node, context))
		if res.error: return res
		
		attr_name = node.attr_name_tok.value

		if isinstance(obj, Instance):
			obj.set(attr_name, value)
			return res.success(value)
		elif isinstance(obj, Dict):
			found = False
			for i, (k, v) in enumerate(obj.elements):
				if k.value == attr_name:
					obj.elements[i] = (k, value)
					found = True
					break
			if not found:
				obj.elements.append((String(attr_name), value))
			return res.success(value)
		else:
			obj.properties[attr_name] = value
			return res.success(value)
	
	def visit_ArrayAccessNode(self, node, context):
		res = RTResult()
		
		obj = res.register(self.visit(node.obj_node, context))
		if res.error: return res
		
		index = res.register(self.visit(node.index_node, context))
		if res.error: return res
		
		if isinstance(obj, List):
			try:
				value = (obj.elements[int(index.value)])

				if isinstance(value, str):
					return res.success(String(value).set_context(context).set_pos(node.pos_start, node.pos_end))
				elif isinstance(value, int) or isinstance(value, float):
					return res.success(Number(value).set_context(context).set_pos(node.pos_start, node.pos_end))
				elif isinstance(value, list):
					for i in value:
						if len(i) < 2:
							return res.success(List(value).set_context(context).set_pos(node.pos_start, node.pos_end))
						else:
							return res.success(Dict(value).set_context(context).set_pos(node.pos_start, node.pos_end))
				else:
					return res.success(value.copy())
			except:
				return res.failure(RTError(
					node.pos_start, node.pos_end,
					f"Index {index} não existe",
					context
				))
		elif isinstance(obj, Dict):
			for k, v in obj.elements:
				if k.value == index.value:
					return res.success(v.copy())
			return res.failure(RTError(
				node.pos_start, node.pos_end,
				f"Chave '{index}' não encontrada",
				context
			))
		elif isinstance(obj, Set):
			try:
				value = (obj.elements[int(index.value)])

				if isinstance(value, str):
					return res.success(String(value).set_context(context).set_pos(node.pos_start, node.pos_end))
				elif isinstance(value, int) or isinstance(value, float):
					return res.success(Number(value).set_context(context).set_pos(node.pos_start, node.pos_end))
				elif isinstance(value, list):
					for i in value:
						if len(i) < 2:
							return res.success(List(value).set_context(context).set_pos(node.pos_start, node.pos_end))
						else:
							return res.success(Dict(value).set_context(context).set_pos(node.pos_start, node.pos_end))
				else:
					return res.success(value.copy())
			except:
				return res.failure(RTError(
					node.pos_start, node.pos_end,
					f"Index {index} não existe",
					context
				))
		
		return res.failure(RTError(
			node.pos_start, node.pos_end,
			"Acesso usando [index] somente disponível para listas",
			context
		))
	
	def visit_SwitchNode(self, node, context):
		res = RTResult()
		
		value_to_compare = res.register(self.visit(node.expr_to_compare, context))
		if res.should_return(): return res

		for case_value, body_node, is_block, _ in node.cases:
			case_val = res.register(self.visit(case_value, context))
			if res.should_return(): return res

			result, error = value_to_compare.get_comparison_eq(case_val)
			if error: return res.failure(error)
			
			if result.is_true():
				body_value = res.register(self.visit(body_node, context))
				if res.should_return(): return res
				return res.success(body_value)

		if node.default_case:
			default_body, is_block, _ = node.default_case
			default_value = res.register(self.visit(default_body, context))
			if res.should_return(): return res
			return res.success(default_value)

		return res.success(Number.null)
	
	def visit_TryCatchNode(self, node, context):
		res = RTResult()
		try_result = res.register(self.visit(node.try_body, context))
		if res.loop_should_break or res.loop_should_continue or res.func_return_value: return res

		if not res.should_return():
			return res.success(try_result)
		
		error_val = String(str(res.error.as_string())).set_context(context).set_pos(node.pos_start, node.pos_end)

		res.reset()
		context.symbol_table.set(node.catch_var_tok.value, error_val)
		catch_result = res.register(self.visit(node.catch_body, context))
		if res.should_return(): return res
		
		return res.success(catch_result)

	def visit_CheckNode(self, node, context):
		res = RTResult()

		condition = res.register(self.visit(node.condition_node, context))
		if res.should_return(): return res

		if condition.is_true():
			return res.success(Number(1).set_context(context).set_pos(node.pos_start, node.pos_end))
		else:
			error_name = res.register(self.visit(node.error_name, context)) if node.error_name else None
			details = res.register(self.visit(node.details, context)) if node.details else "Expressão Conferir resultou em Falso."

			return res.failure(Error(
				node.pos_start, node.pos_end,
				str(error_name), repr(details)
			)) if node.error_name else res.failure(CheckError(
				node.pos_start, node.pos_end,
				repr(details)
			))
	
	def visit_RaiseNode(self, node, context):
		res = RTResult()

		error_name = res.register(self.visit(node.error_name, context))
		details = res.register(self.visit(node.details, context))

		return res.failure(Error(
			node.pos_start, node.pos_end,
			repr(error_name), repr(details)
		))
	
	def visit_SuperNode(self, node, context):
		res = RTResult()
		instance = None
		defining_class = None
		ctx = context
		while ctx is not None and not isinstance(ctx, str):
			if getattr(ctx, 'defining_class', None) is not None:
				defining_class = ctx.defining_class
				instance = ctx.self_obj
				break
			ctx = getattr(ctx, 'parent', None)

		if not isinstance(instance, Instance) or defining_class is None:
			return res.failure(RTError(
				node.pos_start, node.pos_end,
				"'super' só pode ser usado dentro de métodos de classe",
				context
			))

		if not defining_class.parent:
			return res.failure(RTError(
				node.pos_start, node.pos_end,
				f"A classe '{defining_class.name}' não possui uma superclasse",
				context
			))

		return res.success(SuperRef(instance, defining_class.parent).set_context(context).set_pos(node.pos_start, node.pos_end))
	
	def _load_module(self, module_name, node, context):
		"""Resolve, executa (uma única vez) e devolve o contexto do módulo."""
		from .runtime import run  # import tardio (evita ciclo)
		res = RTResult()
		full_path = resolve_module_path(module_name)

		if full_path is None:
			return res.failure(RTError(
				node.pos_start, node.pos_end,
				f"Módulo '{module_name}' não encontrado",
				context
			))

		key = os.path.normcase(os.path.abspath(full_path))
		if key in MODULE_CACHE:
			return res.success(MODULE_CACHE[key])

		if key in MODULES_LOADING:
			return res.failure(RTError(
				node.pos_start, node.pos_end,
				f"Importação circular detectada em '{module_name}'",
				context
			))

		try:
			with open(full_path, 'r', encoding='utf-8') as f:
				text = f.read()
		except Exception as e:
			return res.failure(RTError(
				node.pos_start, node.pos_end,
				f"Falha ao ler o módulo '{module_name}': {e}",
				context
			))

		MODULES_LOADING.add(key)
		try:
			_, error, module_ctx = run(str(full_path), text)
		finally:
			MODULES_LOADING.discard(key)

		if error:
			return res.failure(RTError(
				node.pos_start, node.pos_end,
				f"Erro no módulo '{module_name}': {error.as_string()}",
				context
			))

		MODULE_CACHE[key] = module_ctx
		return res.success(module_ctx)

	def visit_ImportNode(self, node, context):
		res = RTResult()
		module_name = node.file_path.value

		module_ctx = res.register(self._load_module(module_name, node, context))
		if res.error: return res

		for func_tok in node.functions:
			func_name = func_tok.value
			func_value = module_ctx.symbol_table.get(func_name)
			func_const = module_ctx.symbol_table.is_constant(func_name)

			if module_ctx.symbol_table.is_private(func_name):
				return res.failure(RTError(
					node.pos_start, node.pos_end,
					f"'{func_name}' é privado e não pode ser importado",
					context
				))
			if func_value is None:
				return res.failure(RTError(
					node.pos_start, node.pos_end,
					f"'{func_name}' não foi encontrado no módulo '{module_name}'",
					context
				))
			context.symbol_table.set(func_name, func_value, func_const)

		return res.success(Number.null)

	def visit_ImportNamespaceNode(self, node: ImportNamespaceNode, context):
		res = RTResult()
		module_name = node.module_path.value
		pos_start = node.pos_start

		module_ctx = res.register(self._load_module(module_name, node, context))
		if res.error: return res

		namespace = Dict([]).set_context(context).set_pos(pos_start, node.pos_end)
		for name in module_ctx.symbol_table.symbols:
			if not module_ctx.symbol_table.is_private(name):
				value = module_ctx.symbol_table.get(name)
				namespace.elements.append((
					Token(TT_IDENTIFIER, name, node.pos_start, node.pos_end),
					value.copy()
				))

		context.symbol_table.set(module_name, namespace)
		return res.success(Number.null)

	def visit_FuncDefNode(self, node, context):
		res = RTResult()

		func_name = node.var_name_tok.value if node.var_name_tok else None
		body_node = node.body_node
		arg_names = [arg_name.value for arg_name in node.arg_name_toks]
		func_value = Function(func_name, body_node, arg_names, node.should_auto_return, arg_defaults=node.default_vals, arg_types=node.arg_types, return_type=node.return_type).set_context(context).set_pos(node.pos_start, node.pos_end)
		func_value.arg_defaults = [node.default_vals[i] for i in range(len(node.default_vals))]

		if node.var_name_tok:
			context.symbol_table.set(func_name, func_value, private=node.private)

		return res.success(func_value)
	
	def visit_CallNode(self, node, context):		
		res = RTResult()
		args = []

		value_to_call = res.register(self.visit(node.node_to_call, context))
		if res.should_return(): return res
		if not isinstance(value_to_call, (BaseFunction, Class, Instance, SuperRef)):
			return res.failure(RTError(
				node.pos_start, node.pos_end,
				f"'{value_to_call}' não pode ser executado",
				context
			))
		value_to_call = value_to_call.copy().set_pos(node.pos_start, node.pos_end)

		for arg_node in node.arg_nodes:
			args.append(res.register(self.visit(arg_node, context)))
			if res.should_return(): return res

		return_value = res.register(value_to_call.execute(args))
		if res.should_return(): return res

		return res.success(return_value)
	
	def visit_IfNode(self, node, context):
		res = RTResult()

		expr_value = Number.null

		for condition, expr, should_return_null in node.cases:
			condition_value = res.register(self.visit(condition, context))
			if res.should_return(): return res

			if condition_value.is_true():
				expr_value = res.register(self.visit(expr, context))
				if res.should_return(): return res
				return res.success(Number.null if should_return_null else expr_value)

		if node.else_case:
			expr, should_return_null = node.else_case
			expr_value = res.register(self.visit(expr, context))
		
		if res.should_return(): return res
		return res.success(Number.null if should_return_null else expr_value)

	def visit_BinOpNode(self, node, context):
		res = RTResult()
		left = res.register(self.visit(node.left_node, context))
		if res.should_return(): return res
		right = res.register(self.visit(node.right_node, context))
		if res.should_return(): return res

		op_tok = node.op_tok
		method_name = BINOP_BY_TYPE.get(op_tok.type)
		if method_name is None and op_tok.type == TT_KEYWORD:
			method_name = BINOP_BY_KEYWORD.get(op_tok.value)
		if method_name is None:
			return res.failure(RTError(node.pos_start, node.pos_end, f"Operador desconhecido: {op_tok}", context))
		result, error = getattr(left, method_name)(right)

		if error:
			return res.failure(error)
		else:
			return res.success(result.set_pos(node.pos_start, node.pos_end))

	def visit_UnaryOpNode(self, node, context):
		res = RTResult()
		number = res.register(self.visit(node.node, context))
		if res.should_return(): return res

		error = None

		if node.op_tok.type == TT_MINUS:
			number, error = number.multed_by(Number(-1))
		elif node.op_tok.matches(TT_KEYWORD, 'não'):
			number, error = number.notted()

		if error:
			return res.failure(error)
		else:
			return res.success(number.set_pos(node.pos_start, node.pos_end))
	
	def visit_ForNode(self, node, context):
		elements = []
		res = RTResult()
		var_name = node.var_name_tok.value
		start_value = res.register(self.visit(node.start_value_node, context))
		if res.should_return(): return res

		end_value = res.register(self.visit(node.end_value_node, context))
		if res.should_return(): return res

		if node.step_value_node:
			step_value = res.register(self.visit(node.step_value_node, context))
			if res.should_return(): return res
		else:
			step_value = Number(1).set_context(context).set_pos(node.pos_start, node.pos_end)

		i = start_value.value

		if step_value.value >= 0:
			condition = lambda i: i < end_value.value
		else:
			condition = lambda i: i > end_value.value

		while condition(i):
			context.symbol_table.set(var_name, Number(i))
			i += step_value.value

			value = (res.register(self.visit(node.body_node, context)))
			if res.should_return() and res.loop_should_break == False and res.loop_should_continue == False: return res

			if res.loop_should_continue:
				continue
			elif res.loop_should_break:
				break

			elements.append(value)

		return res.success(Number.null if node.should_return_null else List(elements).set_context(context).set_pos(node.pos_start, node.pos_end))

	
	def visit_ForEachNode(self, node, context):
		res = RTResult()
		elements = []
		
		iterable = res.register(self.visit(node.iterable_node, context))
		if res.error: return res
		
		var_names = [tok.value for tok in node.var_name_tok]
		
		if not isinstance(iterable, (List, Tuple, Set, Dict)):
			return res.failure(RTError(
				node.pos_start, node.pos_end,
				"Iterável deve ser lista, tuple, mesa ou dicionário",
				context
			))
			
		items = iterable.elements
		single = False

		if isinstance(iterable, Tuple):
			for item in items:
				if len(var_names) == 1:
					context.symbol_table.set(var_names[0], item.copy())
				else:
					for var_name, element in zip(var_names, items):
						context.symbol_table.set(var_name, element.copy())
						single = True
				
				value = res.register(self.visit(node.body_node, context))
				if res.should_return() and not res.loop_should_continue and not res.loop_should_break:
					return res
					
				if res.loop_should_continue:
					continue
					
				if res.loop_should_break:
					break

				if single == True:
					elements.append(value)
					break
					
				elements.append(value)
		else:
			for item in items:
				if isinstance(item, tuple) and isinstance(iterable, Dict) and len(var_names) == len(item):
					for var_name, element in zip(var_names, item):
						context.symbol_table.set(var_name, element.copy())
				elif isinstance(iterable, Dict):
					for var_name in var_names:
						context.symbol_table.set(var_name, Tuple(item).set_context(context).set_pos(node.pos_start, node.pos_end))
				elif isinstance(item, (Tuple, List)) and len(var_names) == len(item.elements):
					for var_name, element in zip(var_names, item.elements):
						context.symbol_table.set(var_name, element.copy())
				else:
					for name in var_names:
						context.symbol_table.set(name, item.copy())
				
				value = res.register(self.visit(node.body_node, context))
				if res.should_return() and not res.loop_should_continue and not res.loop_should_break:
					return res
					
				if res.loop_should_continue:
					continue
					
				if res.loop_should_break:
					break
					
				elements.append(value)
		
		return res.success(Number.null if node.should_return_null else List(elements))


	def visit_WhileNode(self, node, context):
		res = RTResult()
		elements = []

		while True:
			condition = res.register(self.visit(node.condition_node, context))
			if res.should_return(): return res

			if not condition.is_true(): break

			value = (res.register(self.visit(node.body_node, context)))
			if res.should_return() and res.loop_should_break == False and res.loop_should_continue == False: return res

			if res.loop_should_break:
				break
			elif res.loop_should_continue:
				continue

			elements.append(value)

		return res.success(Number.null if node.should_return_null else List(elements).set_context(context).set_pos(node.pos_start, node.pos_end))

	def visit_ReturnNode(self, node, context):
		res = RTResult()
		values = []

		if node.node_to_return and node.node_to_return != [None]:
			for value_node in node.node_to_return:
				values.append(res.register(self.visit(value_node, context) if value_node else Nulo().set_context(context).set_pos(node.pos_start, node.pos_end)))
				if res.should_return(): return res

			return_value = List(values) if len(values) > 1 else values[0] if values else Number.null

			return res.success_return(return_value)
		else:
			return res.success_return(Nulo().set_context(context).set_pos(node.pos_start, node.pos_end))
	
	def visit_ContinueNode(self, node, context):
		return RTResult().success_continue()
	
	def visit_BreakNode(self, node, context):
		return RTResult().success_break()
