CATEGORIAS = ['extinprag', 'vsafety', 'pessoal']
TIPOS = ['receita', 'custo']


def _parse_valor(s: str) -> float:
    # Suporta formato brasileiro (1.200,50) e internacional (1200.50)
    s = s.strip()
    if ',' in s and '.' in s:
        # Ex: 1.200,50 → remove ponto de milhar, troca vírgula por ponto
        s = s.replace('.', '').replace(',', '.')
    else:
        s = s.replace(',', '.')
    return float(s)


def parse(texto: str) -> dict | None:
    """
    Interpreta mensagens no formato:
      receita 1200 extinprag recarga de extintores
      custo 350,50 vsafety deslocamento
      receita 800 pessoal aluguel

    Retorna dict com tipo, valor, categoria, descricao ou None se inválido.
    """
    partes = texto.strip().lower().split()

    if len(partes) < 3:
        return None

    tipo = partes[0]
    if tipo not in TIPOS:
        return None

    try:
        valor = _parse_valor(partes[1])
    except ValueError:
        return None

    if valor <= 0:
        return None

    categoria = partes[2]
    if categoria not in CATEGORIAS:
        return None

    descricao = ' '.join(partes[3:]) if len(partes) > 3 else ''

    return {
        'tipo': tipo,
        'valor': valor,
        'categoria': categoria,
        'descricao': descricao,
    }


def formatar_brl(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
