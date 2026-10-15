"""Funções nativas (falar, pegar, len, ...)."""

import difflib
import os
import random
import string
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

from .config import DANGEROUS_BUILTINS, STATE
from .errors import RTError, ValorError
from .tokens import TT_IDENTIFIER, Token
from .context import RTResult
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
	Tuple,
	python_to_value,
)


class BuiltInFunction(BaseFunction):
	def __init__(self, name):
		super().__init__(name)
		self.obj = None
	
	def execute(self, args):
		res = RTResult()
		exec_ctx = self.generate_new_context()

		if STATE.safe_mode and self.name in DANGEROUS_BUILTINS:
			return res.failure(RTError(
				self.pos_start, self.pos_end,
				f"A função '{self.name}' está bloqueada no modo seguro (--seguro)",
				exec_ctx
			))

		method_name = f'execute_{self.name}'
		method = getattr(self, method_name, None)
		if method is None:
			return res.failure(RTError(
				self.pos_start, self.pos_end,
				f"A função nativa '{self.name}' ainda não foi implementada no interpretador",
				exec_ctx
			))

		evaluated_args = None
		if hasattr(method, 'default_args'):
			evaluated_args = []
			for i in range(len(method.arg_names)):
				if i < len(args):
					evaluated_args.append(args[i])
				else:
					if i < len(method.default_args) and method.default_args[i] is not None:
						evaluated_args.append(method.default_args[i])
					else:
						return res.failure(RTError(
							self.pos_start, self.pos_end,
							f"Faltando argumento para '{self.arg_names[i]}'",
							exec_ctx
						))

		res.register(self.check_and_populate_args(method.arg_names, evaluated_args or args, exec_ctx))
		if res.should_return(): return res

		return_value = res.register(method(exec_ctx))
		if res.should_return(): return res
		return res.success(return_value)

	def no_visit_method(self, node, context):
		raise Exception(f'Nenhum execute_{self.name} metódo encontrado')

	def copy(self):
		copy = BuiltInFunction(self.name)
		copy.set_context(self.context)
		copy.set_pos(self.pos_start, self.pos_end)
		copy.obj = self.obj
		copy.properties = self.properties
		return copy

	def __repr__(self):
		return f"< função predefinida {self.name} em (<stdlib>) >"
	
	def execute_list_mudar(self, exec_ctx):
		lst = self.obj
		if not isinstance(lst, List):
			return RTResult().failure(RTError(
				self.pos_start, self.pos_end,
				f"'{lst}' não é uma lista.",
				exec_ctx
			))
		
		index = exec_ctx.symbol_table.get('index')
		value = exec_ctx.symbol_table.get('value')

		try:
			lst.elements[int(index.value)] = value
			return RTResult().success(value)
		except:
			return RTResult().failure(RTError(
				self.pos_start, self.pos_end,
				f"Indice '{index}' fora do intervalo, index não existe.",
				exec_ctx
			))
	execute_list_mudar.arg_names = ['index', 'value']

	def execute_dict_extender(self, exec_ctx):
		dictA = self.obj
		dictB = exec_ctx.symbol_table.get('dictB')

		if not isinstance(dictA, Dict):
			return RTResult().failure(RTError(
				self.pos_start, self.pos_end,
				"Primeiro argumento deve ser um dicionário",
				exec_ctx
			))

		if not isinstance(dictB, Dict):
			return RTResult().failure(RTError(
				self.pos_start, self.pos_end,
				"Segundo argumento deve ser um dicionário",
				exec_ctx
			))

		dictA.values.update(dictB.values)
		return RTResult().success(Dict(dictA.values).set_context(exec_ctx).set_pos(self.pos_start, self.pos_end))
	execute_dict_extender.arg_names = ['dictB']

	def execute_dict_mudar(self, exec_ctx):
		res = RTResult()
		key = exec_ctx.symbol_table.get('key')
		value = exec_ctx.symbol_table.get('value')

		if not isinstance(key, String):
			return res.failure(RTError(
				self.pos_start, self.pos_end,
				"Primeiro argumento deve ser uma string",
				exec_ctx
			))

		f = False
		for i, (k, v) in enumerate(self.obj.elements):
			if k.value == key.value:
				self.obj.elements[i] = (k, value)
				f = True
				break
		if not f:
			self.obj.elements.append((key, value))
		
		return RTResult().success(self.obj)

	execute_dict_mudar.arg_names = ['key', 'value']
		
	def execute_falar(self, exec_ctx):
		print(str(exec_ctx.symbol_table.get('value')))
		return RTResult().success(String(str(exec_ctx.symbol_table.get('value'))))
	execute_falar.arg_names = ['value']

	def execute_pegar(self, exec_ctx):
		lst = exec_ctx.symbol_table.get('list')
		if not isinstance(lst, List):
			return RTResult().failure(RTError(
				self.pos_start, self.pos_end,
				f"'{lst}' não é uma lista.",
				exec_ctx
			))
		index = exec_ctx.symbol_table.get('index')
		if not isinstance(index, Number):
			return RTResult().failure(RTError(
				self.pos_start, self.pos_end,
				f"'{index}' não é um número.",
				exec_ctx
			))
		try:
			return RTResult().success(lst.elements[int(index.value)])
		except:
			return RTResult().failure(RTError(
				self.pos_start, self.pos_end,
				f"Indice '{index}' fora do intervalo, index não existe.",
				exec_ctx
			))
	execute_pegar.arg_names = ['list', 'index']
	
	def execute_len(self, exec_ctx):
		val = exec_ctx.symbol_table.get('value')
		if isinstance(val, List):
			return RTResult().success(Number(len(val.elements)).set_context(exec_ctx).set_pos(self.pos_start, self.pos_end))
		elif isinstance(val, String):
			return RTResult().success(Number(len(val.value)).set_context(exec_ctx).set_pos(self.pos_start, self.pos_end))
		else:
			return RTResult().failure(RTError(
				self.pos_start, self.pos_end,
				f"'{val}' não é uma lista ou uma string.",
				exec_ctx
			))
	execute_len.arg_names = ['value']

	def execute_list_procurar(self, exec_ctx):
		lst = self.obj
		val = exec_ctx.symbol_table.get('value')

		for i in lst.elements:
			if val.value == i.value:
				return RTResult().success(Number(lst.elements.index(i)))

		return RTResult().success(Number(-1))
	execute_list_procurar.arg_names = ['value']

	def execute_list_colocar(self, exec_ctx):
		lst = self.obj
		val = exec_ctx.symbol_table.get('value')
		index = exec_ctx.symbol_table.get('index')

		if index.value == -1:
			lst.elements.append(val)
		else:
			try:
				lst.elements.insert(int(index.value), val)
			except:
				return RTResult().failure(RTError(
					self.pos_start, self.pos_end,
					f"Indice '{index}' fora do intervalo, index não existe.",
					exec_ctx
				))

		return RTResult().success(lst)
	execute_list_colocar.arg_names = ['value', 'index']
	execute_list_colocar.default_args = [None, Number(-1)]

	def execute_list_estourar(self, exec_ctx):
		lst = self.obj
		index = exec_ctx.symbol_table.get('index')

		try:
			return RTResult().success(lst.elements.pop(int(index.value)))
		except:
			return RTResult().failure(RTError(
				self.pos_start, self.pos_end,
				f"Indice '{index}' fora do intervalo, index não existe.",
				exec_ctx
			))
	execute_list_estourar.arg_names = ['index']
	execute_list_estourar.default_args = [Number(-1)]

	def execute_perguntar(self, exec_ctx):
		text = input(exec_ctx.symbol_table.get('prompt').value)
		return RTResult().success(String(text))
	execute_perguntar.arg_names = ['prompt']
	execute_perguntar.default_args = [String('')]

	def execute_input_int(self, exec_ctx):
		while True:
			text = input(exec_ctx.symbol_table.get('prompt').value)
			try:
				number = int(text)
				return RTResult().success(Number(number))
			except ValueError:
				print(f"'{text}' nao é um número.")
				continue
	execute_input_int.arg_names = ['prompt']
	
	def execute_número(self, exec_ctx):
		value = exec_ctx.symbol_table.get('value')

		if isinstance(value, Number):
			return RTResult().success(value)
		elif isinstance(value, (String, Boolean, Nulo)):
			try:
				return RTResult().success(Number(int(value.value)))
			except ValueError:
				return RTResult().failure(ValorError(
					self.pos_start, self.pos_end,
					f"'{value}' não pode ser convertido para número.",
					exec_ctx
				))
		elif isinstance(value, (List, Dict, Tuple, Set)):
			return RTResult().failure(ValorError(
				self.pos_start, self.pos_end,
				f"'{value}' não pode ser convertido para número.",
				exec_ctx
			))
		else:
			return RTResult().failure(ValorError(
				self.pos_start, self.pos_end,
				f"'{value}' não pode ser convertido para número.",
				exec_ctx
			))
	execute_número.arg_names = ['value']

	def execute_num(self, exec_ctx):
		if isinstance(exec_ctx.symbol_table.get('value'), Number):
			return RTResult().success(Boolean(1))
		else:
			return RTResult().success(Number.false)
	execute_num.arg_names = ['value']
	
	def execute_str(self, exec_ctx):
		res = RTResult()
		val = exec_ctx.symbol_table.get('value')

		if isinstance(val, String):
			return res.success(val)
		elif isinstance(val, Number):
			return res.success(String(str(val.value)))
		elif isinstance(val, Boolean):
			return res.success(String(str(val.value)))
		elif isinstance(val, List):
			return res.success(String(str(val.elements)))
		elif isinstance(val, Dict):
			return res.success(String(str(val.elements)))
		elif isinstance(val, Tuple):
			return res.success(String(str(val.elements)))
		elif isinstance(val, Set):
			return res.success(String(str(val.elements)))
		elif isinstance(val, BaseFunction):
			return res.success(String(str(val)))
		elif isinstance(val, Nulo):
			return res.success(String(str(val.value)))
		else:
			return res.failure(RTError(
				self.pos_start, self.pos_end,
				f"'{val}' não pode ser convertido para 'string'.",
				exec_ctx
			))

	execute_str.arg_names = ['value']
	
	def execute_string(self, exec_ctx):
		return RTResult().success(Boolean(int(isinstance(exec_ctx.symbol_table.get('value'), String))))
	execute_string.arg_names = ['value']

	def execute_type(self, exec_ctx):
		if isinstance(exec_ctx.symbol_table.get('value'), Number):
			return RTResult().success(String('número'))
		elif isinstance(exec_ctx.symbol_table.get('value'), String):
			return RTResult().success(String('string'))
		elif isinstance(exec_ctx.symbol_table.get('value'), List):
			return RTResult().success(String('lista'))
		elif isinstance(exec_ctx.symbol_table.get('value'), Function):
			return RTResult().success(String('função'))
		elif isinstance(exec_ctx.symbol_table.get('value'), Dict):
			return RTResult().success(String('dicionário'))
		elif isinstance(exec_ctx.symbol_table.get('value'), Boolean):
			return RTResult().success(String(String(exec_ctx.symbol_table.get('value').value)))
		elif isinstance(exec_ctx.symbol_table.get('value'), Tuple):
			return RTResult().success(String('tupla'))
		elif isinstance(exec_ctx.symbol_table.get('value'), Nulo):
			return RTResult().success(String('nulo'))
		elif isinstance(exec_ctx.symbol_table.get('value'), (Set)):
			return RTResult().success(String('mesa'))
		elif isinstance(exec_ctx.symbol_table.get('value'), Instance):
			return RTResult().success(String(exec_ctx.symbol_table.get('value').class_.name))
		elif isinstance(exec_ctx.symbol_table.get('value'), Class):
			return RTResult().success(String(exec_ctx.symbol_table.get('value').name))
		else:
			return RTResult().success(Number.null)

	execute_type.arg_names = ['value']
	
	def execute_lista(self, exec_ctx):
		return RTResult().success(Boolean(int(isinstance(exec_ctx.symbol_table.get('value'), List))))
	execute_lista.arg_names = ['value']
	
	def execute_func(self, exec_ctx):
		return RTResult().success(Boolean(int(isinstance(exec_ctx.symbol_table.get('value'), Function))))
	execute_func.arg_names = ['value']

	def execute_string_picotar(self, exec_ctx):
		val = self.obj
		if isinstance(val, String):
			return RTResult().success(List(self.obj.value.split()))
		else:
			return RTResult().failure(RTError(
				self.pos_start, self.pos_end,
				f"'{self.obj}' não é uma string.",
				exec_ctx
			))
	execute_string_picotar.arg_names = []

	def execute_string_limpar(self, exec_ctx):
		if isinstance(self.obj, String):
			return RTResult().success(List(self.obj.value.strip()))
		else:
			return RTResult().failure(RTError(
				self.pos_start, self.pos_end,
				f"'{self.obj}' não é uma string.",
				exec_ctx
			))
	execute_string_limpar.arg_names = []

	def execute_list_extender(self, exec_ctx):
		listA = self.obj
		listB = exec_ctx.symbol_table.get("listB")

		if not isinstance(listA, List):
			return RTResult().failure(RTError(
				self.pos_start, self.pos_end,
				"Primeiro argumento deve ser uma lista",
				exec_ctx
			))

		if not isinstance(listB, List):
			return RTResult().failure(RTError(
				self.pos_start, self.pos_end,
				"Segundo argumento deve ser uma lista",
				exec_ctx
			))

		listA.elements.extend(listB.elements)
		return RTResult().success(List(listA.elements).set_context(exec_ctx).set_pos(self.pos_start, self.pos_end))
	execute_list_extender.arg_names = ["listB"]

	def execute_quadrado(self, exec_ctx):
		if isinstance(exec_ctx.symbol_table.get('value'), Number):
			return RTResult().success(Number(exec_ctx.symbol_table.get('value').value ** 2))
		else:
			return RTResult().failure(RTError(
				self.pos_start, self.pos_end,
				f"'{exec_ctx.symbol_table.get('value')}' não é um número.",
				exec_ctx
			))
	execute_quadrado.arg_names = ['value']

	def execute_cubo(self, exec_ctx):
		if isinstance(exec_ctx.symbol_table.get('value'), Number):
			return RTResult().success(Number(exec_ctx.symbol_table.get('value').value ** 3))
		else:
			return RTResult().failure(RTError(
				self.pos_start, self.pos_end,
				f"'{exec_ctx.symbol_table.get('value')}' não é um número.",
				exec_ctx
			))
	execute_cubo.arg_names = ['value']

	def execute_raiz(self, exec_ctx):
		if isinstance(exec_ctx.symbol_table.get('value'), Number):
			return RTResult().success(Number(exec_ctx.symbol_table.get('value').value ** (1/2)))
		else:
			return RTResult().failure(RTError(
				self.pos_start, self.pos_end,
				f"'{exec_ctx.symbol_table.get('value')}' não é um número.",
				exec_ctx
			))
	execute_raiz.arg_names = ['value']

	def execute_string_fatiar(self, exec_ctx):
		value = self.obj
		
		if not isinstance(value, String):
			return RTResult().failure(RTError(
				self.pos_start, self.pos_end,
				f"'{value}' não é uma string",
				exec_ctx
			))
		
		chars = [String(char) for char in value.value]
		return RTResult().success(List(chars).set_context(exec_ctx).set_pos(self.pos_start, self.pos_end))
	execute_string_fatiar.arg_names = []

	def execute_string_minúsculo(self, exec_ctx):
		if isinstance(self.obj, String):
			return RTResult().success(String(self.obj.value.lower()).set_pos(self.pos_start, self.pos_end).set_context(exec_ctx))
		else:
			return RTResult().failure(RTError(
				self.pos_start, self.pos_end,
				f"'{self.obj}' não é uma string.",
				exec_ctx
			))
	execute_string_minúsculo.arg_names = []
	
	def execute_string_maiúsculo(self, exec_ctx):
		if isinstance(self.obj, String):
			return RTResult().success(String(self.obj.value.upper()).set_pos(self.pos_start, self.pos_end).set_context(exec_ctx))
		else:
			return RTResult().failure(RTError(
				self.pos_start, self.pos_end,
				f"'{self.obj}' não é uma string.",
				exec_ctx
			))
	execute_string_maiúsculo.arg_names = []

	def execute_aleatório(self, exec_ctx):
		if isinstance(exec_ctx.symbol_table.get('value'), Number) and isinstance(exec_ctx.symbol_table.get('max'), Number):
			return RTResult().success(Number(random.randint(int(exec_ctx.symbol_table.get('value').value), int(exec_ctx.symbol_table.get('max').value))))
		else:
			return RTResult().failure(RTError(
				self.pos_start, self.pos_end,
				f"'{exec_ctx.symbol_table.get('value')}' ou '{exec_ctx.symbol_table.get('max')}' não é um número.",
				exec_ctx
			))
	execute_aleatório.arg_names = ['value', 'max']

	def execute_ler_arquivo(self, exec_ctx):
		caminho = exec_ctx.symbol_table.get('caminho').value
		try:
			with open(caminho, 'r', encoding='utf-8') as f:
				return RTResult().success(String(f.read()))
		except Exception as e:
			return RTResult().failure(RTError(
				self.pos_start, self.pos_end,
				f"Erro ao ler arquivo: {str(e)}",
				exec_ctx
			))
	execute_ler_arquivo.arg_names = ['caminho']

	def execute_escrever_arquivo(self, exec_ctx):
		caminho = exec_ctx.symbol_table.get('caminho').value
		conteúdo = exec_ctx.symbol_table.get('conteúdo').value
		try:
			with open(caminho, 'w', encoding='utf-8') as f:
				f.write(str(conteúdo))
			return RTResult().success(Number.true)
		except Exception as e:
			return RTResult().failure(RTError(
				self.pos_start, self.pos_end,
				f"Erro ao escrever arquivo: {str(e)}",
				exec_ctx
			))
	execute_escrever_arquivo.arg_names = ['caminho', 'conteúdo']

	def execute_clicommand(self, exec_ctx):
		res = RTResult()
		comando = exec_ctx.symbol_table.get('comando')
		
		if not isinstance(comando, String):
			return res.failure(RTError(
				self.pos_start, self.pos_end,
				"Argumento deve ser uma string",
				exec_ctx
			))
		
		try:
			resultado = subprocess.run(
				comando.value,
				shell=True,
				capture_output=True,
				text=True,
				timeout=30,
				encoding='utf-8',
				errors='replace'
			)
			
			output = resultado.stdout.strip()
			if resultado.returncode != 0:
				return res.failure(RTError(self.pos_start, self.pos_end, f"\n[ERRO {resultado.returncode}] {resultado.stderr.strip()}"))
			
			return res.success(String(output))
			
		except subprocess.TimeoutExpired:
			return res.failure(RTError(
				self.pos_start, self.pos_end,
				"Timeout: Comando excedeu 30 segundos",
				exec_ctx
			))
		except Exception as e:
			return res.failure(RTError(
				self.pos_start, self.pos_end,
				f"Erro na execução: {str(e)}",
				exec_ctx
			))

	execute_clicommand.arg_names = ['comando']

	def execute_eval(self, exec_ctx):
		from .runtime import run  # import tardio (evita ciclo)
		res = RTResult()
		comando = exec_ctx.symbol_table.get('comando')
		
		if not isinstance(comando, String):
			return res.failure(RTError(
				self.pos_start, self.pos_end,
				"Argumento deve ser uma string",
				exec_ctx
			))
		
		try:
			rs, err, exec_ctx = run('<eval_expr>', comando.value)
			if err: return res.failure(err)
			return res.success(rs)
		except Exception as e:
			return res.failure(RTError(
				self.pos_start, self.pos_end,
				f"Erro na execução: {str(e)}",
				exec_ctx
			))

	execute_eval.arg_names = ['comando']

	def execute_python(self, exec_ctx):
		res = RTResult()
		comando = exec_ctx.symbol_table.get('comando')
		
		if not isinstance(comando, String):
			return res.failure(RTError(
				self.pos_start, self.pos_end,
				"Argumento deve ser uma string",
				exec_ctx
			))
		
		try:
			return res.success(python_to_value(eval(comando.value)))
		except Exception as e:
			return res.failure(RTError(
				self.pos_start, self.pos_end,
				f"Erro na execução: {str(e)}",
				exec_ctx
			))

	execute_python.arg_names = ['comando']

	def execute_list_invertida(self, exec_ctx):
		return RTResult().success(List(
			self.obj.elements[::-1]
		).set_context(exec_ctx).set_pos(self.pos_start, self.pos_end))
	execute_list_invertida.arg_names = []

	def execute_dict_keys(self, exec_ctx):
		return RTResult().success(List(
			[String(k.value) for k, _ in self.obj.elements]
		))
	execute_dict_keys.arg_names = []

	def execute_dict_values(self, exec_ctx):
		return RTResult().success(List(
			[v.copy() for _, v in self.obj.elements]
		))
	execute_dict_values.arg_names = []

	def execute_dict_items(self, exec_ctx):
		return RTResult().success(List([
			List([String(k.value), v.copy()]) for k, v in self.obj.elements
		]))
	execute_dict_items.arg_names = []

	def execute_update(self, exec_ctx):
		obj = exec_ctx.symbol_table.get("obj")
		other = exec_ctx.symbol_table.get("other")

		if not isinstance(obj, Dict):
			return RTResult().failure(RTError(
				self.pos_start, self.pos_end,
				"Primeiro argumento deve ser um dicionário",
				exec_ctx
			))

		if not isinstance(other, Dict):
			return RTResult().failure(RTError(
				self.pos_start, self.pos_end,
				"Segundo argumento deve ser um dicionário",
				exec_ctx
			))

		obj.elements.extend((k, v) for k, v in other.elements)
		return RTResult().success(Dict(obj.elements).set_context(exec_ctx).set_pos(self.pos_start, self.pos_end))
	execute_update.arg_names = ['obj', 'other']

	def execute_esperar(self, exec_ctx):
		tempo = exec_ctx.symbol_table.get("time")
		if not isinstance(tempo, Number):
			return RTResult().failure(RTError(
				self.pos_start, self.pos_end,
				f"Tempo não é um número, mas sim {type(tempo)}",
				exec_ctx
			))

		time.sleep(float(tempo.value))
		return RTResult().success(Number.null)

	execute_esperar.arg_names = ["time"]
	execute_esperar.default_args = [Number(1)]

	def execute_bomba_exit(self, exec_ctx):
		res = RTResult()
		sys.exit(exec_ctx.symbol_table.get('value'))
	execute_bomba_exit.arg_names = ['value']
	execute_bomba_exit.default_args = [Number(0)]

	def execute_list_map(self, exec_ctx):
		res = RTResult()
		lista = self.obj
		func = exec_ctx.symbol_table.get('func')

		if not isinstance(func, BaseFunction):
			return res.failure(RTError(
				self.pos_start, self.pos_end,
				"Argumento deve ser uma função",
				exec_ctx
			))

		self.obj.elements = ([func.set_context(exec_ctx).execute([arg]).value for arg in lista.elements.copy()])
		if res.should_return(): return res
		return res.success(self.obj)

	execute_list_map.arg_names = ['func']

	def execute_any_is_callable(self, exec_ctx):
		return RTResult().success(Number.true if self.obj.executable else Number.false)
	execute_any_is_callable.arg_names = []
	
	def execute_is_callable(self, exec_ctx):
		return RTResult().success(Number.true if (exec_ctx.symbol_table.get('value').executable) else Number.false)
	execute_is_callable.arg_names = ['value']

	def execute_list_filtrar(self, exec_ctx):
		res = RTResult()
		lista = self.obj
		func = exec_ctx.symbol_table.get('func')
		
		if not isinstance(func, BaseFunction):
			return res.failure(RTError(
				self.pos_start, self.pos_end,
				"Argumento deve ser uma função",
				exec_ctx
			))
		
		new_elements = []
		for idx, element in enumerate(lista.elements):
			# Passa índice e elemento para a função
			if len(func.arg_names) > 1:
				args = [Number(idx), element.copy()]
			else:
				args = [element.copy()]
			condition = res.register(func.execute(args))
			if res.should_return(): return res
			
			if condition.is_true():
				new_elements.append(element.copy())
		
		return res.success(List(new_elements).set_context(exec_ctx).set_pos(self.pos_start, self.pos_end))
	execute_list_filtrar.arg_names = ['func']


	def execute_list_reduzir(self, exec_ctx):
		res = RTResult()
		lista = self.obj
		func = exec_ctx.symbol_table.get('func')
		acumulador = exec_ctx.symbol_table.get('inicial')
		
		if not isinstance(func, BaseFunction):
			return res.failure(RTError(
				self.pos_start, self.pos_end,
				"Primeiro argumento deve ser uma função",
				exec_ctx
			))
		
		if not lista.elements:
			return res.success(acumulador.copy() if acumulador else Number.null)
		
		start_idx = 0
		if isinstance(acumulador, Nulo):
			acumulador = lista.elements[0].copy()
			start_idx = 1
		
		for i in range(start_idx, len(lista.elements)):
			args = [acumulador.copy(), lista.elements[i].copy()]
			acumulador = res.register(func.execute(args))
			if res.should_return(): return res
		
		return res.success(acumulador)
	execute_list_reduzir.arg_names = ['func', 'inicial']
	execute_list_reduzir.default_args = [Nulo()]

	def execute_list_ordenar(self, exec_ctx):
		res = RTResult()
		lista = self.obj
		func = exec_ctx.symbol_table.get('func')

		if isinstance(func, Nulo):
			try:
				sorted_list = sorted(lista.elements, key=lambda x: x.value)
				return res.success(List(sorted_list))
			except:
				return res.failure(RTError(
					self.pos_start, self.pos_end,
					"Não é possível ordenar elementos de tipos diferentes",
					exec_ctx
				))
		
		if not isinstance(func, BaseFunction):
			return res.failure(RTError(
				self.pos_start, self.pos_end,
				"Argumento deve ser uma função",
				exec_ctx
			))
		
		n = len(lista.elements)
		sorted_elements = [elem.copy() for elem in lista.elements]
		
		for i in range(n):
			for j in range(0, n-i-1):
				args = [sorted_elements[j].copy(), sorted_elements[j+1].copy()]
				comparison = res.register(func.execute(args))
				if res.should_return(): return res
				
				if comparison.value > 0:
					sorted_elements[j], sorted_elements[j+1] = sorted_elements[j+1], sorted_elements[j]
		
		return res.success(List(sorted_elements))
	execute_list_ordenar.arg_names = ['func']
	execute_list_ordenar.default_args = [Nulo()]

	def execute_list_agrupar(self, exec_ctx):
		res = RTResult()
		lista = self.obj
		func = exec_ctx.symbol_table.get('func')
		
		if not isinstance(func, BaseFunction):
			return res.failure(RTError(
				self.pos_start, self.pos_end,
				"Argumento deve ser uma função",
				exec_ctx
			))
		
		groups = {}
		for idx, element in enumerate(lista.elements):
			key_val = res.register(func.execute([element.copy()]))
			if res.should_return(): return res
			
			key = str(key_val)
			if key not in groups:
				groups[key] = []
			groups[key].append(element.copy())
		
		group_dict = Dict([])
		for key, values in groups.items():
			group_dict.elements.append((
				Token(TT_IDENTIFIER, key, self.pos_start, self.pos_end),
				List(values)
			))
		
		return res.success(group_dict)
	execute_list_agrupar.arg_names = ['func']

	def execute_any_tamanho(self, exec_ctx):
		if isinstance(self.obj, (Class, Instance, Boolean, Nulo)):
			return RTResult().failure(ValorError(
				self.pos_start, self.pos_end,
				f"Tipo {type(self.obj)} não possui tamanho.",
				exec_ctx
			))
		return RTResult().success(Number(len(self.obj.elements if isinstance(self.obj, (List, Dict, Set, Tuple)) else self.obj.value)).set_context(exec_ctx).set_pos(self.pos_start, self.pos_end))
	execute_any_tamanho.arg_names = []

	def execute_list_todos(self, exec_ctx):
		res = RTResult()
		lista = self.obj
		func = exec_ctx.symbol_table.get('func')
		
		if not isinstance(func, BaseFunction):
			return res.failure(RTError(
				self.pos_start, self.pos_end,
				"Argumento deve ser uma função",
				exec_ctx
			))
		
		for element in lista.elements:
			# Passa o elemento para a função
			condition = res.register(func.execute([element.copy()]))
			if res.should_return(): return res
			
			if not condition.is_true():
				return res.success(Number.false)
		
		return res.success(Number.true)
	execute_list_todos.arg_names = ['func']

	def execute_list_algum(self, exec_ctx):
		res = RTResult()
		lista = self.obj
		func = exec_ctx.symbol_table.get('func')
		
		if not isinstance(func, BaseFunction):
			return res.failure(RTError(
				self.pos_start, self.pos_end,
				"Argumento deve ser uma função",
				exec_ctx
			))
		
		for element in lista.elements:
			condition = res.register(func.execute([element.copy()]))
			if res.should_return(): return res
			
			if condition.is_true():
				return res.success(Number.true)
		
		return res.success(Number.false)
	execute_list_algum.arg_names = ['func']

	def execute_string_começa_com(self, exec_ctx):
		res = RTResult()
		string = self.obj
		substring = exec_ctx.symbol_table.get('substring')
		
		if not isinstance(substring, String):
			return res.failure(RTError(
				self.pos_start, self.pos_end,
				"Argumento deve ser uma string",
				exec_ctx
			))
		
		return res.success(Number.true if string.value.startswith(substring.value) else Number.false)
	execute_string_começa_com.arg_names = ['substring']

	def execute_string_termina_com(self, exec_ctx):
		res = RTResult()
		string = self.obj
		substring = exec_ctx.symbol_table.get('substring')
		
		if not isinstance(substring, String):
			return res.failure(RTError(
				self.pos_start, self.pos_end,
				"Argumento deve ser uma string",
				exec_ctx
			))
		
		return res.success(Number.true if string.value.endswith(substring.value) else Number.false)
	execute_string_termina_com.arg_names = ['substring']

	def execute_numerais(self, exec_ctx):
		try:
			return RTResult().success(List(list(Number(x) for x in range(exec_ctx.symbol_table.get('valor').value))))
		except Exception as e:
			return RTResult().failure(ValorError(
				self.pos_start, self.pos_end,
				f"Erro ao executar numerais: {e}",
				exec_ctx
			))
	execute_numerais.arg_names = ['valor']
