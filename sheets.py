import json
import os
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

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


def resumo_mes(ano: int = None, mes: int = None) -> dict:
    agora = datetime.now()
    ano = ano or agora.year
    mes = mes or agora.month
    prefixo_mes = f"{mes:02d}/{ano}"

    ws = _aba_lancamentos()
    registros = ws.get_all_records()

    resultado = {
        'extinprag': {'receita': 0.0, 'custo': 0.0},
        'vsafety':   {'receita': 0.0, 'custo': 0.0},
        'pessoal':   {'receita': 0.0, 'custo': 0.0},
    }

    for r in registros:
        data = r.get('Data', '')
        if len(data) < 10 or data[3:10] != prefixo_mes:
            continue

        # Suporte ao formato antigo ('Categoria' era empresa) e novo ('Empresa')
        empresa = r.get('Empresa', r.get('Categoria', '')).lower()
        tipo = r.get('Tipo', '').lower()
        try:
            valor = float(str(r.get('Valor', 0)).replace(',', '.'))
        except ValueError:
            continue

        if empresa in resultado and tipo in ('receita', 'custo'):
            resultado[empresa][tipo] += valor

    return resultado


def ultimos_lancamentos(n: int = 10) -> list[dict]:
    ws = _aba_lancamentos()
    registros = ws.get_all_records()
    return registros[-n:] if len(registros) >= n else registros


def listar_categorias_custom() -> list[str]:
    try:
        ws = _aba_categorias()
        registros = ws.get_all_records()
        return [r['Nome'].lower() for r in registros if r.get('Nome')]
    except Exception:
        return []


def salvar_categoria_custom(nome: str) -> None:
    ws = _aba_categorias()
    ws.append_row([nome.lower()])
