"""
Dashboard Financeiro — EXTINPRAG · VSAFETY · Pessoal

Lê a planilha alimentada pelo bot do Telegram e entrega os números em quatro
recortes: visão geral, categorias, empresas e lançamentos. Todos os cálculos
vêm de `analise.py`, o mesmo módulo que o bot usa no /resumo.
"""

import json
import os
from datetime import datetime

import gspread
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from google.oauth2.service_account import Credentials

import analise as an
import tema

st.set_page_config(
    page_title="Dashboard Financeiro",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)
st.markdown(tema.CSS, unsafe_allow_html=True)

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]

PLOTLY_CFG = {'displayModeBar': False, 'responsive': True}


def texto_md(valor: str) -> str:
    """Escapa o cifrão para o Markdown do Streamlit.

    Dois `R$` na mesma string fazem o Streamlit interpretar o trecho entre eles
    como fórmula LaTeX — a legenda vira um borrão em itálico matemático.
    """
    return str(valor).replace('$', r'\$')


# --------------------------------------------------------------------- dados

@st.cache_data(ttl=300, show_spinner="Carregando lançamentos...")
def carregar():
    creds = Credentials.from_service_account_info(
        json.loads(os.environ['GOOGLE_CREDENTIALS']), scopes=SCOPES)
    ws = gspread.authorize(creds).open_by_key(os.environ['SHEET_ID']).worksheet('Lançamentos')
    registros = ws.get_all_records(value_render_option='UNFORMATTED_VALUE')
    return an.preparar(registros), datetime.now()


try:
    df_total, carregado_em = carregar()
except Exception as erro:
    st.error(f"Não consegui ler a planilha: {erro}")
    st.stop()

if df_total.empty:
    st.warning("Nenhum lançamento válido encontrado na planilha.")
    st.stop()

MESES = sorted(df_total['Mes'].unique())


# ------------------------------------------------------------------ período

def opcoes_periodo():
    opcoes = ['Mês atual']
    if len(MESES) >= 2:
        opcoes.append('Mês anterior')
    for n in (3, 6, 12):
        if len(MESES) > n:
            opcoes.append(f'Últimos {n} meses')
    anos = sorted({m.year for m in MESES}, reverse=True)
    opcoes += [f'Ano de {a}' for a in anos]
    opcoes.append('Todo o período')
    opcoes += [f'Mês: {an.rotulo_mes(m)}' for m in reversed(MESES)]
    return opcoes


def resolver_periodo(escolha):
    """Devolve (meses do recorte, meses da base de comparação, rótulo)."""
    if escolha == 'Mês atual':
        return MESES[-1:], MESES[-2:-1], an.rotulo_mes_extenso(MESES[-1])
    if escolha == 'Mês anterior':
        return MESES[-2:-1], MESES[-3:-2], an.rotulo_mes_extenso(MESES[-2])
    if escolha.startswith('Últimos '):
        n = int(escolha.split()[1])
        return MESES[-n:], MESES[-2 * n:-n], f'Últimos {n} meses'
    if escolha.startswith('Ano de '):
        ano = int(escolha.split()[-1])
        return ([m for m in MESES if m.year == ano],
                [m for m in MESES if m.year == ano - 1],
                f'Ano de {ano}')
    if escolha.startswith('Mês: '):
        alvo = next(m for m in MESES if an.rotulo_mes(m) == escolha[5:])
        i = MESES.index(alvo)
        return [alvo], MESES[i - 1:i] if i > 0 else [], an.rotulo_mes_extenso(alvo)
    return list(MESES), [], 'Todo o período'


# ------------------------------------------------------------------ cabeçalho

topo_esq, topo_dir = st.columns([3, 1])
with topo_esq:
    st.markdown(
        '<p class="fin-titulo">Dashboard Financeiro</p>'
        '<p class="fin-sub">EXTINPRAG · VSAFETY · Pessoal — dados da planilha alimentada pelo bot</p>',
        unsafe_allow_html=True)
with topo_dir:
    st.caption(f"Atualizado {carregado_em.strftime('%d/%m/%Y às %H:%M')}")
    if st.button("Recarregar dados", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.write("")

# Uma única barra de filtros, acima de tudo o que ela controla.
f1, f2, f3 = st.columns([1.4, 2, 1])
with f1:
    escolha_periodo = st.selectbox("Período", opcoes_periodo(), index=0)
with f2:
    empresas_disp = [e for e in an.EMPRESAS_ORDEM if e in set(df_total['Empresa'])]
    empresas_disp += sorted(set(df_total['Empresa']) - set(empresas_disp))
    empresas_sel = st.multiselect("Empresa", empresas_disp, default=empresas_disp,
                                  placeholder="Todas as empresas")
with f3:
    modo = st.selectbox("Analisar", ["Despesas", "Receitas"], index=0)

TIPO = 'CUSTO' if modo == 'Despesas' else 'RECEITA'

meses_sel, meses_base, rotulo_periodo = resolver_periodo(escolha_periodo)
empresas_ativas = empresas_sel or empresas_disp

df = df_total[df_total['Mes'].isin(meses_sel) & df_total['Empresa'].isin(empresas_ativas)]
df_base = df_total[df_total['Mes'].isin(meses_base) & df_total['Empresa'].isin(empresas_ativas)]
df_hist = df_total[df_total['Empresa'].isin(empresas_ativas)]

if df.empty:
    st.info(f"Sem lançamentos em {rotulo_periodo} para as empresas selecionadas.")
    st.stop()

k = an.kpis(df)
kb = an.kpis(df_base)
tem_base = not df_base.empty
rotulo_base = an.rotulo_mes_extenso(meses_base[-1]) if len(meses_base) == 1 else 'período anterior'


# ----------------------------------------------------------------- KPI cards

def bloco_delta(atual, anterior, inverter=False):
    """Texto + classe do delta. `inverter` = subir é ruim (despesas)."""
    if not tem_base:
        return '', 'delta-neutro'
    v = an.variacao(atual, anterior)
    if v is None:
        return f'sem base em {rotulo_base}', 'delta-neutro'
    subiu = v > 0
    bom = (not subiu) if inverter else subiu
    seta = '▲' if subiu else '▼'
    classe = 'delta-bom' if bom else 'delta-ruim'
    if abs(v) < 0.05:
        return f'= estável vs {rotulo_base}', 'delta-neutro'
    return f'{seta} {an.pct(abs(v))} vs {rotulo_base}', classe


mes_unico = len(meses_sel) == 1


def nota_referencia(valor_base: float, media_mes: float) -> str:
    """Num mês só, a média mensal repete o próprio valor — mostra a base."""
    if mes_unico and tem_base:
        return f"{rotulo_base}: {an.brl(valor_base)}"
    return f"Média de {an.brl(media_mes)}/mês"


c1, c2, c3, c4 = st.columns(4)
with c1:
    txt, cls = bloco_delta(k['receita'], kb['receita'])
    st.markdown(tema.card("Receitas", an.brl(k['receita']),
                          nota_referencia(kb['receita'], k['receita_media_mes']), txt, cls),
                unsafe_allow_html=True)
with c2:
    txt, cls = bloco_delta(k['custo'], kb['custo'], inverter=True)
    st.markdown(tema.card("Despesas", an.brl(k['custo']),
                          nota_referencia(kb['custo'], k['custo_medio_mes']), txt, cls),
                unsafe_allow_html=True)
with c3:
    txt, cls = bloco_delta(k['saldo'], kb['saldo'])
    sinal = "Sobrou" if k['saldo'] >= 0 else "Faltou"
    st.markdown(tema.card("Resultado", an.brl(k['saldo']),
                          f"{sinal} no período · {k['n']} lançamentos", txt, cls),
                unsafe_allow_html=True)
with c4:
    txt, cls = bloco_delta(k['taxa_poupanca'], kb['taxa_poupanca'])
    taxa = k['taxa_poupanca']
    if taxa >= 0:
        nota_poupanca = f"De cada R$ 100 recebidos, sobram R$ {taxa:.0f}"
    else:
        nota_poupanca = f"Gastou R$ {100 - taxa:.0f} para cada R$ 100 que entraram"
    st.markdown(tema.card("Taxa de poupança", an.pct(taxa), nota_poupanca, txt, cls),
                unsafe_allow_html=True)

st.write("")
st.caption(f"Recorte: **{rotulo_periodo}** · {len(empresas_ativas)} de "
           f"{len(empresas_disp)} empresa(s) · comparado com {rotulo_base}")


# -------------------------------------------------------------------- gráficos

def barras_receita_custo(serie: pd.DataFrame):
    """Receita x despesa mês a mês. Duas séries, um eixo, rótulo só no último mês."""
    ultimo = len(serie) - 1
    fig = go.Figure()
    for nome, coluna, cor in (('Receita', 'Receita', tema.RECEITA),
                              ('Despesa', 'Custo', tema.CUSTO)):
        rotulos = ['' if i != ultimo else an.brl_compacto(v)
                   for i, v in enumerate(serie[coluna])]
        fig.add_bar(
            name=nome, x=serie['MesLabel'], y=serie[coluna], marker_color=cor,
            text=rotulos, textposition='outside',
            textfont=dict(color=tema.TEXTO_2, size=12),
            hovertemplate=f'<b>{nome}</b> em %{{x}}<br>%{{customdata}}<extra></extra>',
            customdata=[an.brl(v) for v in serie[coluna]],
        )
    tema.aplicar(fig, altura=340, barmode='group', bargap=0.32, bargroupgap=0.06,
                 xaxis={**tema.EIXO_X, 'type': 'category'},
                 yaxis={**tema.EIXO_Y, 'tickprefix': 'R$ ', 'tickformat': ',.0f'},
                 hovermode='x unified')
    fig.update_yaxes(rangemode='tozero')
    return fig


def barras_saldo(serie: pd.DataFrame):
    """Resultado mensal — divergente pelo sinal, zero como linha neutra."""
    cores = [tema.RECEITA if v >= 0 else tema.CUSTO for v in serie['Saldo']]
    fig = go.Figure(go.Bar(
        x=serie['MesLabel'], y=serie['Saldo'], marker_color=cores,
        text=[an.brl_compacto(v) for v in serie['Saldo']],
        textposition='outside', textfont=dict(color=tema.TEXTO_2, size=12),
        hovertemplate='<b>%{x}</b><br>Resultado: %{customdata}<extra></extra>',
        customdata=[an.brl(v) for v in serie['Saldo']],
    ))
    tema.aplicar(fig, altura=300, bargap=0.45, showlegend=False,
                 xaxis={**tema.EIXO_X, 'type': 'category'},
                 yaxis={**tema.EIXO_Y, 'tickprefix': 'R$ ', 'tickformat': ',.0f',
                        'zeroline': True, 'zerolinecolor': tema.EIXO, 'zerolinewidth': 1})
    return fig


def barras_ranking(dados: pd.DataFrame, cor: str, altura_min=320):
    """Ranking horizontal — uma série, uma cor, valor direto na ponta da barra."""
    d = dados.sort_values('Total')
    fig = go.Figure(go.Bar(
        x=d['Total'], y=d['Categoria'], orientation='h', marker_color=cor,
        text=[f"{an.brl(v)}  ·  {an.pct(p)}" for v, p in zip(d['Total'], d['Pct'])],
        textposition='outside', textfont=dict(color=tema.TEXTO_2, size=12),
        cliponaxis=False,
        customdata=list(zip([an.brl(v) for v in d['Total']], d['N'],
                            [an.brl(v) for v in d['Ticket']])),
        hovertemplate=('<b>%{y}</b><br>Total: %{customdata[0]}<br>'
                       'Lançamentos: %{customdata[1]}<br>'
                       'Ticket médio: %{customdata[2]}<extra></extra>'),
    ))
    limite = float(d['Total'].max()) * 1.32 if len(d) else 1
    tema.aplicar(fig, altura=max(altura_min, 46 * len(d) + 60), bargap=0.38,
                 showlegend=False, margin=dict(l=8, r=8, t=8, b=8),
                 xaxis={**tema.EIXO_X, 'visible': False, 'range': [0, limite]},
                 yaxis={**tema.EIXO_Y, 'showgrid': False,
                        'tickfont': dict(color=tema.TEXTO_2, size=13)})
    return fig


def barras_variacao(comp: pd.DataFrame, n=10):
    """Δ R$ por categoria entre dois meses — quem puxou o total para cima/baixo."""
    relevantes = comp[comp['Delta'].abs() > 0.005]
    if relevantes.empty:
        return None
    d = pd.concat([relevantes.head(n), relevantes.tail(n)]).drop_duplicates('Categoria')
    d = d.sort_values('Delta')
    cores = [tema.CUSTO if v > 0 else tema.RECEITA for v in d['Delta']]
    rotulo_pct = ['novo' if an.sem_comparativo(p) else an.pct(p, 0) for p in d['DeltaPct']]
    fig = go.Figure(go.Bar(
        x=d['Delta'], y=d['Categoria'], orientation='h', marker_color=cores,
        customdata=list(zip([an.brl(v) for v in d['Atual']],
                            [an.brl(v) for v in d['Anterior']],
                            [an.brl(v) for v in d['Delta']], rotulo_pct)),
        hovertemplate=('<b>%{y}</b><br>Neste período: %{customdata[0]}<br>'
                       'No anterior: %{customdata[1]}<br>'
                       'Diferença: %{customdata[2]} (%{customdata[3]})<extra></extra>'),
    ))
    tema.aplicar(fig, altura=max(300, 40 * len(d) + 70), bargap=0.4, showlegend=False,
                 xaxis={**tema.EIXO_X, 'showgrid': True, 'gridcolor': tema.GRID,
                        'tickprefix': 'R$ ', 'tickformat': ',.0f',
                        'zeroline': True, 'zerolinecolor': tema.MUTED, 'zerolinewidth': 1},
                 yaxis={**tema.EIXO_Y, 'showgrid': False,
                        'tickfont': dict(color=tema.TEXTO_2, size=13)})
    return fig


aba_geral, aba_cat, aba_emp, aba_lanc = st.tabs(
    ["  Visão geral  ", "  Categorias  ", "  Empresas  ", "  Lançamentos  "])


# ------------------------------------------------------------- aba: visão geral

with aba_geral:
    serie = an.serie_mensal(df_hist).tail(13)

    st.markdown(tema.titulo_secao(
        "Receita x despesa, mês a mês",
        "Barras lado a lado na mesma escala. Rótulo no mês mais recente; "
        "passe o mouse para ver os demais."), unsafe_allow_html=True)
    st.plotly_chart(barras_receita_custo(serie), use_container_width=True, config=PLOTLY_CFG)

    st.markdown(tema.titulo_secao(
        "Resultado mensal",
        "Receita menos despesa. Azul = sobrou, vermelho = faltou."),
        unsafe_allow_html=True)
    st.plotly_chart(barras_saldo(serie), use_container_width=True, config=PLOTLY_CFG)

    st.markdown("---")
    st.markdown(tema.titulo_secao("Leituras do período"), unsafe_allow_html=True)

    ritmo = an.ritmo_do_mes(df, meses_sel[-1]) if mes_unico else None
    comp_cat = (an.comparar_categorias(df_hist, meses_sel[-1], meses_base[-1], TIPO)
                if mes_unico and len(meses_base) == 1 else pd.DataFrame())

    i1, i2, i3, i4 = st.columns(4)

    with i1:
        if ritmo and not ritmo['mes_fechado']:
            st.markdown(tema.card(
                "Ritmo de gasto",
                f"{an.brl(ritmo['media_dia'])}/dia",
                f"No dia {ritmo['dia']} de {ritmo['dias_no_mes']} · projeção de "
                f"{an.brl(ritmo['projecao_custo'])} até o fim do mês"),
                unsafe_allow_html=True)
        else:
            st.markdown(tema.card(
                "Despesa média mensal", an.brl(k['custo_medio_mes']),
                f"Sobre {k['n_meses']} mês(es) do recorte"), unsafe_allow_html=True)

    with i2:
        mg = k['maior_gasto']
        if mg:
            st.markdown(tema.card(
                "Maior despesa", an.brl(mg['valor']),
                f"{mg['categoria']} · {mg['empresa']} · {mg['data']}<br>{mg['descricao'][:60]}"),
                unsafe_allow_html=True)
        else:
            st.markdown(tema.card("Maior despesa", "—", "Sem despesas no recorte"),
                        unsafe_allow_html=True)

    with i3:
        if not comp_cat.empty and comp_cat.iloc[0]['Delta'] > 0:
            linha = comp_cat.iloc[0]
            pc = ('nova categoria' if an.sem_comparativo(linha['DeltaPct'])
                  else f"+{an.pct(linha['DeltaPct'], 0)}")
            st.markdown(tema.card(
                "Maior alta", f"+{an.brl(linha['Delta'])}",
                f"{linha['Categoria']} · {pc} vs {rotulo_base}",
                delta_txt='▲ gastou mais', delta_classe='delta-ruim'), unsafe_allow_html=True)
        else:
            st.markdown(tema.card("Ticket médio das despesas", an.brl(k['ticket_custo']),
                                  "Valor médio por lançamento"), unsafe_allow_html=True)

    with i4:
        if not comp_cat.empty and comp_cat.iloc[-1]['Delta'] < 0:
            linha = comp_cat.iloc[-1]
            pc = ('' if an.sem_comparativo(linha['DeltaPct'])
                  else f" · {an.pct(linha['DeltaPct'], 0)}")
            st.markdown(tema.card(
                "Maior economia", an.brl(abs(linha['Delta'])),
                f"{linha['Categoria']}{pc} vs {rotulo_base}",
                delta_txt='▼ gastou menos', delta_classe='delta-bom'), unsafe_allow_html=True)
        else:
            st.markdown(tema.card("Lançamentos no período", str(k['n']),
                                  f"{k['n'] / max(k['n_meses'], 1):.0f} por mês em média"),
                        unsafe_allow_html=True)

    avisos = an.problemas_de_dados(df)
    if avisos:
        st.markdown("---")
        st.markdown(tema.titulo_secao(
            "Qualidade dos dados",
            "Estes lançamentos distorcem a análise — vale corrigir na planilha."),
            unsafe_allow_html=True)
        for aviso in avisos:
            st.markdown(f'<div class="fin-nota-box">{aviso}</div>', unsafe_allow_html=True)


# -------------------------------------------------------------- aba: categorias

with aba_cat:
    cats = an.por_categoria(df, TIPO)

    if cats.empty:
        st.info(f"Sem {modo.lower()} no recorte selecionado.")
    else:
        cor_serie = tema.CUSTO if TIPO == 'CUSTO' else tema.RECEITA
        total_tipo = float(cats['Total'].sum())

        st.markdown(tema.titulo_secao(
            f"{modo} por categoria — {rotulo_periodo}",
            f"Total de {an.brl(total_tipo)} em {int(cats['N'].sum())} lançamentos, "
            f"distribuídos em {len(cats)} categorias."), unsafe_allow_html=True)

        col_graf, col_tab = st.columns([1, 1.2])

        with col_graf:
            st.plotly_chart(barras_ranking(an.dobrar_cauda(cats, 10), cor_serie),
                            use_container_width=True, config=PLOTLY_CFG)

        with col_tab:
            tabela = cats.copy()
            tabela['Valor'] = tabela['Total'].apply(an.brl)
            tabela['Ticket médio'] = tabela['Ticket'].apply(an.brl)
            colunas_tab = ['Categoria', 'Valor', 'Pct', 'N', 'Ticket médio']
            if not mes_unico:
                tabela['Média/mês'] = tabela['MediaMes'].apply(an.brl)
                colunas_tab.append('Média/mês')
            st.dataframe(
                tabela[colunas_tab],
                use_container_width=True, hide_index=True,
                height=max(320, 36 * len(tabela) + 45),
                column_config={
                    'Categoria': st.column_config.TextColumn('Categoria', width='medium'),
                    'Valor': st.column_config.TextColumn('Total', width='medium'),
                    'Pct': st.column_config.ProgressColumn(
                        '% do total', format='%.0f%%', min_value=0.0,
                        max_value=float(cats['Pct'].max())),
                    'N': st.column_config.NumberColumn('Lanç.', width='small'),
                    'Ticket médio': st.column_config.TextColumn('Ticket médio'),
                    'Média/mês': st.column_config.TextColumn('Média/mês'),
                })

        st.markdown("---")

        if mes_unico and len(meses_base) == 1:
            comp = an.comparar_categorias(df_hist, meses_sel[-1], meses_base[-1], TIPO)
            fig_var = barras_variacao(comp)
            st.markdown(tema.titulo_secao(
                f"O que mudou vs {rotulo_base}",
                "Diferença em reais por categoria. Vermelho à direita = gastou mais; "
                "azul à esquerda = gastou menos."), unsafe_allow_html=True)
            if fig_var is None:
                st.info("Nenhuma variação relevante entre os dois meses.")
            else:
                cv1, cv2 = st.columns([1.05, 1])
                with cv1:
                    st.plotly_chart(fig_var, use_container_width=True, config=PLOTLY_CFG)
                with cv2:
                    tab_c = comp.copy()
                    tab_c['Neste mês'] = tab_c['Atual'].apply(an.brl)
                    tab_c['Mês anterior'] = tab_c['Anterior'].apply(an.brl)
                    tab_c['Diferença'] = tab_c['Delta'].apply(
                        lambda v: ('+' if v > 0 else '') + an.brl(v))
                    tab_c['Variação'] = tab_c['DeltaPct'].apply(
                        lambda p: 'novo' if an.sem_comparativo(p) else ('+' if p > 0 else '') + an.pct(p, 0))
                    st.dataframe(
                        tab_c[['Categoria', 'Neste mês', 'Mês anterior', 'Diferença', 'Variação']],
                        use_container_width=True, hide_index=True,
                        height=max(300, 36 * len(tab_c) + 45))
        else:
            st.markdown(tema.titulo_secao(
                "Comparativo mês a mês",
                "Selecione um mês específico no filtro de período para ver a variação "
                "categoria por categoria."), unsafe_allow_html=True)

        st.markdown("---")
        matriz = an.matriz_categoria_empresa(df, TIPO)
        if not matriz.empty and matriz.shape[1] > 2:
            st.markdown(tema.titulo_secao(
                f"{modo}: categoria x empresa",
                "Responde de qual frente sai cada gasto — o que a pizza única escondia."),
                unsafe_allow_html=True)
            exib = matriz.reset_index()
            for col in exib.columns[1:]:
                exib[col] = exib[col].apply(lambda v: an.brl(v) if v else '—')
            st.dataframe(exib, use_container_width=True, hide_index=True,
                         height=max(280, 36 * len(exib) + 45))


# ---------------------------------------------------------------- aba: empresas

with aba_emp:
    emp = an.por_empresa(df)

    st.markdown(tema.titulo_secao(
        f"Resultado por empresa — {rotulo_periodo}",
        "Cada centro de custo com receita, despesa, resultado e margem."),
        unsafe_allow_html=True)

    ce1, ce2 = st.columns([1.1, 1])

    with ce1:
        fig = go.Figure()
        for nome, coluna, cor in (('Receita', 'Receita', tema.RECEITA),
                                  ('Despesa', 'Custo', tema.CUSTO)):
            fig.add_bar(name=nome, x=emp['Empresa'], y=emp[coluna], marker_color=cor,
                        text=[an.brl_compacto(v) for v in emp[coluna]],
                        textposition='outside', textfont=dict(color=tema.TEXTO_2, size=12),
                        customdata=[an.brl(v) for v in emp[coluna]],
                        hovertemplate=f'<b>{nome}</b> — %{{x}}<br>%{{customdata}}<extra></extra>')
        tema.aplicar(fig, altura=360, barmode='group', bargap=0.42, bargroupgap=0.06,
                     xaxis={**tema.EIXO_X, 'type': 'category',
                            'tickfont': dict(color=tema.TEXTO_2, size=13)},
                     yaxis={**tema.EIXO_Y, 'tickprefix': 'R$ ', 'tickformat': ',.0f'},
                     hovermode='x unified')
        fig.update_yaxes(rangemode='tozero')
        st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CFG)

    with ce2:
        tab_e = emp.copy()
        tab_e['Receita R$'] = tab_e['Receita'].apply(an.brl)
        tab_e['Despesa R$'] = tab_e['Custo'].apply(an.brl)
        tab_e['Resultado'] = tab_e['Saldo'].apply(an.brl)
        tab_e['Margem %'] = tab_e['Margem'].apply(lambda v: an.pct(v))
        st.dataframe(
            tab_e[['Empresa', 'Receita R$', 'Despesa R$', 'Resultado', 'Margem %', 'N']],
            use_container_width=True, hide_index=True, height=36 * len(tab_e) + 45,
            column_config={'N': st.column_config.NumberColumn('Lanç.', width='small')})

        total_r = float(emp['Receita'].sum())
        if total_r > 0:
            linhas = [f"**{r['Empresa']}** responde por "
                      f"{an.pct(r['Receita'] / total_r * 100, 0)} da receita"
                      for _, r in emp.sort_values('Receita', ascending=False).head(3).iterrows()
                      if r['Receita'] > 0]
            if linhas:
                st.caption(" · ".join(linhas))

    st.markdown("---")
    st.markdown(tema.titulo_secao(
        "Resultado mensal por empresa",
        "Mesma escala em todos os painéis para permitir a comparação direta."),
        unsafe_allow_html=True)

    hist_emp = (df_hist[df_hist['Mes'].isin(sorted(df_hist['Mes'].unique())[-13:])]
                .groupby(['Empresa', 'Mes', 'Tipo'])['Valor'].sum().unstack('Tipo')
                .reindex(columns=['RECEITA', 'CUSTO'], fill_value=0.0).fillna(0.0))
    hist_emp['Saldo'] = hist_emp['RECEITA'] - hist_emp['CUSTO']
    hist_emp = hist_emp.reset_index()
    hist_emp['MesLabel'] = hist_emp['Mes'].apply(an.rotulo_mes)

    if hist_emp.empty:
        st.info("Sem histórico suficiente.")
    else:
        limite = float(hist_emp['Saldo'].abs().max()) * 1.25 or 1.0
        ordem_meses = [an.rotulo_mes(m) for m in sorted(df_hist['Mes'].unique())[-13:]]
        colunas = st.columns(len(empresas_ativas))
        for coluna, nome_emp in zip(colunas, empresas_ativas):
            sub = hist_emp[hist_emp['Empresa'] == nome_emp]
            with coluna:
                st.markdown(f'<p class="fin-secao">{nome_emp}</p>', unsafe_allow_html=True)
                if sub.empty:
                    st.caption("Sem lançamentos.")
                    continue
                cores = [tema.RECEITA if v >= 0 else tema.CUSTO for v in sub['Saldo']]
                fmini = go.Figure(go.Bar(
                    x=sub['MesLabel'], y=sub['Saldo'], marker_color=cores,
                    customdata=[an.brl(v) for v in sub['Saldo']],
                    hovertemplate='<b>%{x}</b><br>Resultado: %{customdata}<extra></extra>'))
                tema.aplicar(fmini, altura=230, bargap=0.4, showlegend=False,
                             xaxis={**tema.EIXO_X, 'type': 'category',
                                    'categoryorder': 'array', 'categoryarray': ordem_meses,
                                    'tickfont': dict(color=tema.MUTED, size=11)},
                             yaxis={**tema.EIXO_Y, 'range': [-limite, limite],
                                    'tickprefix': 'R$ ', 'tickformat': ',.0f',
                                    'zeroline': True, 'zerolinecolor': tema.EIXO})
                st.plotly_chart(fmini, use_container_width=True, config=PLOTLY_CFG)


# ------------------------------------------------------------- aba: lançamentos

with aba_lanc:
    st.markdown(tema.titulo_secao(
        f"Lançamentos — {rotulo_periodo}",
        f"{len(df)} registros no recorte. Clique no cabeçalho para ordenar."),
        unsafe_allow_html=True)

    b1, b2 = st.columns([2, 1])
    with b1:
        busca = st.text_input("Buscar na descrição ou categoria", placeholder="ex.: extintor, uber, fatura")
    with b2:
        tipo_sel = st.selectbox("Tipo", ["Todos", "Despesas", "Receitas"])

    vis = df.copy()
    if tipo_sel != "Todos":
        vis = vis[vis['Tipo'] == ('CUSTO' if tipo_sel == 'Despesas' else 'RECEITA')]
    if busca:
        alvo = busca.strip().lower()
        vis = vis[vis['Descrição'].str.lower().str.contains(alvo, na=False) |
                  vis['Categoria'].str.lower().str.contains(alvo, na=False)]

    if vis.empty:
        st.info("Nenhum lançamento com esse filtro.")
    else:
        soma_r = float(vis.loc[vis['Tipo'] == 'RECEITA', 'Valor'].sum())
        soma_c = float(vis.loc[vis['Tipo'] == 'CUSTO', 'Valor'].sum())
        st.caption(texto_md(
            f"{len(vis)} lançamento(s) · receitas {an.brl(soma_r)} · "
            f"despesas {an.brl(soma_c)} · resultado {an.brl(soma_r - soma_c)}"))

        exib = vis.sort_values('Data', ascending=False).copy()
        csv = (exib[['Data', 'Tipo', 'Empresa', 'Categoria', 'Valor', 'Descrição']]
               .assign(Data=exib['Data'].dt.strftime('%d/%m/%Y'))
               .to_csv(index=False, sep=';', decimal=',').encode('utf-8-sig'))

        exib['Data'] = exib['Data'].dt.strftime('%d/%m/%Y')
        exib['Tipo'] = exib['Tipo'].map({'RECEITA': 'Receita', 'CUSTO': 'Despesa'})
        exib['Valor'] = exib['Valor'].apply(an.brl)
        st.dataframe(
            exib[['Data', 'Tipo', 'Empresa', 'Categoria', 'Valor', 'Descrição']],
            use_container_width=True, hide_index=True, height=560,
            column_config={
                'Data': st.column_config.TextColumn('Data', width='small'),
                'Tipo': st.column_config.TextColumn('Tipo', width='small'),
                'Valor': st.column_config.TextColumn('Valor', width='small'),
                'Descrição': st.column_config.TextColumn('Descrição', width='large'),
            })

        st.download_button(
            "Baixar este recorte em CSV", csv,
            file_name=f"financeiro_{rotulo_periodo.lower().replace(' ', '_')}.csv",
            mime="text/csv")

    st.markdown("---")
    st.markdown(tema.titulo_secao("Maiores despesas do período"), unsafe_allow_html=True)
    maiores = an.maiores_lancamentos(df, 10, 'CUSTO')
    if maiores.empty:
        st.caption("Sem despesas no recorte.")
    else:
        m = maiores.copy()
        m['Data'] = m['Data'].dt.strftime('%d/%m/%Y')
        m['Valor'] = m['Valor'].apply(an.brl)
        st.dataframe(m, use_container_width=True, hide_index=True,
                     height=36 * len(m) + 45)
