"""
Camada de análise financeira.

Fonte única de verdade para os números: o bot (Telegram) e o dashboard
(Streamlit) consomem as mesmas funções, então o /resumo e o painel nunca
divergem.

Recebe sempre um DataFrame já normalizado por `preparar()`.
"""

import re
import unicodedata
from datetime import date

import pandas as pd

# ---------------------------------------------------------------- constantes

EMPRESAS_ORDEM = ['EXTINPRAG', 'VSAFETY', 'PESSOAL']

MESES_ABREV = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun',
               'jul', 'ago', 'set', 'out', 'nov', 'dez']

MESES_EXTENSO = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
                 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']

# Chave normalizada (sem acento, minúscula) -> rótulo canônico de exibição.
# É isto que elimina as duplicatas do tipo "Cartão" / "cartão" / "CARTAO"
# que hoje aparecem como fatias separadas no gráfico.
CATEGORIAS_CANONICAS = {
    'moradia': 'Moradia',
    'cartao': 'Cartão',
    'alimentacao': 'Alimentação',
    'restaurante': 'Alimentação',
    'supermercado': 'Supermercado',
    'educacao': 'Educação',
    'telefone': 'Telefone e Internet',
    'internet': 'Telefone e Internet',
    'saude': 'Saúde',
    'investimento': 'Investimento',
    'transporte': 'Transporte',
    'combustivel': 'Transporte',
    'ipva': 'Impostos e Taxas',
    'imposto': 'Impostos e Taxas',
    'impostos': 'Impostos e Taxas',
    'taxas': 'Impostos e Taxas',
    'financiamento': 'Financiamento',
    'emprestimo': 'Financiamento',
    'pet': 'Pet',
    'lazer': 'Lazer',
    'vestuario': 'Vestuário',
    'salario': 'Salário',
    'receita': 'Receita',
    'outros': 'Outros',
}

SEM_CATEGORIA = 'Sem categoria'
ROTULO_OUTROS = 'Outros'


def _sem_acento(s) -> str:
    texto = unicodedata.normalize('NFKD', str(s))
    return texto.encode('ascii', 'ignore').decode('ascii').lower().strip()


def normalizar_categoria(valor) -> str:
    """Agrupa variações de escrita da mesma categoria sob um rótulo único."""
    bruto = str(valor).strip()
    if bruto in ('', '0', 'nan', 'None'):
        return SEM_CATEGORIA
    chave = _sem_acento(bruto)
    if chave in ('', '0', 'nan', 'none'):
        return SEM_CATEGORIA
    return CATEGORIAS_CANONICAS.get(chave, bruto.strip().capitalize())


def para_float(valor) -> float:
    """Converte o que vier da planilha em float.

    A célula pode chegar como número (UNFORMATTED_VALUE) ou como texto no
    padrão brasileiro — `R$ 1.234,56`, onde o ponto é separador de milhar.
    Converter só trocando vírgula por ponto transformaria isso em lixo.
    """
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return 0.0 if pd.isna(valor) else float(valor)

    texto = re.sub(r'[^\d,.\-]', '', str(valor))
    if not texto or texto in ('-', '.', ','):
        return 0.0

    if ',' in texto and '.' in texto:
        # O separador decimal é o último a aparecer.
        if texto.rfind(',') > texto.rfind('.'):
            texto = texto.replace('.', '').replace(',', '.')
        else:
            texto = texto.replace(',', '')
    elif ',' in texto:
        texto = texto.replace(',', '.')

    try:
        return float(texto)
    except ValueError:
        return 0.0


def rotulo_mes(periodo) -> str:
    """Period('2026-08') -> 'ago/26'."""
    p = periodo if isinstance(periodo, pd.Period) else pd.Period(periodo, freq='M')
    return f"{MESES_ABREV[p.month - 1]}/{str(p.year)[2:]}"


def rotulo_mes_extenso(periodo) -> str:
    p = periodo if isinstance(periodo, pd.Period) else pd.Period(periodo, freq='M')
    return f"{MESES_EXTENSO[p.month - 1].capitalize()}/{p.year}"


def brl(valor: float, casas: int = 2) -> str:
    txt = f"{valor:,.{casas}f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    return f"R$ {txt}"


def brl_compacto(valor: float) -> str:
    """Para eixos e rótulos curtos: R$ 12,4 mil."""
    absv = abs(valor)
    if absv >= 1_000_000:
        return f"R$ {valor / 1_000_000:.1f}M".replace('.', ',')
    if absv >= 1_000:
        return f"R$ {valor / 1_000:.1f} mil".replace('.', ',')
    return f"R$ {valor:.0f}"


def pct(valor: float, casas: int = 1) -> str:
    return f"{valor:.{casas}f}%".replace('.', ',')


# --------------------------------------------------------------- preparação

def preparar(registros) -> pd.DataFrame:
    """Recebe a lista de dicts da planilha e devolve o DataFrame canônico."""
    df = registros.copy() if isinstance(registros, pd.DataFrame) else pd.DataFrame(registros)

    colunas_vazias = ['Data', 'Tipo', 'Empresa', 'Categoria', 'Valor',
                      'Descrição', 'Mes', 'MesLabel', 'Dia']
    if df.empty:
        return pd.DataFrame(columns=colunas_vazias)

    # Compatibilidade com o formato antigo da planilha (sem coluna Empresa,
    # onde 'Categoria' guardava o centro de custo).
    if 'Empresa' not in df.columns and 'Categoria' in df.columns:
        df['Empresa'] = df['Categoria']
        df['Categoria'] = ''

    for col in ['Data', 'Hora', 'Tipo', 'Empresa', 'Categoria', 'Valor', 'Descrição']:
        if col not in df.columns:
            df[col] = ''

    df['Valor'] = df['Valor'].map(para_float).round(2)

    df['Data'] = pd.to_datetime(df['Data'], format='%d/%m/%Y', errors='coerce')
    df = df[df['Data'].notna()].copy()
    if df.empty:
        return pd.DataFrame(columns=colunas_vazias)

    df['Tipo'] = df['Tipo'].astype(str).str.strip().str.upper()
    df = df[df['Tipo'].isin(['RECEITA', 'CUSTO'])].copy()
    if df.empty:
        return pd.DataFrame(columns=colunas_vazias)

    df['Empresa'] = (df['Empresa'].astype(str).str.strip().str.upper()
                     .replace({'': 'SEM EMPRESA', 'NAN': 'SEM EMPRESA'}))
    df['Categoria'] = df['Categoria'].apply(normalizar_categoria)
    df['Descrição'] = df['Descrição'].astype(str).str.strip().replace('nan', '')

    df['Mes'] = df['Data'].dt.to_period('M')
    df['MesLabel'] = df['Mes'].apply(rotulo_mes)
    df['Dia'] = df['Data'].dt.day

    return df.sort_values('Data').reset_index(drop=True)


def fatiar_mes(df: pd.DataFrame, periodo) -> pd.DataFrame:
    if df.empty or periodo is None:
        return df.iloc[0:0]
    return df[df['Mes'] == pd.Period(periodo, freq='M')]


def mes_anterior(periodo):
    return pd.Period(periodo, freq='M') - 1


# -------------------------------------------------------------------- KPIs

def kpis(df: pd.DataFrame) -> dict:
    """Indicadores do recorte recebido."""
    vazio = dict(receita=0.0, custo=0.0, saldo=0.0, n=0, n_meses=0,
                 taxa_poupanca=0.0, ticket_custo=0.0, custo_medio_mes=0.0,
                 receita_media_mes=0.0, maior_gasto=None)
    if df.empty:
        return vazio

    receita = float(df.loc[df['Tipo'] == 'RECEITA', 'Valor'].sum())
    custo = float(df.loc[df['Tipo'] == 'CUSTO', 'Valor'].sum())
    custos = df[df['Tipo'] == 'CUSTO']
    n_meses = max(int(df['Mes'].nunique()), 1)

    maior = None
    if not custos.empty:
        linha = custos.loc[custos['Valor'].idxmax()]
        maior = dict(
            valor=float(linha['Valor']),
            categoria=linha['Categoria'],
            empresa=linha['Empresa'],
            descricao=linha['Descrição'] or '—',
            data=linha['Data'].strftime('%d/%m/%Y'),
        )

    return dict(
        receita=receita,
        custo=custo,
        saldo=receita - custo,
        n=int(len(df)),
        n_meses=n_meses,
        taxa_poupanca=((receita - custo) / receita * 100) if receita > 0 else 0.0,
        ticket_custo=float(custos['Valor'].mean()) if not custos.empty else 0.0,
        custo_medio_mes=custo / n_meses,
        receita_media_mes=receita / n_meses,
        maior_gasto=maior,
    )


def variacao(atual: float, anterior: float):
    """Variação percentual protegida contra divisão por zero."""
    if anterior == 0:
        return None
    return (atual - anterior) / abs(anterior) * 100


def sem_comparativo(valor) -> bool:
    """True quando não há base para comparar (None ou NaN vindo do pandas)."""
    return valor is None or (isinstance(valor, float) and pd.isna(valor))


# --------------------------------------------------------------- agregações

def serie_mensal(df: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por mês: Receita, Custo, Saldo, Taxa de poupança."""
    if df.empty:
        return pd.DataFrame(columns=['Mes', 'MesLabel', 'Receita', 'Custo', 'Saldo', 'Poupanca'])

    piv = (df.pivot_table(index='Mes', columns='Tipo', values='Valor',
                          aggfunc='sum', fill_value=0.0)
             .reindex(columns=['RECEITA', 'CUSTO'], fill_value=0.0)
             .rename(columns={'RECEITA': 'Receita', 'CUSTO': 'Custo'})
             .sort_index()
             .reset_index())

    piv['Saldo'] = piv['Receita'] - piv['Custo']
    piv['Poupanca'] = piv.apply(
        lambda r: (r['Saldo'] / r['Receita'] * 100) if r['Receita'] > 0 else 0.0, axis=1)
    piv['MesLabel'] = piv['Mes'].apply(rotulo_mes)
    return piv


def por_categoria(df: pd.DataFrame, tipo: str = 'CUSTO') -> pd.DataFrame:
    """Ranking com os números que interessam, não só a fatia da pizza."""
    colunas = ['Categoria', 'Total', 'N', 'Ticket', 'Pct', 'MediaMes']
    if df.empty:
        return pd.DataFrame(columns=colunas)

    base = df[df['Tipo'] == tipo]
    if base.empty:
        return pd.DataFrame(columns=colunas)

    n_meses = max(int(df['Mes'].nunique()), 1)
    agg = (base.groupby('Categoria')['Valor']
               .agg(Total='sum', N='count', Ticket='mean')
               .reset_index()
               .sort_values('Total', ascending=False))

    total = agg['Total'].sum()
    agg['Pct'] = (agg['Total'] / total * 100) if total else 0.0
    agg['MediaMes'] = agg['Total'] / n_meses
    return agg.reset_index(drop=True)


def dobrar_cauda(dados: pd.DataFrame, n: int = 8, coluna: str = 'Categoria') -> pd.DataFrame:
    """Mantém as N maiores e soma o resto em 'Outros' — nunca mais de N+1 faixas.

    Se sobrar uma única categoria na cauda, mostra ela pelo nome: agrupar uma
    linha só não esconde nada e ainda tira a informação.
    """
    if len(dados) <= n + 1:
        return dados.copy()

    topo = dados.head(n).copy()
    cauda = dados.iloc[n:]
    linha = {coluna: f'Outras {len(cauda)} categorias'}
    for col in dados.columns:
        if col == coluna:
            continue
        linha[col] = cauda[col].sum() if pd.api.types.is_numeric_dtype(dados[col]) else ''
    return pd.concat([topo, pd.DataFrame([linha])], ignore_index=True)


def comparar_categorias(df: pd.DataFrame, periodo_atual, periodo_base,
                        tipo: str = 'CUSTO') -> pd.DataFrame:
    """Δ R$ e Δ % de cada categoria entre dois meses."""
    colunas = ['Categoria', 'Atual', 'Anterior', 'Delta', 'DeltaPct']
    atual = por_categoria(fatiar_mes(df, periodo_atual), tipo)
    base = por_categoria(fatiar_mes(df, periodo_base), tipo)
    if atual.empty and base.empty:
        return pd.DataFrame(columns=colunas)

    comp = (atual[['Categoria', 'Total']].rename(columns={'Total': 'Atual'})
            .merge(base[['Categoria', 'Total']].rename(columns={'Total': 'Anterior'}),
                   on='Categoria', how='outer'))

    # Quando um dos lados vem vazio a coluna chega como object; converter
    # explicitamente evita o downcast silencioso que o pandas vai remover.
    for col in ('Atual', 'Anterior'):
        comp[col] = pd.to_numeric(comp[col], errors='coerce').fillna(0.0)

    comp['Delta'] = comp['Atual'] - comp['Anterior']
    comp['DeltaPct'] = pd.Series(
        [variacao(a, b) for a, b in zip(comp['Atual'], comp['Anterior'])],
        index=comp.index, dtype=object)
    return comp.sort_values('Delta', ascending=False).reset_index(drop=True)


def por_empresa(df: pd.DataFrame) -> pd.DataFrame:
    """DRE simplificada: receita, custo, resultado e margem por centro de custo."""
    colunas = ['Empresa', 'Receita', 'Custo', 'Saldo', 'Margem', 'N']
    if df.empty:
        return pd.DataFrame(columns=colunas)

    piv = (df.pivot_table(index='Empresa', columns='Tipo', values='Valor',
                          aggfunc='sum', fill_value=0.0)
             .reindex(columns=['RECEITA', 'CUSTO'], fill_value=0.0)
             .rename(columns={'RECEITA': 'Receita', 'CUSTO': 'Custo'})
             .reset_index())

    piv['Saldo'] = piv['Receita'] - piv['Custo']
    piv['Margem'] = piv.apply(
        lambda r: (r['Saldo'] / r['Receita'] * 100) if r['Receita'] > 0 else 0.0, axis=1)
    piv['N'] = piv['Empresa'].map(df.groupby('Empresa').size()).fillna(0).astype(int)

    ordem = {e: i for i, e in enumerate(EMPRESAS_ORDEM)}
    piv['_o'] = piv['Empresa'].map(lambda e: ordem.get(e, 99))
    return piv.sort_values(['_o', 'Empresa']).drop(columns='_o').reset_index(drop=True)


def matriz_categoria_empresa(df: pd.DataFrame, tipo: str = 'CUSTO') -> pd.DataFrame:
    """Cruza categoria x empresa — responde 'esse gasto é de qual frente?'."""
    if df.empty:
        return pd.DataFrame()
    base = df[df['Tipo'] == tipo]
    if base.empty:
        return pd.DataFrame()

    piv = base.pivot_table(index='Categoria', columns='Empresa', values='Valor',
                           aggfunc='sum', fill_value=0.0)
    piv['Total'] = piv.sum(axis=1)
    return piv.sort_values('Total', ascending=False)


def maiores_lancamentos(df: pd.DataFrame, n: int = 10, tipo: str = 'CUSTO') -> pd.DataFrame:
    if df.empty:
        return df
    base = df[df['Tipo'] == tipo]
    if base.empty:
        return base
    return base.nlargest(n, 'Valor')[['Data', 'Empresa', 'Categoria', 'Valor', 'Descrição']]


def ritmo_do_mes(df_mes: pd.DataFrame, periodo) -> dict:
    """Projeta o fechamento do mês pelo ritmo de gasto até agora."""
    p = pd.Period(periodo, freq='M')
    dias_no_mes = p.days_in_month
    hoje = date.today()
    no_mes_corrente = (hoje.year == p.year and hoje.month == p.month)
    dia_corrente = max(hoje.day if no_mes_corrente else dias_no_mes, 1)

    custo = float(df_mes.loc[df_mes['Tipo'] == 'CUSTO', 'Valor'].sum()) if not df_mes.empty else 0.0
    receita = float(df_mes.loc[df_mes['Tipo'] == 'RECEITA', 'Valor'].sum()) if not df_mes.empty else 0.0
    media_dia = custo / dia_corrente

    return dict(
        dia=dia_corrente,
        dias_no_mes=dias_no_mes,
        mes_fechado=not no_mes_corrente,
        media_dia=media_dia,
        projecao_custo=media_dia * dias_no_mes,
        projecao_saldo=receita - (media_dia * dias_no_mes),
    )


# ----------------------------------------------------------- qualidade dados

def problemas_de_dados(df: pd.DataFrame) -> list:
    """Avisos sobre lançamentos que sujam a análise."""
    avisos = []
    if df.empty:
        return avisos

    sem_cat = int((df['Categoria'] == SEM_CATEGORIA).sum())
    if sem_cat:
        avisos.append(f"{sem_cat} lançamento(s) sem categoria definida.")

    sem_desc = int((df['Descrição'].str.len() == 0).sum())
    if sem_desc:
        avisos.append(f"{sem_desc} lançamento(s) sem descrição.")

    receita_em_custo = df[(df['Tipo'] == 'CUSTO') &
                          (df['Categoria'].isin(['Receita', 'Salário']))]
    if len(receita_em_custo):
        avisos.append(
            f"{len(receita_em_custo)} lançamento(s) marcados como CUSTO mas "
            "categorizados como Receita/Salário — provável erro de digitação."
        )

    dup = int(df.duplicated(subset=['Data', 'Tipo', 'Empresa', 'Valor', 'Descrição'],
                            keep='first').sum())
    if dup:
        avisos.append(f"{dup} lançamento(s) possivelmente duplicados "
                      "(mesma data, valor e descrição).")

    return avisos
