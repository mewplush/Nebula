"""Formata o trecho de código com setas (^^^) apontando onde o erro aconteceu."""

TAB_SIZE = 4


def _visual_col(line, col):
    """Coluna visual de `col`, considerando tabs (que antes eram removidos e desalinhavam a seta)."""
    return len(line[:col].expandtabs(TAB_SIZE))


def string_with_arrows(text, pos_start, pos_end):
    if text is None or pos_start is None or pos_end is None:
        return "Nenhuma posição foi encontrada para esse erro."

    try:
        lines = text.split('\n')
        first = max(0, min(pos_start.ln, len(lines) - 1))
        last = max(first, min(pos_end.ln, len(lines) - 1))

        result = []
        for ln in range(first, last + 1):
            line = lines[ln]
            col_start = pos_start.col if ln == first else 0
            col_end = pos_end.col if ln == last else len(line)

            start = _visual_col(line, col_start)
            end = _visual_col(line, col_end)
            width = max(1, end - start)

            result.append(line.expandtabs(TAB_SIZE))
            result.append(' ' * start + '^' * width)

        return '\n'.join(result)
    except AttributeError:
        return "Nenhuma posição foi encontrada para esse erro."
