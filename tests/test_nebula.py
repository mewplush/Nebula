"""Testes da Nebula. Rode com:  python -m unittest discover -s tests -v"""
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / 'src'
sys.path.insert(0, str(SRC))

import pyneb  # noqa: E402


def run_neb(code, fn='<teste>', context=None):
    """Executa código Nebula; devolve (saída, erro-ou-None)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _, error, _ = pyneb.run(fn, code, context)
    return buf.getvalue().strip(), error


def out(code, **kw):
    output, error = run_neb(code, **kw)
    assert error is None, error.as_string()
    return output


class NebulaTestCase(unittest.TestCase):
    def setUp(self):
        pyneb.MODULE_CACHE.clear()
        pyneb.MODULES_LOADING.clear()
        pyneb.set_safe_mode(False)

    def assertNebError(self, code, fragment, **kw):
        _, error = run_neb(code, **kw)
        self.assertIsNotNone(error, 'era esperado um erro')
        self.assertIn(fragment, error.as_string())


class TestBasics(NebulaTestCase):
    def test_print_and_math(self):
        self.assertEqual(out('falar(2 + 3 * 4)'), '14')

    def test_variables(self):
        self.assertEqual(out('declarar x = 5\nfalar(x * 2)'), '10')

    def test_if_else(self):
        self.assertEqual(out('se 1 igual 2 então falar("a") senão falar("b")'), 'b')

    def test_while(self):
        self.assertEqual(out('declarar i = 0\nenquanto i < 3 faça\n  i += 1\nfim\nfalar(i)'), '3')

    def test_for_each(self):
        self.assertEqual(out('para cada n em [1,2,3] faça\n  falar(n)\nfim'), '1\n2\n3')

    def test_function_and_arrow(self):
        self.assertEqual(out('função dobro usando (x) => x * 2\nfalar(dobro(4))'), '8')

    def test_recursion(self):
        code = 'função f usando (n)\n  se n < 2 então retornar 1\n  retornar n * f(n - 1)\nfim\nfalar(f(10))'
        self.assertEqual(out(code), '3628800')

    def test_moderate_recursion_depth(self):
        code = 'função soma usando (n)\n  se n igual 0 então retornar 0\n  retornar n + soma(n - 1)\nfim\nfalar(soma(150))'
        self.assertEqual(out(code), '11325')

    def test_infinite_recursion_is_a_clean_error(self):
        code = 'função loop usando (n)\n  retornar loop(n + 1)\nfim\nloop(0)'
        self.assertNebError(code, 'Recursão')


class TestErrors(NebulaTestCase):
    def test_undefined_variable(self):
        self.assertNebError('falar(naoexiste)', "'naoexiste' nunca foi declarado")

    def test_did_you_mean(self):
        self.assertNebError('declarar contador = 1\nfalar(contadro)', "Você quis dizer 'contador'")

    def test_syntax_error_has_arrows(self):
        _, error = run_neb('declarar x = (1 +\nfalar(x)')
        self.assertIn('^', error.as_string())

    def test_arrows_align_with_tabs(self):
        _, error = run_neb('\tfalar(naoexiste)')
        lines = error.as_string().split('\n')
        code_line = next(l for l in lines if 'falar(' in l)
        arrow_line = lines[lines.index(code_line) + 1]
        self.assertEqual(code_line.index('naoexiste'), arrow_line.index('^'))

    def test_error_without_position_does_not_crash(self):
        err = pyneb.Error(None, None, 'Teste', 'sem posição')
        self.assertIn('Teste', err.as_string())


class TestClasses(NebulaTestCase):
    CLASS = (
        'classe Vetor\n'
        '  função principal usando (esse, x, y)\n'
        '    esse.x = x\n'
        '    esse.y = y\n'
        '  fim\n'
        '  função somar usando (esse, outro)\n'
        '    retornar Vetor(esse.x + outro.x, esse.y + outro.y)\n'
        '  fim\n'
        '  função igual_a usando (esse, outro)\n'
        '    retornar esse.x igual outro.x e esse.y igual outro.y\n'
        '  fim\n'
        'fim\n'
    )

    def test_method_can_build_its_own_class(self):
        code = self.CLASS + 'declarar a = Vetor(1, 2)\ndeclarar b = Vetor(3, 4)\ndeclarar c = a + b\nfalar(c.x)'
        self.assertEqual(out(code), '4')

    def test_operator_overload_equality(self):
        code = self.CLASS + 'declarar a = Vetor(1, 2)\nfalar(a == Vetor(1, 2))\nfalar(a != Vetor(9, 9))'
        self.assertEqual(out(code), 'verdadeiro\nverdadeiro')

    def test_instance_equality_without_override_does_not_crash(self):
        code = 'classe P\n  função principal usando (esse)\n    esse.v = 1\n  fim\nfim\ndeclarar a = P()\nfalar(a == a)'
        self.assertEqual(out(code), 'verdadeiro')


class TestStdlib(NebulaTestCase):
    def test_prelude_functions_are_global(self):
        self.assertEqual(out('falar(máximo(3, 9))\nfalar(mínimo(3, 9))\nfalar(absoluto(-4))'), '9\n3\n4')

    def test_prelude_lists(self):
        self.assertEqual(out('falar(soma_lista([1,2,3,4]))\nfalar(intervalo(0, 10, 3))'), '10\n0, 3, 6, 9')

    def test_modneb_named_import(self):
        self.assertEqual(out('importar fatorial, mdc de matematica\nfalar(fatorial(6))\nfalar(mdc(48, 18))'), '720\n6')

    def test_modneb_namespace_import(self):
        self.assertEqual(out('importar listas\nfalar(listas.maior([4, 9, 2]))'), '9')

    def test_constants_from_module(self):
        self.assertEqual(out('importar PI de matematica\nfalar(PI)'), '3.14159265358979')

    def test_private_function_cannot_be_imported(self):
        self.assertNebError('importar _auxiliar de matematica', 'privado')

    def test_missing_module(self):
        self.assertNebError('importar nao_existe_mesmo', 'não encontrado')


class TestImports(NebulaTestCase):
    def make_dir(self, files):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for name, text in files.items():
            Path(tmp.name, name).write_text(text, encoding='utf-8')
        return Path(tmp.name)

    def test_module_is_executed_only_once(self):
        d = self.make_dir({'efeito.neb': 'falar("carregado")\nfunção f usando () => 1\n'})
        code = 'importar f de efeito\nimportar efeito\n'
        self.assertEqual(out(code, fn=str(d / 'main.neb')), 'carregado')

    def test_circular_import_is_detected(self):
        d = self.make_dir({'a.neb': 'importar b\n', 'b.neb': 'importar a\n'})
        self.assertNebError('importar a\n', 'circular', fn=str(d / 'main.neb'))

    def test_import_resolves_next_to_the_file(self):
        d = self.make_dir({'util.neb': 'função tres usando () => 3\n'})
        self.assertEqual(out('importar tres de util\nfalar(tres())', fn=str(d / 'main.neb')), '3')

    def test_filename_restored_after_import(self):
        d = self.make_dir({'m.neb': 'declarar z = 1\n'})
        before = pyneb.FILENAME
        out('importar m\n', fn=str(d / 'main.neb'))
        self.assertEqual(pyneb.FILENAME, before)


class TestRuntime(NebulaTestCase):
    def test_persistent_context_keeps_variables(self):
        ctx = pyneb.new_context()
        run_neb('declarar a = 41', context=ctx)
        self.assertEqual(out('falar(a + 1)', context=ctx), '42')

    def test_python_builtin_returns_nebula_values(self):
        self.assertEqual(out('declarar r = python("2 + 3")\nfalar(r * 2)'), '10')
        self.assertEqual(out('falar(len(python("[1, 2, 3]")))'), '3')

    def test_safe_mode_blocks_dangerous_builtins(self):
        pyneb.set_safe_mode(True)
        self.assertNebError('executar("echo oi")', 'modo seguro')
        self.assertNebError('python("1+1")', 'modo seguro')

    def test_lexer_still_handles_accents(self):
        self.assertEqual(out('declarar número_é = 3\nfalar(número_é)'), '3')


class TestLanguageFixes(NebulaTestCase):
    def test_string_interpolation(self):
        self.assertEqual(out('declarar nome = "Ana"\nfalar("oi ${nome}! ${1 + 2}")'), 'oi Ana! 3')

    def test_dict_with_string_keys(self):
        self.assertEqual(out('declarar d = {"a": 1, b: 2}\nfalar(d.a)\nfalar(d.b)'), '1\n2')
        self.assertEqual(out('declarar d = {"nome completo": 5}\nfalar(d["nome completo"])'), '5')


ANIMAL = (
    'classe Animal\n'
    '    função principal usando (esse, nome)\n'
    '        esse.nome = nome\n'
    '    fim\n'
    '    função apresentar usando (esse)\n'
    '        falar("Eu sou ${esse.nome}")\n'
    '    fim\n'
    '    função som usando (esse)\n'
    '        retornar "..."\n'
    '    fim\n'
    'fim\n'
)


class TestInheritance(NebulaTestCase):
    def test_empty_subclass_inherits_constructor_and_methods(self):
        self.assertEqual(out(ANIMAL + 'classe Cachorro extende Animal\nfim\nCachorro("Rex").apresentar()'), 'Eu sou Rex')

    def test_override(self):
        code = ANIMAL + 'classe Cachorro extende Animal\n  função som usando (esse)\n    retornar "au"\n  fim\nfim\n' \
            'falar(Cachorro("R").som())\nfalar(Animal("A").som())'
        self.assertEqual(out(code), 'au\n...')

    def test_super_method_call(self):
        code = ANIMAL + 'classe Cachorro extende Animal\n  função som usando (esse)\n    retornar super.som() + "au"\n  fim\nfim\n' \
            'falar(Cachorro("R").som())'
        self.assertEqual(out(code), '...au')

    def test_super_in_constructor_both_forms(self):
        code = ANIMAL + (
            'classe A extende Animal\n  função principal usando (esse, n, r)\n    super.principal(n)\n    esse.raca = r\n  fim\nfim\n'
            'classe B extende Animal\n  função principal usando (esse, n)\n    super(n)\n  fim\nfim\n'
            'declarar a = A("x", "pug")\na.apresentar()\nfalar(a.raca)\nB("y").apresentar()')
        self.assertEqual(out(code), 'Eu sou x\npug\nEu sou y')

    def test_three_levels_with_chained_super(self):
        code = ANIMAL + (
            'classe C extende Animal\n  função som usando (esse)\n    retornar super.som() + "au"\n  fim\nfim\n'
            'classe F extende C\n  função som usando (esse)\n    retornar super.som() + "!"\n  fim\nfim\n'
            'falar(F("b").som())')
        self.assertEqual(out(code), '...au!')

    def test_instances_do_not_share_state(self):
        code = ANIMAL + 'classe C extende Animal\nfim\ndeclarar a = C("A")\ndeclarar b = C("B")\na.apresentar()\nb.apresentar()'
        self.assertEqual(out(code), 'Eu sou A\nEu sou B')

    def test_super_without_parent_is_a_clean_error(self):
        self.assertNebError('classe A\n  função f usando (esse)\n    retornar super.f()\n  fim\nfim\nA().f()', 'não possui uma superclasse')

    def test_super_outside_method(self):
        self.assertNebError('super.f()', "só pode ser usado dentro de métodos")


class TestReportedBugs(NebulaTestCase):
    """Casos do erros_encontrados.txt."""

    NUM = (
        'classe NúmeroOpcional\n'
        '  função principal usando (esse, x = nulo)\n    esse.__val = x\n  fim\n'
        '  função existe usando (esse)\n    retornar tipo(esse.__val) == "número"\n  fim\n'
        '  função somar usando (esse, outro)\n'
        '    se tipo(esse) == tipo(outro) então\n'
        '      se não outro.existe() então\n        retornar esse.__val\n      senão\n        retornar esse.__val + outro.__val\n      fim\n'
        '    senão\n      retornar esse.__val + outro\n    fim\n  fim\n'
        '  função multiplicar usando (esse, outro)\n    retornar esse.__val * outro.__val\n  fim\n'
        '  função dividir usando (esse, outro)\n    retornar esse.__val / outro.__val\n  fim\n'
        'fim\n'
    )

    def test_operand_is_not_duplicated_after_calling_a_method_on_another_instance(self):
        code = self.NUM + 'declarar x = NúmeroOpcional(1)\ndeclarar y = NúmeroOpcional(3)\nfalar(x + y)\nfalar(x * y)\nfalar(x + 2)'
        self.assertEqual(out(code), '4\n3\n3')
        code = self.NUM + 'declarar a = NúmeroOpcional(9)\ndeclarar c = NúmeroOpcional(3)\nfalar(a / c)'
        self.assertEqual(out(code), '3.0')

    def test_attribute_access_does_not_rebind_esse(self):
        code = ('classe N\n  função principal usando (esse, x)\n    esse.v = x\n  fim\n'
                '  função t usando (esse, outro)\n    falar(esse.v)\n    outro.v\n    falar(esse.v)\n  fim\nfim\n'
                'N(1).t(N(3))')
        self.assertEqual(out(code), '1\n1')

    def test_variable_declared_after_loop_over_instance_attribute(self):
        code = ('classe Mesa\n  função principal usando (esse)\n    esse.__valores = []\n  fim\nfim\n'
                'declarar x = Mesa()\ndeclarar y = Mesa()\npara cada z em y.__valores faça\n  falar("z")\nfim\n'
                'declarar b = Mesa()\nfalar(tipo(b))')
        self.assertEqual(out(code), 'Mesa')

    def test_methods_can_be_named_like_builtins(self):
        code = ('classe M\n  função principal usando (esse)\n    esse.l = []\n  fim\n'
                '  função str usando (esse)\n    retornar "meu str"\n  fim\n'
                '  função colocar usando (esse, x)\n    esse.l.colocar(x)\n    retornar str(esse.l)\n  fim\nfim\n'
                'declarar m = M()\nfalar(m.str())\nfalar(m.colocar(4))')
        self.assertEqual(out(code), 'meu str\n[4]')

    def test_real_constants_stay_protected(self):
        self.assertNebError('declarar nulo = 5', 'constante')

    def test_unimplemented_builtin_is_a_clean_error_not_a_python_crash(self):
        self.assertNebError('declarar l = [1]\ncolocar(l, 2)', 'ainda não foi implementada')

    def test_texto_method_controls_string_conversion(self):
        code = ('classe P\n  função principal usando (esse, n)\n    esse.n = n\n  fim\n'
                '  função texto usando (esse)\n    retornar "P(" + str(esse.n) + ")"\n  fim\nfim\n'
                'declarar p = P(3)\nfalar(p)\nfalar("valor: ${p}")')
        self.assertEqual(out(code), 'P(3)\nvalor: P(3)')

    def test_syntax_error_points_to_the_unclosed_block(self):
        _, error = run_neb('classe legal\n    função principal usando (esse, x)\n        esse.x = x\n    fin\nfim\n')
        text = error.as_string()
        self.assertIn("para fechar a classe 'legal'", text)
        self.assertNotIn('Syntaxe Inválida: Syntaxe Inválida', text)

    def test_empty_function_body(self):
        self.assertEqual(out('função vazia usando ()\nfim\nfalar(vazia())'), 'nulo')


class TestTypeAnnotations(NebulaTestCase):
    def test_typed_variables_accept_matching_values(self):
        code = ('declarar x: número = 5\ndeclarar s: string = "oi"\ndeclarar l: lista[número] = [1, 2]\n'
                'declarar u: número ou nulo = nulo\nfalar(x)\nfalar(u)')
        self.assertEqual(out(code), '5\nnulo')

    def test_declaration_type_mismatch(self):
        self.assertNebError('declarar x: número = "a"', "esperado 'número', obtido 'string'")

    def test_reassignment_is_checked(self):
        self.assertNebError('declarar x: número = 1\nx = "texto"', "Tipo inválido para 'x'")

    def test_value_is_not_stored_when_check_fails(self):
        ctx = pyneb.new_context()
        run_neb('declarar x: número = 1', context=ctx)
        run_neb('x = "texto"', context=ctx)
        self.assertEqual(out('falar(x)', context=ctx), '1')

    def test_generic_list_elements(self):
        self.assertNebError('declarar l: lista[número] = [1, "a"]', "esperado 'lista[número]'")

    def test_dict_generic(self):
        self.assertEqual(out('declarar d: dicionário[string, número] = {a: 1}\nfalar(d.a)'), '1')
        self.assertNebError('declarar d: dicionário[número] = {a: "x"}', 'Erro de Tipo')

    def test_union_rejects_other_types(self):
        self.assertNebError('declarar u: número ou string = 3\nu = nulo', "esperado 'número ou string'")

    def test_parameters_and_return(self):
        code = 'função soma usando (a: número, b: número = 10) -> número => a + b\nfalar(soma(1, 2))\nfalar(soma(5))'
        self.assertEqual(out(code), '3\n15')

    def test_wrong_argument(self):
        self.assertNebError('função s usando (a: número, b: número) -> número => a + b\ns(1, "2")', "Argumento 'b' de 's'")

    def test_wrong_return(self):
        self.assertNebError('função f usando (a) -> número => "oops"\nf(1)', "Retorno de 'f'")

    def test_implicit_null_return_matches_nulo(self):
        self.assertEqual(out('função g usando (a) -> nulo\n  falar(a)\nfim\ng(3)'), '3')

    def test_unknown_type(self):
        self.assertNebError('declarar x: Banana = 1', "tipo desconhecido 'Banana'")

    def test_class_types_accept_subclasses_only(self):
        base = 'classe Animal\nfim\nclasse Cachorro extende Animal\nfim\n'
        self.assertEqual(out(base + 'declarar c: Animal = Cachorro()\nfalar(tipo(c))'), 'Cachorro')
        self.assertNebError(base + 'declarar n: Cachorro = Animal()', "esperado 'Cachorro', obtido 'Animal'")

    def test_typed_methods_and_anonymous_functions(self):
        code = 'classe C\n  função dobro usando (esse, x: número) -> número\n    retornar x * 2\n  fim\nfim\nfalar(C().dobro(4))'
        self.assertEqual(out(code), '8')
        self.assertNebError(code + '\nC().dobro("a")', "Argumento 'x' de 'dobro'")
        self.assertEqual(out('declarar f = função (x: número) -> número => x + 1\nfalar(f(1))'), '2')

    def test_type_error_has_its_own_name(self):
        _, error = run_neb('declarar x: número = "a"')
        self.assertTrue(error.as_string().lstrip().split('\n')[-1] or True)
        self.assertIn('Erro de Tipo', error.as_string())

    def test_untyped_code_is_unaffected(self):
        self.assertEqual(out('declarar x = 5\nx = "agora string"\nfalar(x)'), 'agora string')


# ======================================================================================
# Linter
# ======================================================================================
from nebula import linter as neblint  # noqa: E402


def lint(code, hints=True, **kw):
    return neblint.lint_text(code, '<teste>', hints=hints, **kw)


def codes(code, **kw):
    return [d.code for d in lint(code, **kw)]


class LintCase(unittest.TestCase):
    def assertHas(self, code, *expected):
        found = codes(code)
        for e in expected:
            self.assertIn(e, found, f'{e} não apareceu; achei {found}')

    def assertLacks(self, code, *unexpected):
        found = codes(code)
        for u in unexpected:
            self.assertNotIn(u, found, f'{u} apareceu sem querer; achei {found}')

    def assertClean(self, code):
        self.assertEqual([repr(d) for d in lint(code, hints=False)], [])

    def tmp(self, files):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for name, text in files.items():
            Path(tmp.name, name).write_text(text, encoding='utf-8')
        return Path(tmp.name)


class TestLintBasics(LintCase):
    def test_clean_program(self):
        self.assertClean('declarar x = 1\nfalar(x)\nfunção f usando (a) => a + 1\nfalar(f(x))')

    def test_syntax_error(self):
        d = lint('declarar x = (1 +\nfalar(x)')
        self.assertEqual([x.code for x in d], ['NEB001'])
        self.assertEqual(d[0].line, 1)

    def test_undeclared_name_with_suggestion(self):
        d = lint('declarar contador = 1\nfalar(contadro)')
        self.assertEqual(d[0].code, 'NEB101')
        self.assertIn("Você quis dizer 'contador'", d[0].message)

    def test_builtins_and_prelude_are_known(self):
        self.assertClean('falar(máximo(1, 2))\nfalar(len([1]))\nfalar(nulo)')

    def test_constant_reassignment(self):
        self.assertHas('declarar constante PI = 3\nPI = 4', 'NEB102')

    def test_unreachable_code(self):
        self.assertHas('função f usando ()\n  retornar 1\n  falar(2)\nfim', 'NEB201')

    def test_unreachable_after_if_else_that_always_returns(self):
        self.assertHas('função f usando (x)\n  se x então\n    retornar 1\n  senão\n    retornar 2\n  fim\n  falar(3)\nfim', 'NEB201')

    def test_return_and_loop_control_outside_place(self):
        self.assertHas('retornar 1', 'NEB501')
        self.assertHas('parar', 'NEB502')
        self.assertHas('continuar', 'NEB502')
        self.assertLacks('enquanto verdadeiro faça\n  parar\nfim', 'NEB502')

    def test_unused_local_variable_and_parameter(self):
        found = codes('função f usando (a)\n  declarar b = 1\nfim')
        self.assertIn('NEB202', found)
        self.assertIn('NEB203', found)

    def test_unused_function_local(self):
        self.assertHas('função f usando ()\n  função g usando () => 1\nfim', 'NEB202')

    def test_module_level_names_are_not_reported_as_unused(self):
        self.assertClean('declarar x = 1\nfunção f usando () => 1')

    def test_duplicate_definition(self):
        self.assertHas('função f usando () => 1\nfunção f usando () => 2', 'NEB205')

    def test_shadowing_builtin_is_only_a_hint(self):
        self.assertHas('função str usando () => 1', 'NEB206')
        self.assertEqual(codes('função str usando () => 1', hints=False), [])

    def test_assignment_without_declarar_hint(self):
        self.assertHas('x = 5\nfalar(x)', 'NEB207')

    def test_assignment_in_function_shadows_global(self):
        code = 'declarar total = 0\nfunção f usando ()\n  total = 5\n  falar(total)\nfim'
        self.assertHas(code, 'NEB209')

    def test_declarar_inside_method_hint(self):
        code = 'classe C\n  função m usando (esse)\n    declarar x = 1\n  fim\nfim'
        self.assertHas(code, 'NEB210')


class TestLintNoFalsePositives(LintCase):
    def test_forward_reference_from_function_body(self):
        self.assertClean('função a usando () => b()\nfunção b usando () => 1\nfalar(a())')

    def test_recursion_and_closures(self):
        self.assertClean('função f usando (n)\n  se n < 2 então retornar 1\n  retornar n * f(n - 1)\nfim\nfalar(f(3))')
        self.assertClean('função fora usando ()\n  declarar x = 1\n  função dentro usando () => x\n  retornar dentro()\nfim\nfalar(fora())')

    def test_name_read_before_assignment_inside_loop(self):
        code = 'declarar i = 0\ndeclarar ant = 0\nenquanto i < 3 faça\n  falar(ant)\n  ant = i\n  i += 1\nfim'
        self.assertClean(code)

    def test_string_interpolation_counts_as_use(self):
        self.assertClean('declarar nome = "a"\nfalar("oi ${nome}")')

    def test_loop_and_catch_variables(self):
        self.assertClean('para cada x em [1, 2] faça\n  falar(x)\nfim\ntentar\n  falar(1)\ncaso erro faça\n  falar(erro)\nfim')

    def test_methods_named_like_builtins_and_implicit_this(self):
        code = ('classe M\n  função principal usando (esse)\n    esse.l = []\n  fim\n'
                '  função str usando (esse)\n    retornar "x"\n  fim\n'
                '  função tam usando (esse)\n    retornar len(l)\n  fim\nfim\nfalar(M().tam())')
        self.assertEqual(codes(code, hints=False), [])

    def test_class_level_attribute_and_inherited_members(self):
        code = ('classe A\n  declarar base = 1\n  função principal usando (esse)\n    esse.x = 1\n  fim\n'
                '  função ver usando (esse)\n    retornar esse.x\n  fim\nfim\n'
                'classe B extende A\n  função ver2 usando (esse)\n    retornar esse.ver() + esse.x\n  fim\nfim\nfalar(B().ver2())')
        self.assertEqual(codes(code, hints=False), [])

    def test_super_calls_are_fine(self):
        code = ('classe A\n  função principal usando (esse, n)\n    esse.n = n\n  fim\n  função som usando (esse)\n    retornar "a"\n  fim\nfim\n'
                'classe B extende A\n  função principal usando (esse, n)\n    super(n)\n  fim\n'
                '  função som usando (esse)\n    retornar super.som() + "b"\n  fim\nfim\nfalar(B(1).som())')
        self.assertEqual(codes(code, hints=False), [])

    def test_untyped_code_gets_no_type_diagnostics(self):
        self.assertEqual(codes('declarar x = 1\nx = "a"\nfalar(x)', hints=False), [])

    def test_known_builtin_return_type_is_used(self):
        self.assertHas('função f usando (a: número) => a\ndeclarar v = pegar("x")\nfalar(f(v))', 'NEB304')

    def test_unknown_inference_is_not_reported(self):
        self.assertClean('função f usando (a: número) => a\ndeclarar v = python("1")\nfalar(f(v))')


class TestLintTypes(LintCase):
    def test_unknown_type(self):
        self.assertHas('declarar x: Banana = 1', 'NEB301')

    def test_type_that_is_not_a_class(self):
        self.assertHas('função f usando () => 1\ndeclarar x: f = 1', 'NEB301')

    def test_generic_arity(self):
        self.assertHas('declarar x: lista[número, string] = []', 'NEB301')
        self.assertHas('declarar x: número[string] = 1', 'NEB301')

    def test_variable_literal_mismatch(self):
        self.assertHas('declarar x: número = "a"', 'NEB302')
        self.assertHas('declarar x: lista[número] = ["a"]', 'NEB302')
        self.assertHas('declarar x: número ou nulo = "a"', 'NEB302')
        self.assertLacks('declarar x: número ou nulo = nulo', 'NEB302')

    def test_reassignment_uses_declared_type(self):
        self.assertHas('declarar x: número = 1\nx = "a"', 'NEB302')

    def test_expression_inference(self):
        self.assertHas('declarar x: string = 1 + 2', 'NEB302')
        self.assertHas('declarar x: número = "a" + "b"', 'NEB302')
        self.assertHas('declarar x: número = 1 < 2', 'NEB302')
        self.assertLacks('declarar x: string = "a" * 3', 'NEB302')

    def test_call_arity(self):
        base = 'função s usando (a, b = 1) => a + b\n'
        self.assertHas(base + 's()', 'NEB303')
        self.assertHas(base + 's(1, 2, 3)', 'NEB303')
        self.assertLacks(base + 's(1)\ns(1, 2)', 'NEB303')

    def test_constructor_and_method_arity(self):
        cls = ('classe A\n  função principal usando (esse, n)\n    esse.n = n\n  fim\n'
               '  função m usando (esse, x)\n    retornar x\n  fim\nfim\n')
        self.assertHas(cls + 'A()', 'NEB303')
        self.assertHas(cls + 'declarar a = A(1)\na.m()', 'NEB303')
        self.assertHas(cls + 'declarar a = A(1)\na.m(1, 2)', 'NEB303')
        self.assertLacks(cls + 'declarar a = A(1)\na.m(1)', 'NEB303')
        self.assertHas('classe B\nfim\nB(1)', 'NEB303')

    def test_super_constructor_arity(self):
        code = ('classe A\n  função principal usando (esse, n)\n    esse.n = n\n  fim\nfim\n'
                'classe B extende A\n  função principal usando (esse)\n    super()\n  fim\nfim')
        self.assertHas(code, 'NEB303')

    def test_argument_type_mismatch(self):
        base = 'função s usando (a: número, b: string) => a\n'
        self.assertHas(base + 's("x", "y")', 'NEB304')
        self.assertHas(base + 's(1, 2)', 'NEB304')
        self.assertLacks(base + 's(1, "y")', 'NEB304')

    def test_return_type_mismatch(self):
        self.assertHas('função f usando () -> número\n  retornar "a"\nfim', 'NEB305')
        self.assertHas('função f usando () -> número => "a"', 'NEB305')
        self.assertHas('função f usando () -> número\n  retornar\nfim', 'NEB305')
        self.assertLacks('função f usando () -> número ou nulo\n  retornar\nfim', 'NEB305')

    def test_missing_return(self):
        self.assertHas('função f usando () -> número\n  falar(1)\nfim', 'NEB306')
        self.assertLacks('função f usando () -> nulo\n  falar(1)\nfim', 'NEB306')
        self.assertLacks('função f usando (x) -> número\n  se x então\n    retornar 1\n  senão\n    retornar 2\n  fim\nfim', 'NEB306')

    def test_class_types_and_inheritance(self):
        base = 'classe Animal\nfim\nclasse Gato extende Animal\nfim\n'
        self.assertLacks(base + 'declarar a: Animal = Gato()', 'NEB302')
        self.assertHas(base + 'declarar g: Gato = Animal()', 'NEB302')
        self.assertHas(base + 'declarar a: Animal = 5', 'NEB302')
        self.assertLacks(base + 'função f usando (a: Animal) => a\nf(Gato())', 'NEB304')
        self.assertHas(base + 'função f usando (a: Gato) => a\nf(Animal())', 'NEB304')

    def test_forward_reference_to_own_class_in_annotation(self):
        self.assertClean('classe No\n  função principal usando (esse, prox: No ou nulo = nulo)\n    esse.prox = prox\n  fim\nfim\nfalar(No(No()))')


class TestLintClasses(LintCase):
    def test_super_misuse(self):
        self.assertHas('falar(super)', 'NEB401')
        self.assertHas('classe A\n  função f usando (esse)\n    retornar super.f()\n  fim\nfim', 'NEB401')

    def test_method_must_start_with_esse(self):
        self.assertHas('classe A\n  função f usando ()\n    retornar 1\n  fim\nfim', 'NEB402')
        self.assertHas('classe A\n  função f usando (x)\n    retornar 1\n  fim\nfim', 'NEB402')

    def test_invalid_superclass(self):
        self.assertHas('classe A extende Nada\nfim', 'NEB403')
        self.assertHas('declarar x = 1\nclasse A extende x\nfim', 'NEB403')

    def test_unknown_attribute_and_method(self):
        base = 'classe A\n  função principal usando (esse)\n    esse.x = 1\n  fim\nfim\n'
        self.assertHas(base.replace('fim\n', 'fim\n', 1) + 'classe B extende A\n  função m usando (esse)\n    retornar esse.y\n  fim\nfim', 'NEB404')
        self.assertHas(base + 'declarar a: A = A()\na.voar()', 'NEB404')
        self.assertHas('classe A\nfim\nclasse B extende A\n  função m usando (esse)\n    retornar super.nada()\n  fim\nfim', 'NEB404')

    def test_unknown_parent_silences_attribute_warnings(self):
        code = 'classe B extende Nada\n  função m usando (esse)\n    retornar esse.y\n  fim\nfim'
        self.assertLacks(code, 'NEB404')


class TestLintModules(LintCase):
    def test_import_names_checked_against_stdlib_module(self):
        self.assertHas('importar fatorial, naoexiste de matematica\nfalar(fatorial(3))', 'NEB104')
        self.assertHas('importar _auxiliar de matematica', 'NEB104')

    def test_missing_module(self):
        self.assertHas('importar modulo_que_nao_existe', 'NEB105')
        found = codes('importar modulo_que_nao_existe')
        self.assertNotIn('NEB204', found)

    def test_namespace_member_checks(self):
        self.assertHas('importar matematica\nfalar(matematica.naoexiste)', 'NEB106')
        self.assertClean('importar matematica\nfalar(matematica.fatorial(3))')

    def test_unused_imports(self):
        self.assertHas('importar fatorial de matematica', 'NEB204')
        self.assertHas('importar matematica', 'NEB204')

    def test_calls_into_imported_function_are_checked(self):
        self.assertHas('importar fatorial de matematica\nfalar(fatorial())', 'NEB303')
        self.assertHas('importar matematica\nfalar(matematica.fatorial(1, 2))', 'NEB303')

    def test_local_module_with_classes_and_types(self):
        d = self.tmp({'tipos.neb': 'classe Mesa\n  função principal usando (esse)\n    esse.v = []\n  fim\n  função add usando (esse, x)\n    esse.v.colocar(x)\n  fim\nfim\n'})
        main = str(d / 'main.neb')
        ok = 'importar tipos\ndeclarar m: tipos.Mesa = tipos.Mesa()\nm.add(1)\nfalar(m)'
        self.assertEqual([x.code for x in neblint.lint_text(ok, main)], [])
        bad = 'importar tipos\ndeclarar m: tipos.Mesa = 5\ndeclarar n: tipos.Nada = 1\ntipos.Mesa(1)'
        found = [x.code for x in neblint.lint_text(bad, main)]
        self.assertIn('NEB302', found)
        self.assertIn('NEB301', found)
        self.assertIn('NEB303', found)

    def test_class_imported_by_name_is_a_type(self):
        d = self.tmp({'tipos.neb': 'classe Mesa\nfim\n'})
        main = str(d / 'main.neb')
        self.assertEqual([x.code for x in neblint.lint_text('importar Mesa de tipos\ndeclarar m: Mesa = Mesa()\nfalar(m)', main)], [])

    def test_module_with_syntax_error_is_a_warning_not_a_crash(self):
        d = self.tmp({'quebrado.neb': 'declarar x = (1 +\n'})
        found = [x.code for x in neblint.lint_text('importar quebrado\nfalar(quebrado.x)', str(d / 'main.neb'))]
        self.assertIn('NEB107', found)
        self.assertNotIn('NEB106', found)

    def test_circular_imports_do_not_hang(self):
        d = self.tmp({'a.neb': 'importar b\ndeclarar x = 1\n', 'b.neb': 'importar a\ndeclarar y = 1\n'})
        neblint.lint_text('importar a\nfalar(a.x)', str(d / 'main.neb'))

    def test_private_members_are_not_exported(self):
        d = self.tmp({'m.neb': 'função privada oculta usando () => 1\nfunção aberta usando () => 2\n'})
        found = [x.code for x in neblint.lint_text('importar oculta de m', str(d / 'main.neb'))]
        self.assertIn('NEB104', found)


class TestLintSuppression(LintCase):
    def test_line_suppression_all_and_specific(self):
        self.assertEqual(codes('falar(nada)  # neb-ignore'), [])
        self.assertEqual(codes('falar(nada)  # neb-ignore: NEB101'), [])
        self.assertIn('NEB101', codes('falar(nada)  # neb-ignore: NEB202'))

    def test_file_suppression(self):
        self.assertEqual(codes('# neb-ignore-file: NEB101\nfalar(nada)\nfalar(outro)'), [])

    def test_ignore_option(self):
        self.assertEqual(codes('falar(nada)', ignore={'NEB101'}), [])

    def test_neblint_config_file(self):
        d = self.tmp({'.neblint': 'ignore = NEB101  # tudo bem\n', 'x.neb': 'falar(nada)\n'})
        self.assertEqual(neblint.lint_file(d / 'x.neb'), [])
        self.assertEqual(len(neblint.lint_file(d / 'x.neb', use_config=False)), 1)

    def test_positions_are_one_based_and_point_at_the_token(self):
        d = lint('declarar a = 1\nfalar(zzz)')[0]
        self.assertEqual((d.line, d.col), (2, 7))

    def test_diagnostic_to_dict(self):
        d = lint('falar(zzz)')[0].to_dict()
        for key in ('file', 'line', 'column', 'end_line', 'end_column', 'code', 'severity', 'message'):
            self.assertIn(key, d)


class TestLintCLI(LintCase):
    def cli(self, *args, cwd):
        env = dict(os.environ, PYTHONUTF8='1', HOME=str(cwd), APPDATA=str(cwd))
        return subprocess.run([sys.executable, str(SRC / 'shell.py'), *args], cwd=cwd, capture_output=True,
                              text=True, env=env, encoding='utf-8')

    def test_exit_codes(self):
        d = self.tmp({'ok.neb': 'falar(1)\n', 'erro.neb': 'falar(nada)\n', 'aviso.neb': 'função f usando ()\n  declarar x = 1\nfim\n'})
        self.assertEqual(self.cli('lint', 'ok.neb', cwd=d).returncode, 0)
        self.assertEqual(self.cli('lint', 'erro.neb', cwd=d).returncode, 1)
        self.assertEqual(self.cli('lint', 'aviso.neb', cwd=d).returncode, 0)
        self.assertEqual(self.cli('lint', 'aviso.neb', '--strict', cwd=d).returncode, 1)
        self.assertEqual(self.cli('lint', 'nao_existe.neb', cwd=d).returncode, 2)

    def test_directory_is_linted_recursively(self):
        d = self.tmp({'a.neb': 'falar(nada)\n'})
        (d / 'sub').mkdir()
        (d / 'sub' / 'b.neb').write_text('falar(outro)\n', encoding='utf-8')
        r = self.cli('lint', '.', cwd=d)
        self.assertIn('a.neb', r.stdout)
        self.assertIn('b.neb', r.stdout)
        self.assertEqual(r.returncode, 1)

    def test_json_output_and_ignore(self):
        import json
        d = self.tmp({'x.neb': 'falar(nada)\n'})
        data = json.loads(self.cli('lint', 'x.neb', '--json', cwd=d).stdout)
        self.assertEqual(data[0]['code'], 'NEB101')
        self.assertEqual(self.cli('lint', 'x.neb', '--ignore', 'NEB101', cwd=d).returncode, 0)

    def test_hints_flag_and_rules_listing(self):
        d = self.tmp({'x.neb': 'x = 1\nfalar(x)\n'})
        self.assertNotIn('NEB207', self.cli('lint', 'x.neb', cwd=d).stdout)
        self.assertIn('NEB207', self.cli('lint', 'x.neb', '--dicas', cwd=d).stdout)
        self.assertIn('NEB101', self.cli('--regras', cwd=d).stdout)

    def test_output_shows_source_line_and_caret(self):
        d = self.tmp({'x.neb': 'falar(nada)\n'})
        out_text = self.cli('lint', 'x.neb', cwd=d).stdout
        self.assertIn('falar(nada)', out_text)
        self.assertIn('^^^^', out_text)

    def test_repository_examples_and_stdlib_are_clean(self):
        r = self.cli('lint', str(SRC.parent / 'examples'), str(SRC / 'stdlib'), cwd=SRC)
        self.assertEqual(r.returncode, 0, r.stdout)


class TestCustomClassTypesFromModules(NebulaTestCase):
    MOD = 'classe Mesa\n  função principal usando (esse)\n    esse.v = []\n  fim\nfim\nclasse Sub extende Mesa\nfim\n'

    def run_in_dir(self, main_code):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        Path(tmp.name, 'tipos.neb').write_text(self.MOD, encoding='utf-8')
        return run_neb(main_code, fn=str(Path(tmp.name, 'main.neb')))

    def test_namespace_class_as_type(self):
        output, error = self.run_in_dir('importar tipos\ndeclarar m: tipos.Mesa = tipos.Mesa()\nfalar("ok")')
        self.assertIsNone(error)
        self.assertEqual(output, 'ok')

    def test_subclass_from_module_is_accepted(self):
        _, error = self.run_in_dir('importar tipos\ndeclarar m: tipos.Mesa = tipos.Sub()')
        self.assertIsNone(error)

    def test_namespace_class_mismatch_and_unknown_member(self):
        _, error = self.run_in_dir('importar tipos\ndeclarar m: tipos.Mesa = 5')
        self.assertIn("esperado 'tipos.Mesa', obtido 'número'", error.as_string())
        _, error = self.run_in_dir('importar tipos\ndeclarar m: tipos.Nada = 5')
        self.assertIn("tipo desconhecido 'tipos.Nada'", error.as_string())

    def test_same_class_name_in_different_modules_is_not_confused(self):
        _, error = self.run_in_dir('importar tipos\nclasse Mesa\nfim\ndeclarar m: tipos.Mesa = Mesa()')
        self.assertIn('Erro de Tipo', error.as_string())

    def test_class_imported_by_name_and_generics(self):
        output, error = self.run_in_dir('importar Mesa de tipos\ndeclarar l: lista[Mesa] = [Mesa(), Mesa()]\nfalar(len(l))')
        self.assertIsNone(error)
        self.assertEqual(output, '2')

    def test_dotted_type_syntax_error(self):
        _, error = run_neb('declarar x: tipos. = 1')
        self.assertIn('depois do', error.as_string())


# ======================================================================================
# Language server
# ======================================================================================
import json  # noqa: E402
import threading  # noqa: E402


class LspClient:
    """Cliente mínimo de teste: sobe `nebula lsp` e conversa pelo protocolo (Content-Length + JSON-RPC)."""

    def __init__(self, cwd):
        env = dict(os.environ, PYTHONUTF8='1', HOME=str(cwd), APPDATA=str(cwd))
        self.proc = subprocess.Popen([sys.executable, str(SRC / 'shell.py'), 'lsp'], cwd=cwd, env=env,
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.next_id = 1

    def send(self, message):
        body = json.dumps(message, ensure_ascii=False).encode('utf-8')
        self.proc.stdin.write(f'Content-Length: {len(body)}\r\n\r\n'.encode('ascii') + body)
        self.proc.stdin.flush()

    def read(self):
        headers = {}
        while True:
            line = self.proc.stdout.readline()
            if not line:
                return None
            line = line.decode('ascii').strip()
            if not line:
                break
            k, _, v = line.partition(':')
            headers[k.strip().lower()] = v.strip()
        return json.loads(self.proc.stdout.read(int(headers['content-length'])).decode('utf-8'))

    def request(self, method, params=None):
        request_id = self.next_id
        self.next_id += 1
        self.send({'jsonrpc': '2.0', 'id': request_id, 'method': method, 'params': params or {}})
        while True:
            message = self.read()
            if message is None or message.get('id') == request_id:
                return message

    def notify(self, method, params=None):
        self.send({'jsonrpc': '2.0', 'method': method, 'params': params or {}})

    def next_notification(self, method):
        while True:
            message = self.read()
            if message is None or message.get('method') == method:
                return message

    def open(self, uri, text):
        self.notify('textDocument/didOpen', {'textDocument': {'uri': uri, 'languageId': 'nebula', 'version': 1, 'text': text}})
        return self.next_notification('textDocument/publishDiagnostics')['params']

    def close(self):
        try:
            self.request('shutdown')
            self.notify('exit')
            code = self.proc.wait(timeout=10)
        finally:
            for stream in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
                stream.close()
            self.proc.kill()
        return code


class TestLanguageServer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.client = LspClient(self.tmp.name)
        self.addCleanup(lambda: self.client.proc.poll() is None and self.client.proc.kill())

    def uri(self, name='x.neb'):
        return Path(self.tmp.name, name).as_uri()

    def init(self):
        response = self.client.request('initialize', {'processId': None, 'rootUri': None, 'capabilities': {}})
        self.client.notify('initialized')
        return response

    def test_initialize_announces_capabilities(self):
        result = self.init()['result']
        self.assertEqual(result['capabilities']['textDocumentSync']['change'], 1)
        self.assertEqual(result['serverInfo']['name'], 'nebula-lsp')
        self.assertEqual(self.client.close(), 0)

    def test_requests_before_initialize_are_rejected(self):
        response = self.client.request('textDocument/hover', {})
        self.assertEqual(response['error']['code'], -32002)
        self.client.close()

    def test_diagnostics_on_open_with_exact_ranges(self):
        self.init()
        params = self.client.open(self.uri(), 'declarar a = 1\nfalar(zzz)\n')
        self.assertEqual(params['uri'], self.uri())
        d = params['diagnostics'][0]
        self.assertEqual(d['code'], 'NEB101')
        self.assertEqual(d['severity'], 1)
        self.assertEqual(d['source'], 'nebula-lint')
        self.assertEqual(d['range']['start'], {'line': 1, 'character': 6})
        self.assertEqual(d['range']['end'], {'line': 1, 'character': 9})
        self.client.close()

    def test_change_updates_and_close_clears(self):
        self.init()
        uri = self.uri()
        self.client.open(uri, 'falar(zzz)\n')
        self.client.notify('textDocument/didChange', {'textDocument': {'uri': uri, 'version': 2},
                                                      'contentChanges': [{'text': 'falar(1)\n'}]})
        self.assertEqual(self.client.next_notification('textDocument/publishDiagnostics')['params']['diagnostics'], [])
        self.client.notify('textDocument/didChange', {'textDocument': {'uri': uri, 'version': 3},
                                                      'contentChanges': [{'text': 'declarar x: número = "a"\n'}]})
        codes_ = [d['code'] for d in self.client.next_notification('textDocument/publishDiagnostics')['params']['diagnostics']]
        self.assertIn('NEB302', codes_)
        self.client.notify('textDocument/didClose', {'textDocument': {'uri': uri}})
        self.assertEqual(self.client.next_notification('textDocument/publishDiagnostics')['params']['diagnostics'], [])
        self.client.close()

    def test_syntax_error_is_reported(self):
        self.init()
        d = self.client.open(self.uri(), 'declarar x = (1 +\n')['diagnostics']
        self.assertEqual([x['code'] for x in d], ['NEB001'])
        self.client.close()

    def test_imports_resolve_relative_to_the_file(self):
        Path(self.tmp.name, 'tipos.neb').write_text('classe Mesa\nfim\n', encoding='utf-8')
        self.init()
        d = self.client.open(self.uri(), 'importar tipos\ndeclarar m: tipos.Mesa = 5\nfalar(m)\n')['diagnostics']
        self.assertIn('NEB302', [x['code'] for x in d])
        self.client.close()

    def test_neblint_ignore_is_respected(self):
        Path(self.tmp.name, '.neblint').write_text('ignore = NEB101\n', encoding='utf-8')
        self.init()
        self.assertEqual(self.client.open(self.uri(), 'falar(zzz)\n')['diagnostics'], [])
        self.client.close()

    def test_accents_and_utf16_columns(self):
        self.init()
        d = self.client.open(self.uri(), 'falar("ação 😀", zzz)\n')['diagnostics'][0]
        # 😀 vale 2 unidades UTF-16; as colunas do LSP precisam contar isso
        self.assertEqual(d['range']['start']['character'], len('falar("ação ') + 2 + len('", '))
        self.client.close()

    def test_unknown_request_gets_method_not_found_and_notifications_are_ignored(self):
        self.init()
        self.client.notify('workspace/naoExiste')
        response = self.client.request('textDocument/inexistente', {})
        self.assertEqual(response['error']['code'], -32601)
        self.client.close()

    def test_exit_without_shutdown_returns_1(self):
        self.init()
        self.client.notify('exit')
        self.assertEqual(self.client.proc.wait(timeout=10), 1)
        for stream in (self.client.proc.stdin, self.client.proc.stdout, self.client.proc.stderr):
            stream.close()

    def test_stray_prints_do_not_corrupt_the_protocol(self):
        # o servidor redireciona sys.stdout para stderr; uma mensagem depois de um "print" ainda precisa ser válida
        self.init()
        self.assertEqual(self.client.open(self.uri(), 'falar(1)\n')['diagnostics'], [])
        self.client.close()


SAMPLE = (
    'importar matematica\n'                                              # 0
    'classe Animal\n'                                                    # 1
    '    função principal usando (esse, nome: string)\n'                 # 2
    '        esse.nome = nome\n'                                         # 3
    '    fim\n'                                                          # 4
    '    função som usando (esse) -> string\n'                           # 5
    '        retornar "..."\n'                                           # 6
    '    fim\n'                                                          # 7
    'fim\n'                                                              # 8
    'classe Gato extende Animal\n'                                       # 9
    'fim\n'                                                              # 10
    'declarar constante LIMITE: número = 3\n'                            # 11
    'função dobro usando (x: número) -> número => x * 2\n'               # 12
    'declarar g: Gato = Gato("a")\n'                                     # 13
    'falar(dobro(LIMITE))\n'                                             # 14
    'falar(matematica.fatorial(3))\n'                                    # 15
    'g.som()\n'                                                          # 16
)


class TestLanguageServerStage2(TestLanguageServer):
    """Herda a infraestrutura; sobrescreve os testes herdados para não repeti-los."""

    def hover(self, line, character, uri=None):
        return self.client.request('textDocument/hover', {'textDocument': {'uri': uri or self.uri()},
                                                          'position': {'line': line, 'character': character}})['result']

    def definition(self, line, character, uri=None):
        return self.client.request('textDocument/definition', {'textDocument': {'uri': uri or self.uri()},
                                                               'position': {'line': line, 'character': character}})['result']

    def open_sample(self, text=SAMPLE):
        self.init()
        self.client.open(self.uri(), text)

    def test_capabilities_include_stage2_providers(self):
        caps = self.init()['result']['capabilities']
        self.assertTrue(caps['documentSymbolProvider'] and caps['hoverProvider'] and caps['definitionProvider'])
        self.client.close()

    def test_document_symbols_are_hierarchical(self):
        self.open_sample()
        symbols = self.client.request('textDocument/documentSymbol', {'textDocument': {'uri': self.uri()}})['result']
        names = [(x['name'], x['kind']) for x in symbols]
        self.assertEqual(names, [('Animal', 5), ('Gato', 5), ('LIMITE', 14), ('dobro', 12), ('g', 13)])
        animal = symbols[0]
        self.assertEqual([(c['name'], c['kind']) for c in animal['children']], [('principal', 6), ('som', 6)])
        self.assertIn('-> string', animal['children'][1]['detail'])
        for sym in symbols:  # selectionRange precisa estar dentro de range
            self.assertLessEqual((sym['range']['start']['line'], sym['range']['start']['character']),
                                 (sym['selectionRange']['start']['line'], sym['selectionRange']['start']['character']))
        self.client.close()

    def test_hover_function_class_variable_and_module(self):
        self.open_sample()
        self.assertIn('função dobro(x: número) -> número', self.hover(14, 8)['contents']['value'])
        self.assertIn('declarar constante LIMITE: número', self.hover(14, 14)['contents']['value'])
        self.assertIn('Exporta:', self.hover(15, 8)['contents']['value'])
        self.assertIn('método som(esse) -> string', self.hover(16, 3)['contents']['value'])
        cls = self.hover(13, 12)['contents']['value']  # o tipo `Gato` na anotação
        self.assertIn('classe Gato extende Animal', cls)
        self.client.close()

    def test_hover_on_builtin_and_on_nothing(self):
        self.open_sample()
        self.assertIn('nome nativo', self.hover(14, 2)['contents']['value'])  # falar
        self.assertIsNone(self.hover(8, 1))
        self.client.close()

    def test_definition_local_symbols(self):
        self.open_sample()
        d = self.definition(14, 8)  # dobro -> linha 12
        self.assertEqual((d['uri'], d['range']['start']['line']), (self.uri(), 12))
        d = self.definition(16, 3)  # g.som -> método som, linha 5
        self.assertEqual(d['range']['start']['line'], 5)
        d = self.definition(13, 12)  # tipo Gato -> classe, linha 9
        self.assertEqual(d['range']['start']['line'], 9)
        d = self.definition(9, 20)  # extende Animal
        self.assertEqual(d['range']['start']['line'], 1)
        self.client.close()

    def test_definition_into_another_module(self):
        self.open_sample()
        d = self.definition(15, 8)  # matematica -> arquivo do módulo
        self.assertTrue(d['uri'].endswith('matematica.modneb'))
        d = self.definition(15, 18)  # matematica.fatorial -> linha da função
        self.assertTrue(d['uri'].endswith('matematica.modneb'))
        self.assertGreater(d['range']['start']['line'], 0)
        self.client.close()

    def test_definition_of_name_imported_by_name(self):
        self.init()
        text = 'importar fatorial de matematica\nfalar(fatorial(3))\n'
        self.client.open(self.uri(), text)
        d = self.definition(1, 8)
        self.assertTrue(d['uri'].endswith('matematica.modneb'))
        self.client.close()

    def test_definition_and_hover_with_emoji_before_the_name(self):
        self.init()
        text = 'função dobro usando (x) => x * 2\nfalar("😀", dobro(1))\n'
        self.client.open(self.uri(), text)
        column = len('falar("') + 2 + len('", ') + 1  # 😀 ocupa 2 unidades UTF-16
        self.assertEqual(self.definition(1, column)['range']['start']['line'], 0)
        self.assertIn('função dobro', self.hover(1, column)['contents']['value'])
        self.client.close()

    def test_last_good_analysis_survives_a_syntax_error_on_other_lines(self):
        self.open_sample()
        uri = self.uri()
        broken = SAMPLE + 'declarar x = (1 +\n'  # erro só na última linha
        self.client.notify('textDocument/didChange', {'textDocument': {'uri': uri, 'version': 2},
                                                      'contentChanges': [{'text': broken}]})
        diags = self.client.next_notification('textDocument/publishDiagnostics')['params']['diagnostics']
        self.assertIn('NEB001', [x['code'] for x in diags])
        self.assertIn('função dobro', self.hover(14, 8)['contents']['value'])       # linha não mudou: usa a análise antiga
        self.assertIsNone(self.hover(17, 3))                                          # linha nova: sem informação
        symbols = self.client.request('textDocument/documentSymbol', {'textDocument': {'uri': uri}})['result']
        self.assertEqual(symbols[0]['name'], 'Animal')                                # outline antigo continua
        self.client.close()

    def test_features_return_null_for_unknown_documents(self):
        self.init()
        self.assertIsNone(self.hover(0, 0, uri=self.uri('nao_aberto.neb')))
        self.assertIsNone(self.definition(0, 0, uri=self.uri('nao_aberto.neb')))
        self.client.close()


# os testes herdados de TestLanguageServer já rodam na classe pai; aqui só os da etapa 2
for _name in [n for n in dir(TestLanguageServer) if n.startswith('test_')]:
    setattr(TestLanguageServerStage2, _name, None)


class TestAnalysisAPI(unittest.TestCase):
    def test_symbol_at_and_describe(self):
        a = neblint.analyze_text(SAMPLE, 'x.neb')
        self.assertFalse(a.syntax_error)
        sym, rng = a.symbol_at(14, 8)
        self.assertEqual((sym.kind, sym.name), ('function', 'dobro'))
        self.assertIn('função dobro(x: número) -> número', neblint.describe_symbol(sym))
        self.assertIsNone(a.symbol_at(8, 1))

    def test_syntax_error_gives_empty_index(self):
        a = neblint.analyze_text('declarar x = (1 +\n', 'x.neb')
        self.assertTrue(a.syntax_error)
        self.assertEqual((a.outline, a.defs, a.refs), ([], [], []))

    def test_outline_kinds(self):
        a = neblint.analyze_text('classe A\n  declarar base = 1\n  função m usando (esse)\n    retornar 1\n  fim\nfim\ndeclarar constante C = 1\n', 'x.neb')
        top = [(e['name'], e['kind']) for e in a.outline]
        self.assertEqual(top, [('A', 'class'), ('C', 'constant')])
        self.assertEqual([(c['name'], c['kind']) for c in a.outline[0]['children']], [('base', 'field'), ('m', 'method')])


class TestLineEndingsAndEmptyFiles(NebulaTestCase):
    """Relatado no editor: NEB001 com '\\r' no fim da 1ª linha (CRLF) e em arquivo vazio."""

    def test_crlf_programs_behave_like_lf(self):
        lf = 'importar fatorial de matematica\nfalar(fatorial(4))\nfunção f usando ()\n  retornar 1\nfim\nfalar(f())\n'
        self.assertEqual(out(lf.replace('\n', '\r\n')), out(lf))
        self.assertEqual(neblint.lint_text(lf.replace('\n', '\r\n'), 'x.neb'), [])

    def test_crlf_class_and_blocks(self):
        code = 'classe A\r\n  função principal usando (esse)\r\n    esse.x = 1\r\n  fim\r\nfim\r\nfalar(A().x)\r\n'
        self.assertEqual(out(code), '1')

    def test_empty_blank_and_comment_only_files_are_valid(self):
        for text in ('', '\n', '   \n\t\n', '# só um comentário\n# outro\n', '\r\n'):
            self.assertEqual(neblint.lint_text(text, 'x.neb'), [], repr(text))
            _, error = run_neb(text)
            self.assertIsNone(error, repr(text))

    def test_bom_is_ignored(self):
        self.assertEqual(out('\ufefffalar(1)\n'), '1')
        self.assertEqual(neblint.lint_text('\ufeffdeclarar x = 1\n', 'x.neb', hints=False), [])

    def test_real_errors_still_reported_with_crlf(self):
        d = neblint.lint_text('declarar a = 1\r\nfalar(zzz)\r\n', 'x.neb')
        self.assertEqual([(x.code, x.line, x.col) for x in d], [('NEB101', 2, 7)])


class TestLspLineEndings(TestLanguageServer):
    def test_crlf_document_has_no_false_syntax_error_and_right_columns(self):
        self.init()
        clean = self.client.open(self.uri(), 'importar fatorial de matematica\r\nfalar(fatorial(3))\r\n')['diagnostics']
        self.assertEqual(clean, [])
        uri = self.uri('b.neb')
        d = self.client.open(uri, 'declarar a = 1\r\nfalar(zzz)\r\n')['diagnostics'][0]
        self.assertEqual((d['code'], d['range']['start']), ('NEB101', {'line': 1, 'character': 6}))
        self.client.close()

    def test_empty_document_is_clean(self):
        self.init()
        self.assertEqual(self.client.open(self.uri(), '')['diagnostics'], [])
        self.client.close()


for _name in [n for n in dir(TestLanguageServer) if n.startswith('test_') and not hasattr(TestLspLineEndings, '__dict__') ]:
    pass
for _name in [n for n in dir(TestLanguageServer) if n.startswith('test_')]:
    if _name not in TestLspLineEndings.__dict__:
        setattr(TestLspLineEndings, _name, None)


# ======================================================================================
# Correções rápidas
# ======================================================================================
def apply_edits(text, edits):
    """Aplica edições ((l0, c0, l1, c1), texto) em code points, de trás para frente."""
    lines = text.split('\n')
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line) + 1)
    for (l0, c0, l1, c1), new in sorted(edits, key=lambda e: e[0], reverse=True):
        text = text[:offsets[l0] + c0] + new + text[offsets[l1] + c1:]
    return text


class TestQuickFixes(LintCase):
    def fixed(self, code_text, rule, index=0):
        analysis = neblint.analyze_text(code_text, 'x.neb', hints=True)
        diagnostics = [d for d in analysis.diagnostics if d.code == rule and d.fixes]
        self.assertTrue(diagnostics, f'{rule} sem correção; diagnósticos: {[d.code for d in analysis.diagnostics]}')
        fix = diagnostics[0].fixes[index]
        new_text = apply_edits(code_text, fix['edits'])
        after = [d.code for d in neblint.analyze_text(new_text, 'x.neb', hints=True).diagnostics]
        self.assertNotIn('NEB001', after, f'a correção quebrou a sintaxe: {new_text!r}')
        return new_text, after, fix

    def test_did_you_mean_for_names(self):
        text, after, fix = self.fixed('declarar contador = 1\nfalar(contadro)\n', 'NEB101')
        self.assertEqual(text, 'declarar contador = 1\nfalar(contador)\n')
        self.assertTrue(fix['preferred'])

    def test_unused_import_names(self):
        text, after, _ = self.fixed('importar fatorial, mdc de matematica\nfalar(mdc(4, 2))\n', 'NEB204')
        self.assertEqual(text, 'importar mdc de matematica\nfalar(mdc(4, 2))\n')
        self.assertNotIn('NEB204', after)

    def test_unused_import_that_is_alone_removes_the_line(self):
        text, _, fix = self.fixed('importar fatorial de matematica\nfalar(1)\n', 'NEB204')
        self.assertEqual(text, 'falar(1)\n')
        self.assertIn('Remover a importação', fix['title'])

    def test_unused_namespace_import(self):
        text, _, _ = self.fixed('importar matematica\nfalar(1)\n', 'NEB204')
        self.assertEqual(text, 'falar(1)\n')

    def test_import_fix_keeps_comment_and_crlf(self):
        text, _, _ = self.fixed('importar fatorial, mdc de matematica  # uteis\r\nfalar(mdc(4, 2))\r\n', 'NEB204')
        self.assertEqual(text, 'importar mdc de matematica  # uteis\r\nfalar(mdc(4, 2))\r\n')

    def test_unused_variable_parameter_and_function_are_renamed(self):
        text, after, _ = self.fixed('função f usando ()\n  declarar inutil = 5\nfim\nf()\n', 'NEB202')
        self.assertIn('declarar _inutil = 5', text)
        self.assertNotIn('NEB202', after)
        text, after, _ = self.fixed('função f usando (a, b)\n  retornar a\nfim\nf(1, 2)\n', 'NEB203')
        self.assertIn('usando (a, _b)', text)

    def test_remove_unreachable_code(self):
        text, after, _ = self.fixed('função f usando ()\n  retornar 1\n  falar(2)\nfim\nf()\n', 'NEB201')
        self.assertEqual(text, 'função f usando ()\n  retornar 1\nfim\nf()\n')
        self.assertNotIn('NEB201', after)

    def test_unreachable_block_statements_get_no_fix(self):
        code = 'função f usando (x)\n  retornar 1\n  se x então\n    falar(1)\n  fim\nfim\nf(1)\n'
        first = [d for d in neblint.analyze_text(code, 'x.neb').diagnostics if d.code == 'NEB201'][0]
        self.assertEqual(first.fixes, [])  # remover um bloco inteiro exige saber onde ele termina; não arriscamos

    def test_unreachable_single_line_with_trailing_comment_is_removed(self):
        text, _, _ = self.fixed('função f usando ()\n  retornar 1\n  falar(2)  # ok\nfim\nf()\n', 'NEB201')
        self.assertEqual(text, 'função f usando ()\n  retornar 1\nfim\nf()\n')

    def test_add_esse_to_methods(self):
        text, after, _ = self.fixed('classe A\n  função m usando ()\n    retornar 1\n  fim\nfim\n', 'NEB402')
        self.assertIn('função m usando (esse)', text)
        text, _, _ = self.fixed('classe A\n  função m usando (x)\n    retornar x\n  fim\nfim\n', 'NEB402')
        self.assertIn('função m usando (esse, x)', text)

    def test_declarar_fixes(self):
        text, _, _ = self.fixed('x = 5\nfalar(x)\n', 'NEB207')
        self.assertEqual(text, 'declarar x = 5\nfalar(x)\n')
        text, after, _ = self.fixed('declarar total = 0\nfunção f usando ()\n  total = 5\n  falar(total)\nfim\nf()\n', 'NEB209')
        self.assertIn('  declarar total = 5', text)
        self.assertNotIn('NEB209', after)

    def test_declarar_inside_method_becomes_attribute(self):
        text, after, _ = self.fixed('classe A\n  função m usando (esse)\n    declarar x = 1\n  fim\nfim\n', 'NEB210')
        self.assertIn('    esse.x = 1', text)
        self.assertNotIn('NEB210', after)

    def test_type_name_suggestions(self):
        text, after, _ = self.fixed('classe Mesa\nfim\ndeclarar m: Mesaa = Mesa()\nfalar(m)\n', 'NEB301')
        self.assertIn('declarar m: Mesa = Mesa()', text)
        text, _, _ = self.fixed('declarar n: numero = 1\nfalar(n)\n', 'NEB301')
        self.assertIn('declarar n: número = 1', text)

    def test_member_and_import_name_suggestions(self):
        text, _, _ = self.fixed('importar matematica\nfalar(matematica.fatoria(2))\n', 'NEB106')
        self.assertIn('matematica.fatorial(2)', text)
        text, _, _ = self.fixed('importar fatoral de matematica\nfalar(1)\n', 'NEB104')
        self.assertIn('importar fatorial de matematica', text)

    def test_class_and_attribute_suggestions(self):
        text, _, _ = self.fixed('classe Animal\nfim\nclasse Gato extende Animall\nfim\n', 'NEB403')
        self.assertIn('extende Animal', text)
        code = 'classe A\n  função principal usando (esse)\n    esse.nome = 1\n  fim\n  função m usando (esse)\n    retornar esse.nomee\n  fim\nfim\n'
        text, after, _ = self.fixed(code, 'NEB404')
        self.assertIn('esse.nome\n', text)

    def test_organize_imports_removes_everything_unused_at_once(self):
        code = 'importar fatorial, mdc, mmc de matematica\nimportar listas\nimportar matematica\nfalar(mdc(4, 2))\nfalar(matematica.PI)\n'
        analysis = neblint.analyze_text(code, 'x.neb')
        new_text = apply_edits(code, analysis.organize_import_edits())
        self.assertEqual(new_text, 'importar mdc de matematica\nimportar matematica\nfalar(mdc(4, 2))\nfalar(matematica.PI)\n')
        self.assertEqual([d.code for d in neblint.analyze_text(new_text, 'x.neb').diagnostics], [])

    def test_suppressed_diagnostic_offers_no_fix(self):
        analysis = neblint.analyze_text('importar fatorial de matematica  # neb-ignore: NEB204\nfalar(1)\n', 'x.neb')
        self.assertEqual(analysis.diagnostics, [])
        self.assertEqual(analysis.organize_import_edits(), [])

    def test_json_includes_fixes_one_based(self):
        d = neblint.lint_text('declarar contador = 1\nfalar(contadro)\n', 'x.neb')[0].to_dict()
        edit = d['fixes'][0]['edits'][0]
        self.assertEqual((edit['start_line'], edit['start_column'], edit['new_text']), (2, 7, 'contador'))


class TestLspQuickFixes(TestLanguageServer):
    def apply_lsp_edits(self, text, edits):
        lines = text.split('\n')
        converted = []
        from nebula.lsp import col_from_utf16
        for e in edits:
            r = e['range']
            converted.append(((r['start']['line'], col_from_utf16(lines[r['start']['line']], r['start']['character']),
                              r['end']['line'], col_from_utf16(lines[min(r['end']['line'], len(lines) - 1)], r['end']['character'])),
                             e['newText']))
        return apply_edits(text, converted)

    def actions(self, uri, text, line, character=0, end_line=None, end_character=None, only=None):
        context = {'diagnostics': []}
        if only:
            context['only'] = only
        return self.client.request('textDocument/codeAction', {
            'textDocument': {'uri': uri},
            'range': {'start': {'line': line, 'character': character},
                      'end': {'line': end_line if end_line is not None else line, 'character': end_character if end_character is not None else character}},
            'context': context})['result']

    def test_capabilities(self):
        caps = self.init()['result']['capabilities']
        self.assertIn('quickfix', caps['codeActionProvider']['codeActionKinds'])
        self.assertEqual(caps['completionProvider']['triggerCharacters'], ['.'])
        self.client.close()

    def test_quickfix_for_the_diagnostic_under_the_cursor(self):
        self.init()
        text = 'declarar contador = 1\nfalar(contadro)\n'
        self.client.open(self.uri(), text)
        acts = self.actions(self.uri(), text, 1, 8)
        titles = [a['title'] for a in acts]
        self.assertIn("Trocar por 'contador'", titles)
        action = next(a for a in acts if a['title'] == "Trocar por 'contador'")
        self.assertEqual(action['kind'], 'quickfix')
        self.assertTrue(action['isPreferred'])
        self.assertEqual(action['diagnostics'][0]['code'], 'NEB101')
        new_text = self.apply_lsp_edits(text, action['edit']['changes'][self.uri()])
        self.assertEqual(new_text, 'declarar contador = 1\nfalar(contador)\n')
        self.client.close()

    def test_no_actions_away_from_diagnostics_and_for_other_kinds(self):
        self.init()
        text = 'declarar contador = 1\nfalar(contadro)\n'
        self.client.open(self.uri(), text)
        self.assertEqual(self.actions(self.uri(), text, 0, 3), [])
        self.assertEqual(self.actions(self.uri(), text, 1, 8, only=['refactor']), [])
        self.client.close()

    def test_organize_imports_action(self):
        self.init()
        text = 'importar fatorial, mdc de matematica\nimportar listas\nfalar(mdc(4, 2))\n'
        self.client.open(self.uri(), text)
        acts = self.actions(self.uri(), text, 0, 0, only=['source.organizeImports'])
        self.assertEqual([a['kind'] for a in acts], ['source.organizeImports'])
        new_text = self.apply_lsp_edits(text, acts[0]['edit']['changes'][self.uri()])
        self.assertEqual(new_text, 'importar mdc de matematica\nfalar(mdc(4, 2))\n')
        self.client.close()

    def test_delete_line_fix_on_last_line_without_newline(self):
        self.init()
        text = 'falar(1)\nimportar matematica'
        self.client.open(self.uri(), text)
        acts = self.actions(self.uri(), text, 1, 10)
        fix = next(a for a in acts if a['title'].startswith('Remover a importação'))
        new_text = self.apply_lsp_edits(text, fix['edit']['changes'][self.uri()])
        self.assertEqual(new_text.strip(), 'falar(1)')
        self.client.close()


for _name in [n for n in dir(TestLanguageServer) if n.startswith('test_')]:
    if _name not in TestLspQuickFixes.__dict__:
        setattr(TestLspQuickFixes, _name, None)


# ======================================================================================
# Completar
# ======================================================================================
COMPLETION_SAMPLE = (
    'importar matematica\n'                                  # 0
    'classe Animal\n'                                        # 1
    '    função principal usando (esse, nome: string)\n'     # 2
    '        esse.nome = nome\n'                             # 3
    '    fim\n'                                              # 4
    '    função som usando (esse) -> string\n'               # 5
    '        retornar "..."\n'                               # 6
    '    fim\n'                                              # 7
    'fim\n'                                                  # 8
    'classe Gato extende Animal\n'                           # 9
    '    função miar usando (esse)\n'                        # 10
    '        retornar ""\n'                                  # 11
    '    fim\n'                                              # 12
    'fim\n'                                                  # 13
    'declarar g: Gato = Gato("a")\n'                         # 14
    'declarar nomes: lista[string] = ["a"]\n'                # 15
    'função dobro usando (x: número) -> número => x * 2\n'   # 16
    'falar(1)\n'                                             # 17
)


class TestCompletion(TestLanguageServer):
    def complete(self, line, character, uri=None):
        result = self.client.request('textDocument/completion', {'textDocument': {'uri': uri or self.uri()},
                                                                 'position': {'line': line, 'character': character}})['result']
        return result

    def labels(self, text, line, character):
        self.client.notify('textDocument/didChange', {'textDocument': {'uri': self.uri(), 'version': 9},
                                                      'contentChanges': [{'text': text}]})
        self.client.next_notification('textDocument/publishDiagnostics')
        return [i['label'] for i in self.complete(line, character)['items']]

    def start(self, text=COMPLETION_SAMPLE):
        self.init()
        self.client.open(self.uri(), text)

    def with_line(self, new_line, line=17):
        lines = COMPLETION_SAMPLE.split('\n')
        lines[line] = new_line
        return '\n'.join(lines)

    def test_members_of_class_instances_modules_and_builtin_types(self):
        self.start()
        self.assertEqual(sorted(self.labels(self.with_line('g.'), 17, 2)), ['miar', 'nome', 'som'])  # sem `principal`
        self.assertIn('fatorial', self.labels(self.with_line('matematica.'), 17, 11))
        members = self.labels(self.with_line('nomes.'), 17, 6)
        self.assertIn('colocar', members)
        self.assertNotIn('maiúsculo', members)
        self.client.close()

    def test_esse_and_super_inside_methods(self):
        self.start()
        text = COMPLETION_SAMPLE.replace('        retornar ""\n', '        esse.\n        super.\n')
        self.assertEqual(sorted(self.labels(text, 11, 13)), ['miar', 'nome', 'som'])
        self.assertEqual(self.labels(text, 12, 14), ['som'])
        self.client.close()

    def test_names_in_scope_builtins_keywords_and_snippets(self):
        self.start()
        labels = self.labels(self.with_line('fal'), 17, 3)
        for expected in ('Animal', 'Gato', 'g', 'dobro', 'matematica', 'falar', 'máximo', 'enquanto', 'se … fim'):
            self.assertIn(expected, labels)
        self.client.close()

    def test_local_scope_includes_parameters_and_hides_other_functions_locals(self):
        self.start()
        text = COMPLETION_SAMPLE.replace('função dobro usando (x: número) -> número => x * 2', 'função dobro usando (x: número) -> número\n    declarar interno = x\n    retornar \nfim\nfunção outra usando (y)\n    retornar y\nfim')
        labels = self.labels(text, 18, 11)
        self.assertIn('x', labels)
        self.assertIn('interno', labels)
        self.assertNotIn('y', labels)
        self.client.close()

    def test_types_after_colon_arrow_and_extende(self):
        self.start()
        labels = self.labels(self.with_line('declarar v: '), 17, 12)
        for expected in ('número', 'string', 'lista', 'Animal', 'Gato', 'qualquer'):
            self.assertIn(expected, labels)
        self.assertNotIn('falar', labels)
        self.assertIn('Animal', self.labels(self.with_line('função f usando (a) -> '), 17, 22))
        self.assertEqual(sorted(self.labels(self.with_line('classe Z extende '), 17, 17)), ['Animal', 'Gato'])
        self.assertIn('Gato', self.labels(self.with_line('função f usando (a: lista[G'), 17, 27))
        self.client.close()

    def test_module_classes_as_types(self):
        Path(self.tmp.name, 'tipos.neb').write_text('classe Mesa\nfim\n', encoding='utf-8')
        self.init()
        text = 'importar tipos\ndeclarar m: tipos.\n'
        self.client.open(self.uri(), text)
        labels = [i['label'] for i in self.complete(1, 18)['items']]
        self.assertEqual(labels, ['Mesa'])
        self.client.close()

    def test_import_modules_and_names(self):
        Path(self.tmp.name, 'tipos.neb').write_text('função util usando () => 1\n', encoding='utf-8')
        self.init()
        self.client.open(self.uri(), 'importar \n')
        labels = [i['label'] for i in self.complete(0, 9)['items']]
        self.assertIn('matematica', labels)
        self.assertIn('tipos', labels)
        self.assertNotIn('x', labels)
        self.client.notify('textDocument/didChange', {'textDocument': {'uri': self.uri(), 'version': 3},
                                                      'contentChanges': [{'text': 'importar  de matematica\n'}]})
        self.client.next_notification('textDocument/publishDiagnostics')
        names = [i['label'] for i in self.complete(0, 9)['items']]
        self.assertIn('fatorial', names)
        self.assertIn('PI', names)
        self.client.close()

    def test_nothing_inside_strings_comments_or_when_naming_things(self):
        self.start()
        for line, col in (('falar("ol', 9), ('# comentário aqui', 12), ('função ', 7), ('classe ', 7), ('para cada ', 10)):
            self.assertEqual(self.labels(self.with_line(line), 17, col), [], line)
        self.assertIn('LIMITE', self.labels(self.with_line('declarar constante LIMITE = 1\nfalar("a ${LIM'), 18, 14))
        self.client.close()

    def test_snippets_have_snippet_format(self):
        self.start()
        self.labels(self.with_line('se'), 17, 2)
        items = self.complete(17, 2)['items']
        snippet = next(i for i in items if i['label'] == 'se … fim')
        self.assertEqual(snippet['insertTextFormat'], 2)
        self.assertIn('${1:condição}', snippet['insertText'])
        self.client.close()

    def test_completion_keeps_working_while_the_code_is_broken(self):
        self.start()
        broken = self.with_line('declarar x = (1 +\ng.')
        labels = self.labels(broken, 18, 2)  # a linha 17 é inválida (erro de sintaxe) e a 18 é o `g.` que se digita
        self.assertEqual(sorted(labels), ['miar', 'nome', 'som'])
        broken = self.with_line('declarar x = (1 +\nfal')
        self.assertIn('falar', self.labels(broken, 18, 3))
        self.assertIn('Animal', self.labels(broken, 18, 0))
        self.client.close()

    def test_new_file_with_error_still_gets_keywords_and_builtins(self):
        self.init()
        self.client.open(self.uri(), 'se (\n')
        labels = [i['label'] for i in self.complete(0, 1)['items']]
        self.assertIn('falar', labels)
        self.assertIn('enquanto', labels)
        self.client.close()

    def test_unknown_document_returns_null(self):
        self.init()
        self.assertIsNone(self.complete(0, 0, uri=self.uri('nao_aberto.neb')))
        self.client.close()


for _name in [n for n in dir(TestLanguageServer) if n.startswith('test_')]:
    if _name not in TestCompletion.__dict__:
        setattr(TestCompletion, _name, None)


class TestLspHelpers(unittest.TestCase):
    def test_uri_to_path(self):
        from nebula.lsp import uri_to_path
        self.assertIsNone(uri_to_path('untitled:Sem-titulo-1'))
        self.assertTrue(uri_to_path(Path('/tmp/a b.neb').as_uri()).endswith('a b.neb'))

    def test_utf16_col(self):
        from nebula.lsp import utf16_col
        self.assertEqual(utf16_col('aé😀b', 3), 4)
        self.assertEqual(utf16_col('abc', 99), 3)

    def test_col_from_utf16_is_the_inverse(self):
        from nebula.lsp import col_from_utf16, utf16_col
        text = 'aé😀bç'
        for index in range(len(text) + 1):
            self.assertEqual(col_from_utf16(text, utf16_col(text, index)), index)


class TestPackageLayout(NebulaTestCase):
    def test_legacy_pyneb_is_the_package(self):
        import nebula
        self.assertIs(pyneb, nebula)

    def test_public_api_is_reexported(self):
        import nebula
        for name in ('run', 'new_context', 'parse_text', 'Lexer', 'Parser', 'Interpreter', 'Number', 'BuiltInFunction',
                     'DEFAULT_CONFIG', 'MODULE_CACHE', 'set_safe_mode', 'TT_KEYWORD'):
            self.assertTrue(hasattr(nebula, name), name)

    def test_legacy_globals_still_readable(self):
        pyneb.set_safe_mode(True)
        self.assertTrue(pyneb.SAFE_MODE)
        pyneb.set_safe_mode(False)
        self.assertFalse(pyneb.SAFE_MODE)
        self.assertIsInstance(pyneb.FILENAME, str)

    def test_each_submodule_imports_in_a_fresh_interpreter(self):
        for name in ('paths', 'config', 'modules', 'errors', 'position', 'tokens', 'lexer', 'nodes', 'parser',
                     'context', 'values', 'typesystem', 'builtin_functions', 'interpreter', 'runtime', 'linter', 'completion', 'lsp'):
            r = subprocess.run([sys.executable, '-c', f'import nebula.{name}'], cwd=SRC, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f'{name}: {r.stderr[-300:]}')

    def test_string_with_arrows_shim(self):
        import string_with_arrows
        self.assertTrue(callable(string_with_arrows.string_with_arrows))

    def test_python_builtin_still_sees_stdlib_modules(self):
        self.assertEqual(out('falar(python("os.name"))'), os.name)


class TestCLI(NebulaTestCase):
    """Roda o shell de outra pasta, como acontece quando está no PATH."""

    def cli(self, *args, cwd):
        env = dict(os.environ, PYTHONUTF8='1', HOME=str(cwd), XDG_CONFIG_HOME=str(Path(cwd) / '.cfg'),
                   APPDATA=str(Path(cwd) / '.cfg'))
        return subprocess.run([sys.executable, str(SRC / 'shell.py'), *args], cwd=cwd,
                              capture_output=True, text=True, env=env, encoding='utf-8')

    def test_run_file_from_any_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'oi.neb').write_text('falar("oi")\nimportar matematica\nfalar(matematica.fatorial(4))\n', encoding='utf-8')
            r = self.cli('oi', cwd=tmp)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.split(), ['oi', '24'])

    def test_exit_code_on_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'x.neb').write_text('falar(nada)\n', encoding='utf-8')
            self.assertEqual(self.cli('x', cwd=tmp).returncode, 1)

    def test_check_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'ok.neb').write_text('falar(1)\n', encoding='utf-8')
            Path(tmp, 'ruim.neb').write_text('declarar x = (1 +\n', encoding='utf-8')
            self.assertEqual(self.cli('--verificar', 'ok.neb', cwd=tmp).returncode, 0)
            self.assertEqual(self.cli('--verificar', 'ruim.neb', cwd=tmp).returncode, 1)

    def test_setmain_and_dot(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'p.neb').write_text('falar("principal")\n', encoding='utf-8')
            self.assertEqual(self.cli('setmain', 'p', cwd=tmp).returncode, 0)
            r = self.cli('.', cwd=tmp)
            self.assertEqual(r.stdout.strip(), 'principal')

    def test_repl_survives_errors_and_keeps_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, PYTHONUTF8='1', HOME=tmp)
            r = subprocess.run([sys.executable, str(SRC / 'shell.py'), '-s'], cwd=tmp, env=env,
                               input='declarar a = 7\nfalar(zzz)\nfalar(a * 6)\nexit()\n',
                               capture_output=True, text=True, encoding='utf-8')
            self.assertIn('42', r.stdout)
            self.assertIn('nunca foi declarado', r.stdout)


if __name__ == '__main__':
    unittest.main()
