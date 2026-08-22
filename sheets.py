import json
import os
from datetime import datetime

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
