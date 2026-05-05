import unicodedata

CATEGORIAS = ['extinprag', 'vsafety', 'pessoal']
TIPOS = ['receita', 'custo']

CATEGORIAS_GASTO_FIXAS = [
    'moradia',
    'cartão',
    'alimentação',
    'supermercado',
    'educação',
    'telefone',
    'saúde',
    'investimento',
    'transporte',
    'outros',
]

PALAVRAS_CHAVE = {
    'moradia': ['aluguel', 'condominio', 'iptu', 'energia', 'agua', 'gas', 'luz', 'habitacao'],
    'cartão': ['cartao', 'fatura', 'nubank', 'itau', 'bradesco', 'santander', 'inter'],
    'alimentação': ['restaurante', 'lanche', 'comida', 'refeicao', 'ifood', 'pizza', 'hamburguer', 'cafe', 'padaria'],
    'supermercado': ['mercado', 'supermercado', 'feira', 'hortifruti', 'atacado'],
    'transporte': ['gasolina', 'combustivel', 'uber', 'onibus', 'pedagio', 'estacionamento', 'posto', 'pneu', 'mecanico', '99'],
    'saúde': ['farmacia', 'medico', 'consulta', 'exame', 'dentista', 'hospital', 'remedio', 'plano'],
    'educação': ['curso', 'livro', 'escola', 'faculdade', 'treinamento', 'mensalidade'],
    'telefone': ['celular', 'internet', 'telefone', 'tim', 'vivo', 'claro', 'oi', 'wifi', 'chip'],
    'investimento': ['investimento', 'aplicacao', 'poupanca', 'cdb', 'acoes', 'fundo', 'tesouro'],
}


def _normalizar(s: str) -> str:
    return unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii').lower()


def detectar_categoria_gasto(descricao: str, categorias_custom: list = None) -> str:
    desc_norm = _normalizar(descricao)
    for categoria, palavras in PALAVRAS_CHAVE.items():
        for palavra in palavras:
            if palavra in desc_norm:
                return categoria
    if categorias_custom:
        for cat in categorias_custom:
            if _normalizar(cat) in desc_norm:
                return cat
    return 'outros'


def _parse_valor(s: str) -> float:
    s = s.strip()
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    else:
        s = s.replace(',', '.')
    return round(float(s), 2)


def parse(texto: str, categorias_custom: list = None) -> dict | None:
    """
    Formato: receita 1200 extinprag descrição
             custo 150 vsafety gasolina #transporte  (categoria explícita com #)
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

    empresa = partes[2]
    if empresa not in CATEGORIAS:
        return None

    texto_desc = ' '.join(partes[3:])
    categoria_gasto = None

    if '#' in texto_desc:
        idx = texto_desc.rfind('#')
        descricao = texto_desc[:idx].strip()
        cat_raw = texto_desc[idx + 1:].strip()
        if cat_raw:
            categoria_gasto = _normalizar(cat_raw)
    else:
        descricao = texto_desc

    if not categoria_gasto:
        categoria_gasto = 'receita' if tipo == 'receita' else detectar_categoria_gasto(descricao, categorias_custom)

    return {
        'tipo': tipo,
        'valor': valor,
        'empresa': empresa,
        'categoria_gasto': categoria_gasto,
        'descricao': descricao,
    }


def formatar_brl(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
