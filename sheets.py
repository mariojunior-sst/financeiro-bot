import json
import os
from datetime import datetime, timedelta

import gspread
from google.oauth2.service_account import Credentials
from lancamentos import _normalizar

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]

CABECALHO = ['Data', 'Hora', 'Tipo', 'Empresa', 'Categoria', 'Valor', 'Descrição']
CABECALHO_CATEGORIAS = ['Nome']


def _client():
    creds_json = os.environ['GOOGLE_CREDENTIALS']
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)


def _planilha():
    return _client().open_by_key(os.environ['SHEET_ID'])


def _migrar_lancamentos_se_necessario(ws):
    """Detecta formato antigo (sem coluna Empresa) e migra automaticamente."""
    header = ws.row_values(1)
    if not header:
        return
    # Formato antigo: ['Data','Hora','Tipo','Categoria','Valor','Descrição'] (6 colunas)
    if len(header) == 6 and header[3] == 'Categoria' and header[4] == 'Valor':
        ws.update_cell(1, 4, 'Empresa')
        ws.insert_cols([['']], col=5)
        ws.update_cell(1, 5, 'Categoria')


def _aba_lancamentos():
    planilha = _planilha()
    try:
        ws = planilha.worksheet('Lançamentos')
        _migrar_lancamentos_se_necessario(ws)
    except gspread.WorksheetNotFound:
        ws = planilha.add_worksheet('Lançamentos', rows=5000, cols=10)
        ws.append_row(CABECALHO)
        ws.format('A1:G1', {'textFormat': {'bold': True}})
    return ws


def _aba_categorias():
    planilha = _planilha()
    try:
        ws = planilha.worksheet('Categorias')
    except gspread.WorksheetNotFound:
        ws = planilha.add_worksheet('Categorias', rows=100, cols=3)
        ws.append_row(CABECALHO_CATEGORIAS)
        ws.format('A1', {'textFormat': {'bold': True}})
    return ws


def registrar(tipo: str, valor: float, empresa: str, categoria: str, descricao: str) -> None:
    ws = _aba_lancamentos()
    agora = datetime.now()
    ws.append_row([
        agora.strftime('%d/%m/%Y'),
        agora.strftime('%H:%M'),
        tipo.upper(),
        empresa.upper(),
        categoria.title(),
        round(valor, 2),
        descricao,
    ], value_input_option='RAW')


def ultimos_lancamentos(n: int = 10) -> list[dict]:
    ws = _aba_lancamentos()
    registros = ws.get_all_records()
    return registros[-n:] if len(registros) >= n else registros


def carregar_df():
    """DataFrame normalizado de toda a planilha — base das análises do bot.

    É a mesma função que o dashboard usa, então /resumo e painel sempre
    mostram o mesmo número.
    """
    import analise

    ws = _aba_lancamentos()
    registros = ws.get_all_records(value_render_option='UNFORMATTED_VALUE')
    return analise.preparar(registros)


def listar_categorias_custom() -> list[str]:
    try:
        ws = _aba_categorias()
        registros = ws.get_all_records()
        return [_normalizar(r['Nome']) for r in registros if r.get('Nome')]
    except Exception:
        return []


def salvar_categoria_custom(nome: str) -> None:
    ws = _aba_categorias()
    nome_norm = _normalizar(nome)
    existentes = [_normalizar(r['Nome']) for r in ws.get_all_records() if r.get('Nome')]
    if nome_norm not in existentes:
        ws.append_row([nome.lower()])


# Sem coluna de valor a cadastrar: conta fixa é fixa no compromisso, não no
# valor. 'Último Valor' é preenchido pelo bot na baixa, só como referência.
CABECALHO_CONTAS = [
    'Nome', 'Dia', 'Empresa', 'Categoria', 'Ativa', 'Pago Até', 'Último Valor',
    'Observação',
]

COL_ATIVA = 5
COL_PAGO_ATE = 6
COL_ULTIMO_VALOR = 7


def _aba_contas():
    planilha = _planilha()
    try:
        ws = planilha.worksheet('Contas Fixas')
    except gspread.WorksheetNotFound:
        ws = planilha.add_worksheet('Contas Fixas', rows=200, cols=8)
        ws.append_row(CABECALHO_CONTAS)
        ws.format('A1:H1', {'textFormat': {'bold': True}})
    return ws


def _num(valor) -> float:
    """Aceita 2350, '2350.50' e '2.350,50' — a planilha devolve os três."""
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor or '0').replace('R$', '').strip()
    if ',' in texto and '.' in texto:
        texto = texto.replace('.', '').replace(',', '.')
    else:
        texto = texto.replace(',', '.')
    try:
        return float(texto)
    except ValueError:
        return 0.0


def _competencia_texto(valor) -> str:
    """Normaliza 'Pago Até' para AAAA-MM.

    A gravação força texto, mas a coluna também é editável na mão dentro do
    Sheets — e ali '2026-08' vira data, que volta como número de série. Sem
    esta conversão a conta pareceria eternamente não paga, em silêncio.
    """
    if valor in (None, ''):
        return ''
    if hasattr(valor, 'strftime'):
        return valor.strftime('%Y-%m')
    if isinstance(valor, (int, float)):
        # Serial do Sheets: dias desde 30/12/1899.
        return (datetime(1899, 12, 30) + timedelta(days=int(valor))).strftime('%Y-%m')
    return str(valor).strip()[:7]


def listar_contas() -> list[dict]:
    """Contas fixas cadastradas, com o número da linha para poder atualizar."""
    ws = _aba_contas()
    registros = ws.get_all_records(value_render_option='UNFORMATTED_VALUE')
    contas = []
    for i, r in enumerate(registros):
        nome = str(r.get('Nome') or '').strip()
        if not nome:
            continue
        ultimo = _num(r.get('Último Valor'))
        contas.append({
            'linha': i + 2,  # +1 do cabeçalho, +1 porque a planilha é 1-based
            'nome': nome,
            'dia': int(_num(r.get('Dia')) or 1),
            'empresa': str(r.get('Empresa') or 'pessoal').strip().lower(),
            'categoria': str(r.get('Categoria') or 'outros').strip().lower(),
            'ativa': str(r.get('Ativa') or 'SIM').strip().upper() != 'NÃO',
            'pago_ate': _competencia_texto(r.get('Pago Até')),
            'ultimo_valor': ultimo or None,
            'observacao': str(r.get('Observação') or '').strip(),
        })
    return contas


def salvar_conta(nome: str, dia: int, empresa: str, categoria: str,
                 observacao: str = '') -> None:
    ws = _aba_contas()
    ws.append_row([
        nome.strip(),
        int(dia),
        empresa.strip().upper(),
        categoria.strip().lower(),
        'SIM',
        '',
        '',
        observacao.strip(),
    ], value_input_option='RAW')


def marcar_conta_paga(linha: int, competencia: str, valor: float = None) -> None:
    """Grava a competência quitada e o valor efetivamente pago naquele mês.

    Vai por `update` com RAW de propósito: o `update_cell` usa USER_ENTERED e o
    Sheets converteria '2026-08' em data, quebrando a comparação de atraso.
    """
    ws = _aba_contas()
    if valor is None:
        ws.update([[competencia]], f'F{linha}', value_input_option='RAW')
    else:
        # Uma chamada só para as duas colunas — metade das idas à API.
        ws.update([[competencia, round(float(valor), 2)]], f'F{linha}:G{linha}',
                  value_input_option='RAW')


def alternar_conta_ativa(linha: int, ativa: bool) -> None:
    ws = _aba_contas()
    ws.update_cell(linha, COL_ATIVA, 'SIM' if ativa else 'NÃO')
