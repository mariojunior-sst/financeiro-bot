import json
import os
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]

CABECALHO = ['Data', 'Hora', 'Tipo', 'Categoria', 'Valor', 'Descrição']


def _client():
    creds_json = os.environ['GOOGLE_CREDENTIALS']
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)


def _planilha():
    return _client().open_by_key(os.environ['SHEET_ID'])


def _aba_lancamentos():
    planilha = _planilha()
    try:
        ws = planilha.worksheet('Lançamentos')
    except gspread.WorksheetNotFound:
        ws = planilha.add_worksheet('Lançamentos', rows=5000, cols=10)
        ws.append_row(CABECALHO)
        ws.format('A1:F1', {'textFormat': {'bold': True}})
    return ws


def registrar(tipo: str, valor: float, categoria: str, descricao: str) -> None:
    ws = _aba_lancamentos()
    agora = datetime.now()
    ws.append_row([
        agora.strftime('%d/%m/%Y'),
        agora.strftime('%H:%M'),
        tipo.upper(),
        categoria.upper(),
        valor,
        descricao,
    ])


def resumo_mes(ano: int = None, mes: int = None) -> dict:
    """
    Retorna totais de receita e custo por categoria para o mês/ano informado.
    Padrão: mês atual.
    """
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
        # Data no formato DD/MM/YYYY → pegar MM/YYYY a partir da posição 3
        if len(data) < 10 or data[3:10] != prefixo_mes:
            continue

        cat = r.get('Categoria', '').lower()
        tipo = r.get('Tipo', '').lower()
        try:
            valor = float(str(r.get('Valor', 0)).replace(',', '.'))
        except ValueError:
            continue

        if cat in resultado and tipo in ('receita', 'custo'):
            resultado[cat][tipo] += valor

    return resultado


def ultimos_lancamentos(n: int = 10) -> list[dict]:
    ws = _aba_lancamentos()
    registros = ws.get_all_records()
    return registros[-n:] if len(registros) >= n else registros
