"""Nebula CLI / shell.

Uso:
    nebula arquivo.neb          executa um arquivo
    nebula --shell              abre o shell interativo
    nebula setmain arquivo.neb  define o arquivo principal  (e `nebula .` executa)
    nebula --verificar arq.neb  só checa a sintaxe, sem executar
    nebula --seguro arq.neb     executa bloqueando executar/python/arquivos
"""
import argparse
import json
import os
import sys
import threading
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import nebula as pyneb  # noqa: E402  (precisa do sys.path acima)

# --------------------------------------------------------------------------
# Cores: usa termcolor se existir; senão, um fallback ANSI simples.
# --------------------------------------------------------------------------
try:
    from termcolor import colored, cprint
except ImportError:  # termcolor é opcional agora
    _COLORS = {'red': 31, 'green': 32, 'yellow': 33, 'blue': 34, 'magenta': 35, 'cyan': 36,
               'light_red': 91, 'light_yellow': 93}
    _ATTRS = {'bold': 1, 'dark': 2, 'underline': 4, 'blink': 5}

    def colored(text, color=None, attrs=None):
        if not sys.stdout.isatty():
            return text
        codes = []
        if color in _COLORS:
            codes.append(_COLORS[color])
        codes += [_ATTRS[a] for a in (attrs or []) if a in _ATTRS]
        return f"\033[{';'.join(map(str, codes))}m{text}\033[0m" if codes else text

    def cprint(text, color=None, attrs=None, **kwargs):
        print(colored(text, color, attrs), **kwargs)

if os.name == 'nt':
    os.system('')  # habilita sequências ANSI no console do Windows

# --------------------------------------------------------------------------
# Configuração (por usuário: não exige permissão de administrador)
# --------------------------------------------------------------------------


def config_dir():
    if os.name == 'nt':
        base = os.environ.get('APPDATA') or str(Path.home() / 'AppData' / 'Roaming')
        return Path(base) / 'Nebula'
    base = os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
    return Path(base) / 'nebula'


CONFIG_FILE = config_dir() / 'config'
LEGACY_CONFIG = BASE_DIR / '.config'  # formato antigo (ainda é lido)


def is_inno_install():
    return (BASE_DIR / 'unins000.exe').exists() or (BASE_DIR.parent / 'unins000.exe').exists()


def read_config():
    for candidate in (CONFIG_FILE, LEGACY_CONFIG):
        if candidate.exists():
            config = {}
            for chunk in candidate.read_text(encoding='utf-8').split(';'):
                if '=' in chunk:
                    key, value = chunk.split('=', 1)
                    config[key.strip()] = value.strip().strip("'")
            return config
    return {}


def write_config(main_file):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    content = (
        f"access_point_main={main_file};\n"
        f"version={pyneb.DEFAULT_CONFIG['version']};\n"
        f"inno_setup='{'true' if is_inno_install() else 'false'}';\n"
    )
    CONFIG_FILE.write_text(content, encoding='utf-8')


# --------------------------------------------------------------------------
# Resolução de arquivos (sempre a partir da pasta onde o comando foi digitado)
# --------------------------------------------------------------------------


def resolve_script(name):
    name = name.replace('\\', '/')
    if name.startswith('pyneb/src/'):
        name = name[len('pyneb/src/'):]
    names = [name] if name.endswith('.neb') else [name + '.neb', name]
    bases = [Path.cwd(), BASE_DIR.parent]  # BASE_DIR.parent = compatibilidade com o antigo '../'
    for n in names:
        p = Path(n)
        if p.is_absolute():
            if p.is_file():
                return p
            continue
        for base in bases:
            if (base / p).is_file():
                return base / p
    return None


def display_path(path):
    try:
        return os.path.relpath(path)
    except ValueError:  # outro drive no Windows
        return str(path)


def print_error(error):
    cprint(error.as_string(), 'red', attrs=['bold'])


def run_file(path):
    try:
        text = Path(path).read_text(encoding='utf-8-sig')
    except OSError as e:
        cprint(f"Não foi possível ler '{path}': {e}", 'red', attrs=['bold'])
        return 1
    if not text.strip():
        print("Arquivo vazio, favor adicionar algum código.")
        return 1
    _, error, _ = pyneb.run(display_path(path), text)
    if error:
        print_error(error)
        return 1
    return 0


def check_file(path):
    text = Path(path).read_text(encoding='utf-8-sig')
    _, error = pyneb.parse_text(display_path(path), text)
    if error:
        print_error(error)
        return 1
    cprint(f"{display_path(path)}: sintaxe OK", 'green', attrs=['bold'])
    return 0


# --------------------------------------------------------------------------
# Shell interativo
# --------------------------------------------------------------------------

HELP_TEXT = (
    "Comandos:\n"
    "  help      mostra esta mensagem\n"
    "  exit()    sai do shell\n"
    "  <código>  executa código Nebula (as variáveis continuam entre as linhas)\n"
    "Blocos (se/enquanto/função/classe...) continuam até o 'fim'.\n"
    "Linha vazia durante um bloco incompleto executa o que foi digitado.\n"
)


def block_depth(text):
    """Quantos blocos (se/enquanto/para/função/classe/tentar) ainda estão abertos.

    O parser aceita alguns blocos sem 'fim' no fim do texto, então só olhar o erro
    de sintaxe não basta; contamos aberturas e 'fim' linha a linha.
    """
    tokens, error = pyneb.Lexer('<stdin>', text).make_tokens()
    if error:
        return 0
    depth = 0
    line = []
    for tok in tokens + [None]:
        if tok is not None and tok.type not in (pyneb.TT_NEWLINE, pyneb.TT_EOF):
            line.append(tok)
            continue
        if line:
            first, last = line[0], line[-1]
            closes = sum(1 for t in line if t.matches(pyneb.TT_KEYWORD, 'fim'))
            opens = 0
            has_arrow = any(t.type == pyneb.TT_ARROW for t in line)
            if first.matches(pyneb.TT_KEYWORD, 'caso'):
                opens = 0
            elif first.matches(pyneb.TT_KEYWORD, 'senão'):
                opens = 0  # continuação do mesmo bloco 'se' (compartilha o 'fim')
            elif last.type == pyneb.TT_KEYWORD and last.value in ('então', 'faça'):
                opens = 1
            elif first.matches(pyneb.TT_KEYWORD, 'tentar') and len(line) == 1:
                opens = 1
            elif first.matches(pyneb.TT_KEYWORD, 'classe') and closes == 0:
                opens = 1
            elif first.matches(pyneb.TT_KEYWORD, 'função') and not has_arrow and closes == 0:
                opens = 1
            depth = max(0, depth + opens - closes)
        line = []
    return depth


def needs_more_input(text):
    """True se o código parece incompleto (ex.: bloco sem 'fim')."""
    if block_depth(text) > 0:
        return True
    _, error = pyneb.parse_text('<stdin>', text)
    if not error or error.pos_start is None:
        return False
    return error.pos_start.idx >= len(text.rstrip())


def shell():
    try:
        import readline  # noqa: F401  (histórico/setas em Linux/macOS)
        has_readline = True
    except ImportError:
        has_readline = False

    cprint("Nebula Shell", 'blue', attrs=['bold', 'underline'])
    cprint("Digite 'exit()' para sair e 'help' para ajuda.", 'green')
    print()

    context = pyneb.new_context()
    buffer = []

    while True:
        prompt = 'nebula >> ' if not buffer else '   ...  '
        try:
            line = input(prompt if has_readline else colored(prompt, 'magenta'))
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print()
            buffer = []
            continue

        if not buffer:
            stripped = line.strip()
            if stripped == 'exit()':
                return 0
            if stripped == '':
                continue
            if stripped == 'help':
                print(HELP_TEXT)
                continue
        elif line.strip() == '':
            pass  # linha vazia: força a execução do que está no buffer
        buffer.append(line)
        text = '\n'.join(buffer)

        if line.strip() != '' and needs_more_input(text):
            continue

        buffer = []
        result, error, _ = pyneb.run('<stdin>', text, context)
        if error:
            print_error(error)  # erro não encerra mais o shell
            continue
        if result is not None:
            try:
                cprint(result.__sstr__(), 'light_yellow', attrs=['bold'])
            except Exception:
                cprint(str(result), 'light_yellow', attrs=['bold'])


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


SEVERITY_COLORS = {'erro': 'red', 'aviso': 'yellow', 'dica': 'cyan'}


def lint_command(args):
    from nebula import linter

    if args.rules:
        for code, (severity, description) in linter.RULES.items():
            cprint(f'{code}  {severity:5}  {description}', SEVERITY_COLORS[severity])
        return 0

    paths = args.extra or ['.']
    missing = [p for p in paths if not Path(p).exists()]
    if missing:
        cprint(f"Não encontrei: {', '.join(missing)}", 'cyan', attrs=['bold'])
        return 2
    ignore = {c.strip().upper() for c in args.ignore.split(',') if c.strip()}
    results = linter.lint_paths(paths, ignore=ignore, hints=args.hints)
    counts = {'erro': 0, 'aviso': 0, 'dica': 0}
    all_diagnostics = []
    for diagnostics in results.values():
        for d in diagnostics:
            counts[d.severity] += 1
            all_diagnostics.append(d)

    if args.json:
        print(json.dumps([d.to_dict() for d in all_diagnostics], ensure_ascii=False, indent=2))
    else:
        for file, diagnostics in results.items():
            if not diagnostics:
                continue
            lines = Path(file).read_text(encoding='utf-8-sig').split('\n')
            for d in diagnostics:
                head = f'{display_path(file)}:{d.line}:{d.col}: '
                print(head + colored(f'{d.severity} {d.code}', SEVERITY_COLORS[d.severity], attrs=['bold']) + f': {d.message}')
                if 0 < d.line <= len(lines):
                    line = lines[d.line - 1].rstrip('\r').expandtabs(4)
                    width = max(1, (d.end_col - d.col) if d.end_line == d.line else len(line) - d.col + 1)
                    print('    ' + line)
                    print('    ' + ' ' * (len(lines[d.line - 1][:d.col - 1].expandtabs(4))) + colored('^' * width, SEVERITY_COLORS[d.severity]))
        summary = f"{len(results)} arquivo(s): {counts['erro']} erro(s), {counts['aviso']} aviso(s)"
        if args.hints:
            summary += f", {counts['dica']} dica(s)"
        cprint(summary, 'red' if counts['erro'] else ('yellow' if counts['aviso'] else 'green'), attrs=['bold'])
    return 1 if counts['erro'] or (args.strict and counts['aviso']) else 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog='nebula',
        description='Nebula — linguagem de programação em português (interpretador PyNeb).',
        allow_abbrev=False,
    )
    parser.add_argument('alvo', nargs='?', help='arquivo .neb, ou comando: setmain, init, ., special-keys')
    parser.add_argument('extra', nargs='*', help='argumentos do comando')
    parser.add_argument('-s', '--shell', action='store_true', help='abre o shell interativo')
    parser.add_argument('-v', '--version', action='store_true', help='mostra a versão')
    parser.add_argument('-c', '--config', action='store_true', help='mostra a configuração (opcional: chave)')
    parser.add_argument('--p', action='store_true', dest='show_path', help='mostra o caminho do launcher')
    parser.add_argument('--verificar', '--check', action='store_true', dest='check', help='só verifica a sintaxe')
    parser.add_argument('--stdio', action='store_true', help='(lsp) aceito por compatibilidade com editores; o servidor sempre usa stdio')
    parser.add_argument('--json', action='store_true', help='(lint) saída em JSON')
    parser.add_argument('--ignore', default='', help='(lint) códigos a ignorar, separados por vírgula: NEB202,NEB204')
    parser.add_argument('--dicas', action='store_true', dest='hints', help='(lint) mostra também as dicas')
    parser.add_argument('--strict', action='store_true', help='(lint) avisos também fazem o comando falhar')
    parser.add_argument('--regras', action='store_true', dest='rules', help='(lint) lista todas as regras')
    parser.add_argument('--seguro', '--safe', action='store_true', dest='safe',
                        help='modo seguro: bloqueia executar, python, ler_arquivo e escrever_arquivo')
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.safe:
        pyneb.set_safe_mode(True)

    target = args.alvo

    if args.version:
        cprint(pyneb.DEFAULT_CONFIG['version'], 'blue', attrs=['underline'])
        return 0

    if args.config:
        key = target
        if key and key in pyneb.DEFAULT_CONFIG:
            print(pyneb.DEFAULT_CONFIG[key])
        else:
            print(pyneb.DEFAULT_CONFIG)
        return 0

    if args.show_path or target in ('__path__', '--p'):
        launcher = BASE_DIR / 'nebula.bat'
        if not launcher.exists():
            launcher = BASE_DIR.parent / 'nebula.bat'
        print(launcher)
        return 0

    if args.shell or target in ('__shell__', 'shell'):
        return shell()

    if args.rules or target == 'lint':
        return lint_command(args)

    if target == 'lsp':
        from nebula.lsp import serve
        return serve()

    if target is None:
        parser.print_help()
        return 1

    if target == 'special-keys':
        for k, v in pyneb.DEFAULT_CONFIG['special-keys'].items():
            if k == 'special-keys':
                continue
            print(f'{k}: {v}\n')
        return 0

    if target == 'setmain':
        if not args.extra:
            cprint("Uso: nebula setmain <arquivo>", 'yellow', attrs=['bold'])
            return 1
        script = resolve_script(args.extra[0])
        if script is None:
            cprint(f"Arquivo {args.extra[0]} não encontrado.", 'cyan', attrs=['bold'])
            return 1
        write_config(str(script.resolve()))
        cprint('Sucesso!', 'green', attrs=['bold'])
        return 0

    if target in ('iniciar', 'init', '--init'):
        main_file = 'not-defined'
        if args.extra:
            script = resolve_script(args.extra[0])
            main_file = str(script.resolve()) if script else args.extra[0]
        write_config(main_file)
        cprint('Sucesso!', 'green', attrs=['bold'])
        return 0

    if target == '.':
        main_file = read_config().get('access_point_main', 'not-defined')
        if main_file in ('', 'not-defined'):
            cprint("Parece que um arquivo principal não foi definido, use nebula setmain <arquivo> para definir um arquivo principal.",
                   'yellow', attrs=['bold'])
            return 1
        path = Path(main_file)
        if not path.is_absolute():  # formato antigo (relativo à pasta do shell)
            path = (BASE_DIR / path).resolve()
        if not path.is_file():
            cprint(f"Arquivo {main_file} não encontrado. Use: \"nebula setmain <arquivo>\"", 'cyan', attrs=['bold'])
            return 1
        return check_file(path) if args.check else run_file(path)

    script = resolve_script(target)
    if script is None:
        cprint(f"Arquivo {target} não encontrado. Use: \"nebula <arquivo>\"", 'cyan', attrs=['bold'])
        return 1
    return check_file(script) if args.check else run_file(script)


def run_in_big_stack(argv):
    """Executa em uma thread com pilha grande (recursão profunda em Nebula)."""
    result = {'code': 1}

    def target():
        try:
            result['code'] = main(argv)
        except SystemExit as e:
            result['code'] = e.code if isinstance(e.code, int) else 1
        except BrokenPipeError:  # ex.: `nebula lint x | head`
            result['code'] = 0
            try:
                sys.stdout = open(os.devnull, 'w')
            except OSError:
                pass

    try:
        threading.stack_size(256 * 1024 * 1024)
    except (ValueError, RuntimeError):
        return main(argv)

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    try:
        while thread.is_alive():
            thread.join(0.1)
    except KeyboardInterrupt:
        print("\nInterrompido.")
        os._exit(130)
    return result['code']


if __name__ == '__main__':
    argv = sys.argv[1:]
    interactive = any(a in ('-s', '--shell', '__shell__', 'shell') for a in argv)
    sys.exit(main(argv) if interactive else run_in_big_stack(argv))
