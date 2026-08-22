"""
Paleta e chrome dos gráficos.

As cores de série não são escolha estética: o par receita/custo foi validado
contra a superfície escura (#12263F) para separação sob daltonismo — verde x
vermelho reprova (ΔE 4,1 em deuteranopia), azul x vermelho passa (ΔE 19,2).
Verde e vermelho seguem existindo, mas só como *status* (setas de variação),
sempre acompanhados de sinal e rótulo, nunca como cor de série sozinha.
"""

# Superfícies
PLANO = '#0A1728'        # fundo da página
SUPERFICIE = '#12263F'   # fundo dos cartões e da área de plotagem
SUPERFICIE_ALT = '#0F1E33'
BORDA = 'rgba(255,255,255,0.10)'

# Tinta
TEXTO = '#FFFFFF'
TEXTO_2 = '#B7C4D4'
MUTED = '#93A4B8'
GRID = '#1E3247'
EIXO = '#2A415C'

# Séries (validadas — ver docstring)
RECEITA = '#3987e5'
CUSTO = '#e66767'
NEUTRO = '#5A6E85'

# Status (só com ícone/sinal + rótulo ao lado)
BOM = '#0ca30c'
ATENCAO = '#fab219'
RUIM = '#d03b3b'

FONTE = 'system-ui, -apple-system, "Segoe UI", sans-serif'

LAYOUT_BASE = dict(
    paper_bgcolor='rgba(0,0,0,0)',
    plot_bgcolor='rgba(0,0,0,0)',
    separators=',.',  # padrão brasileiro: R$ 100.000,00 (e não 100,000.00)
    font=dict(color=TEXTO_2, family=FONTE, size=13),
    margin=dict(l=8, r=8, t=8, b=8),
    hoverlabel=dict(bgcolor=SUPERFICIE_ALT, bordercolor=BORDA,
                    font=dict(color=TEXTO, family=FONTE, size=13)),
    legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0,
                font=dict(color=TEXTO_2, size=12), bgcolor='rgba(0,0,0,0)'),
)

EIXO_X = dict(showgrid=False, zeroline=False, linecolor=EIXO, linewidth=1,
              tickfont=dict(color=MUTED, size=12), title=None, ticks='outside',
              ticklen=4, tickcolor=EIXO)

EIXO_Y = dict(showgrid=True, gridcolor=GRID, gridwidth=1, zeroline=False,
              linecolor='rgba(0,0,0,0)', tickfont=dict(color=MUTED, size=12),
              title=None)


def aplicar(fig, altura=320, **extra):
    """Aplica o chrome padrão a uma figura Plotly.

    `extra` sobrescreve o padrão em vez de colidir com ele — assim um gráfico
    pode ajustar `margin`, `legend` etc. sem duplicar o argumento.
    """
    layout = dict(LAYOUT_BASE)
    layout.update(extra)
    layout['height'] = altura
    fig.update_layout(**layout)
    return fig


CSS = f"""
<style>
  [data-testid="stAppViewContainer"] {{ background: {PLANO}; }}
  [data-testid="stHeader"] {{ background: rgba(0,0,0,0); }}
  [data-testid="stSidebar"] {{ background: {SUPERFICIE_ALT}; }}
  .block-container {{ padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1500px; }}

  html, body, [class*="css"] {{ font-family: {FONTE}; }}

  h1, h2, h3, h4, h5 {{ color: {TEXTO} !important; letter-spacing: -0.01em; }}

  .fin-titulo {{ font-size: 1.6rem; font-weight: 650; color: {TEXTO}; margin: 0; }}
  .fin-sub {{ font-size: 0.9rem; color: {MUTED}; margin: 4px 0 0 0; }}

  .fin-secao {{ font-size: 1.0rem; font-weight: 620; color: {TEXTO};
                margin: 4px 0 2px 0; }}
  .fin-legenda {{ font-size: 0.82rem; color: {MUTED}; margin: 0 0 10px 0; }}

  .fin-card {{
      background: {SUPERFICIE}; border: 1px solid {BORDA}; border-radius: 14px;
      padding: 16px 18px; height: 100%;
  }}
  .fin-card .rotulo {{
      font-size: 0.76rem; font-weight: 600; letter-spacing: 0.06em;
      text-transform: uppercase; color: {MUTED}; margin: 0 0 8px 0;
  }}
  .fin-card .valor {{
      font-size: 1.85rem; font-weight: 640; color: {TEXTO};
      line-height: 1.1; margin: 0;
  }}
  .fin-card .nota {{ font-size: 0.8rem; color: {MUTED}; margin: 8px 0 0 0; }}
  .fin-card .delta {{ font-size: 0.84rem; font-weight: 600; margin: 8px 0 0 0; }}
  .delta-bom {{ color: {BOM}; }}
  .delta-ruim {{ color: {RUIM}; }}
  .delta-neutro {{ color: {MUTED}; }}

  .fin-nota-box {{
      background: {SUPERFICIE}; border: 1px solid {BORDA};
      border-left: 3px solid {ATENCAO};
      border-radius: 10px; padding: 12px 16px; margin-bottom: 8px;
      font-size: 0.88rem; color: {TEXTO_2};
  }}

  [data-testid="stMetricValue"] {{ color: {TEXTO}; }}

  /* A faixa colorida que o Streamlit desenha no topo não pertence ao painel. */
  [data-testid="stDecoration"] {{ display: none; }}

  /* st.caption sai apagado demais sobre o fundo escuro. */
  [data-testid="stCaptionContainer"] p, .stCaption p, small {{
      color: {MUTED} !important; font-size: 0.84rem;
  }}

  [data-testid="stDataFrame"] {{ border: 1px solid {BORDA}; border-radius: 10px; }}

  .stTabs [data-baseweb="tab-list"] {{ gap: 4px; border-bottom: 1px solid {BORDA}; }}
  .stTabs [data-baseweb="tab"] {{
      background: transparent; color: {MUTED}; font-weight: 560;
      padding: 10px 18px; border-radius: 8px 8px 0 0;
  }}
  .stTabs [aria-selected="true"] {{ color: {TEXTO} !important; background: {SUPERFICIE}; }}

  hr {{ border-color: {BORDA}; }}
</style>
"""


def card(rotulo: str, valor: str, nota: str = '', delta_txt: str = '',
         delta_classe: str = 'delta-neutro') -> str:
    partes = [f'<div class="fin-card"><p class="rotulo">{rotulo}</p>',
              f'<p class="valor">{valor}</p>']
    if delta_txt:
        partes.append(f'<p class="delta {delta_classe}">{delta_txt}</p>')
    if nota:
        partes.append(f'<p class="nota">{nota}</p>')
    partes.append('</div>')
    return ''.join(partes)


def titulo_secao(titulo: str, legenda: str = '') -> str:
    html = f'<p class="fin-secao">{titulo}</p>'
    if legenda:
        html += f'<p class="fin-legenda">{legenda}</p>'
    return html
