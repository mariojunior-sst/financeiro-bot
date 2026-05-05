import json
import os

import gspread
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from google.oauth2.service_account import Credentials

st.set_page_config(
    page_title="Dashboard Financeiro",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background-color: #1C1C2E; }
[data-testid="stSidebar"] { background-color: #16213E; }
[data-testid="stHeader"] { background-color: #1C1C2E; }
h1, h2, h3, h4 { color: #F5A623; }
[data-testid="stMetricValue"] { color: #F5A623; font-size: 2rem !important; }
[data-testid="stMetricLabel"] { color: #AAAAAA; }
div[data-testid="metric-container"] {
    background: #16213E;
    border: 1px solid #F5A623;
    border-radius: 12px;
    padding: 16px;
}
[data-testid="stDataFrame"] { background-color: #16213E; }
</style>
""", unsafe_allow_html=True)

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]

CORES = {
    'receita': '#2ECC71',
    'custo': '#E74C3C',
    'destaque': '#F5A623',
    'fundo': 'rgba(0,0,0,0)',
    'texto': '#FFFFFF',
}

LAYOUT_BASE = dict(
    paper_bgcolor=CORES['fundo'],
    plot_bgcolor=CORES['fundo'],
    font=dict(color=CORES['texto']),
    legend=dict(font=dict(color=CORES['texto'])),
)


def brl(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')


@st.cache_data(ttl=300)
def carregar_dados():
    creds_dict = json.loads(os.environ['GOOGLE_CREDENTIALS'])
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    ws = client.open_by_key(os.environ['SHEET_ID']).worksheet('Lançamentos')
    registros = ws.get_all_records(value_render_option='UNFORMATTED_VALUE')
    if not registros:
        return pd.DataFrame()

    df = pd.DataFrame(registros)
    df['Valor'] = pd.to_numeric(df['Valor'], errors='coerce').fillna(0)
    df['Data'] = pd.to_datetime(df['Data'], format='%d/%m/%Y', errors='coerce')

    # Compatibilidade com formato antigo (sem coluna Empresa)
    if 'Empresa' not in df.columns and 'Categoria' in df.columns:
        df['Empresa'] = df['Categoria']

    df['Tipo'] = df['Tipo'].str.upper()
    df['Mes'] = df['Data'].dt.to_period('M')
    return df


# --- Carregar dados ---
try:
    df = carregar_dados()
except Exception as e:
    st.error(f"Erro ao carregar dados da planilha: {e}")
    st.stop()

if df.empty:
    st.warning("Nenhum lançamento encontrado na planilha.")
    st.stop()

# --- Sidebar ---
st.sidebar.title("Dashboard Financeiro")
st.sidebar.markdown("---")

meses = sorted(df['Mes'].dropna().unique(), reverse=True)
opcoes_mes = ["Todos os meses"] + [str(m) for m in meses]
mes_sel = st.sidebar.selectbox("Mês", opcoes_mes)

empresas = sorted(df['Empresa'].dropna().unique().tolist()) if 'Empresa' in df.columns else []
empresa_sel = st.sidebar.selectbox("Empresa", ["Todas"] + empresas)

st.sidebar.markdown("---")
if st.sidebar.button("🔄 Atualizar dados"):
    st.cache_data.clear()
    st.rerun()

# --- Filtros ---
df_f = df.copy()
if mes_sel != "Todos os meses":
    df_f = df_f[df_f['Mes'].astype(str) == mes_sel]
if empresa_sel != "Todas":
    df_f = df_f[df_f['Empresa'] == empresa_sel]

receitas = df_f[df_f['Tipo'] == 'RECEITA']['Valor'].sum()
custos = df_f[df_f['Tipo'] == 'CUSTO']['Valor'].sum()
saldo = receitas - custos
n_lancamentos = len(df_f)

# --- Cabeçalho ---
st.title("💰 Dashboard Financeiro Pessoal")
st.markdown("---")

# --- Scorecards ---
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("📈 Total de Receitas", brl(receitas))
with c2:
    st.metric("📉 Total de Despesas", brl(custos))
with c3:
    cor_saldo = "#2ECC71" if saldo >= 0 else "#E74C3C"
    st.metric("💼 Saldo do Período", brl(saldo))
with c4:
    st.metric("🧾 Lançamentos", str(n_lancamentos))

st.markdown("---")

# --- Gráficos linha 1 ---
col_pizza, col_barras = st.columns(2)

with col_pizza:
    st.subheader("🗂 Gastos por Categoria")
    df_custo = df_f[df_f['Tipo'] == 'CUSTO']
    if not df_custo.empty and 'Categoria' in df_custo.columns:
        df_custo = df_custo[df_custo['Categoria'].astype(str).str.strip().isin(['', '0']) == False]
        df_cat = df_custo.groupby('Categoria')['Valor'].sum().reset_index()
        df_cat = df_cat[df_cat['Valor'] > 0]
        fig = px.pie(
            df_cat, values='Valor', names='Categoria', hole=0.45,
            color_discrete_sequence=['#F5A623', '#E74C3C', '#3498DB',
                                     '#2ECC71', '#9B59B6', '#1ABC9C',
                                     '#E67E22', '#34495E', '#F39C12', '#D35400'],
        )
        fig.update_traces(textposition='inside', textinfo='percent+label')
        fig.update_layout(**LAYOUT_BASE)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sem dados de custos para o período.")

with col_barras:
    st.subheader("🏢 Receita vs Custo por Empresa")
    if 'Empresa' in df_f.columns:
        df_emp = df_f.groupby(['Empresa', 'Tipo'])['Valor'].sum().reset_index()
        fig = px.bar(
            df_emp, x='Empresa', y='Valor', color='Tipo', barmode='group',
            color_discrete_map={'RECEITA': CORES['receita'], 'CUSTO': CORES['custo']},
        )
        fig.update_layout(**LAYOUT_BASE,
                          xaxis=dict(color=CORES['texto']),
                          yaxis=dict(color=CORES['texto']))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sem dados de empresa disponíveis.")

# --- Evolução mensal ---
st.subheader("📅 Receitas x Gastos — Evolução Mensal")
df_mensal = df.groupby(['Mes', 'Tipo'])['Valor'].sum().reset_index()
df_mensal['Mes'] = df_mensal['Mes'].astype(str)

if not df_mensal.empty:
    fig = px.line(
        df_mensal, x='Mes', y='Valor', color='Tipo', markers=True,
        color_discrete_map={'RECEITA': CORES['receita'], 'CUSTO': CORES['custo']},
    )
    fig.update_traces(line=dict(width=3), marker=dict(size=8))
    fig.update_layout(**LAYOUT_BASE,
                      xaxis=dict(color=CORES['texto'], title='Mês'),
                      yaxis=dict(color=CORES['texto'], title='R$'))
    st.plotly_chart(fig, use_container_width=True)

# --- Últimos lançamentos ---
st.markdown("---")
st.subheader("🕐 Últimos Lançamentos")
colunas = ['Data', 'Empresa', 'Tipo', 'Categoria', 'Valor', 'Descrição']
colunas_existentes = [c for c in colunas if c in df.columns]
df_rec = df.sort_values('Data', ascending=False).head(15)[colunas_existentes].copy()
df_rec['Data'] = df_rec['Data'].dt.strftime('%d/%m/%Y')
df_rec['Valor'] = df_rec['Valor'].apply(brl)
st.dataframe(df_rec, use_container_width=True, hide_index=True)
