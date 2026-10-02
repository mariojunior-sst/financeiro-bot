import logging
import os
from datetime import datetime, time as hora_do_dia

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import analise
import lancamentos
import sheets
import vencimentos

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

ALLOWED_USER_ID = os.environ.get('ALLOWED_USER_ID')


def _autorizado(update: Update) -> bool:
    if not ALLOWED_USER_ID:
        return True
    return str(update.effective_user.id) == ALLOWED_USER_ID


def _teclado_confirmacao():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Confirmar", callback_data="confirmar"),
        InlineKeyboardButton("✏️ Corrigir", callback_data="corrigir"),
        InlineKeyboardButton("❌ Cancelar", callback_data="cancelar"),
    ]])


def _teclado_nova_categoria(cat: str):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(f"✅ Criar '{cat}'", callback_data=f"criar_cat:{cat}"),
        InlineKeyboardButton("❌ Usar 'outros'", callback_data="usar_outros"),
    ]])


def _montar_confirmacao(l: dict) -> str:
    cabecalho = "💰 *RECEITA identificada:*" if l['tipo'] == 'receita' else "💸 *GASTO identificado:*"
    return (
        f"{cabecalho}\n\n"
        f"🏢 Empresa: {l['empresa'].upper()}\n"
        f"🗂 Categoria: {l['categoria_gasto'].title()}\n"
        f"💵 Valor: {lancamentos.formatar_brl(l['valor'])}\n"
        f"📝 Descrição: {l['descricao'] or '—'}\n\n"
        f"Confirma o lançamento?"
    )


DASHBOARD_URL = os.environ.get('DASHBOARD_URL')

MSG_AJUDA = """
*Como registrar um lançamento:*

`[receita ou custo] [valor] [empresa] [descrição]`

*Empresas disponíveis:*
• `extinprag` — lançamentos da EXTINPRAG
• `vsafety` — lançamentos da VSAFETY
• `pessoal` — lançamentos pessoais

*Exemplos:*
`receita 1500 extinprag manutenção extintores cliente X`
`custo 200 extinprag compra de materiais`
`receita 3000 vsafety consultoria NR12 cliente Y`
`custo 150 pessoal supermercado`

*Especificar categoria manualmente:*
Adicione `#categoria` no final:
`custo 150 vsafety gasolina #transporte`

*Categorias:*
moradia • cartão • alimentação • supermercado
educação • telefone • saúde • investimento • transporte

Use vírgula ou ponto para decimais: `1.200,50` ou `1200.50`

*Contas fixas (lembrete automático):*
`/novaconta nome | dia | empresa`
Ex.: `/novaconta Financiamento da casa | 10 | pessoal`

Sem valor: ele varia mês a mês. A baixa é automática — ao lançar
`custo 2350 pessoal financiamento da casa`, a conta é quitada sozinha.

/contas — todas as contas e o que falta pagar
/lembrete — o que está vencendo agora
/pausarconta — pausar ou retomar uma conta
/paguei — baixa manual, só para conta paga fora do bot

*Comandos:*
/resumo — fechamento do mês com comparativo
/categorias — ranking de gastos por categoria
/comparar — mês atual x mês anterior, categoria a categoria
/empresas — resultado e margem de cada frente
/historico — últimos 10 lançamentos
/dashboard — link do dashboard financeiro
/ajuda — ver esta mensagem
""".strip()


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _autorizado(update):
        return
    await update.message.reply_text(
        f"Olá, Mário! Sou seu assistente financeiro.\n\n{MSG_AJUDA}",
        parse_mode='Markdown',
    )


async def cmd_ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _autorizado(update):
        return
    await update.message.reply_text(MSG_AJUDA, parse_mode='Markdown')


async def cmd_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _autorizado(update):
        return
    if DASHBOARD_URL:
        await update.message.reply_text(
            f"📊 *Dashboard Financeiro*\n\n{DASHBOARD_URL}",
            parse_mode='Markdown',
        )
    else:
        await update.message.reply_text(
            "Dashboard não configurado ainda.\n\n"
            "Configure a variável `DASHBOARD_URL` no Railway com a URL pública do serviço web.",
            parse_mode='Markdown',
        )


def _bloco(linhas: list) -> str:
    """Tabela monoespaçada — mantém as colunas de valores alinhadas no Telegram."""
    return "\n```\n" + "\n".join(linhas) + "\n```"


def _curto(texto, n: int) -> str:
    """Corta com reticências em vez de truncar no meio da palavra sem aviso."""
    texto = str(texto)
    return texto if len(texto) <= n else texto[:n - 1] + "…"


def _linha(rotulo: str, valor: str, extra: str = '', larg_rot: int = 11,
           larg_val: int = 14) -> str:
    return f"{rotulo:<{larg_rot}}{valor:>{larg_val}}  {extra}".rstrip()


def _seta(delta_pct, inverter: bool = False) -> str:
    """Sinal + percentual. `inverter` = subir é ruim (despesas)."""
    if analise.sem_comparativo(delta_pct):
        return ''
    if abs(delta_pct) < 0.05:
        return '= estável'
    subiu = delta_pct > 0
    bom = (not subiu) if inverter else subiu
    return f"{'▲' if subiu else '▼'}{abs(delta_pct):.0f}% {'👍' if bom else '👎'}"


async def _carregar(update) -> "object | None":
    """Busca a planilha e devolve o DataFrame preparado, ou None em caso de erro."""
    try:
        df = sheets.carregar_df()
    except Exception as e:
        logger.error(f"Erro ao carregar planilha: {e}")
        await update.message.reply_text("Erro ao acessar a planilha. Tente novamente.")
        return None
    if df.empty:
        await update.message.reply_text("Nenhum lançamento registrado ainda.")
        return None
    return df


def _mes_corrente(df):
    """Mês atual se houver lançamentos nele; senão, o mês mais recente da planilha."""
    import pandas as pd

    atual = pd.Period(datetime.now(), freq='M')
    meses = sorted(df['Mes'].unique())
    return atual if atual in meses else meses[-1]


async def cmd_resumo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _autorizado(update):
        return

    await update.message.reply_text("Fechando os números...")
    df = await _carregar(update)
    if df is None:
        return

    mes = _mes_corrente(df)
    anterior = analise.mes_anterior(mes)
    atual = analise.fatiar_mes(df, mes)
    base = analise.fatiar_mes(df, anterior)

    k = analise.kpis(atual)
    kb = analise.kpis(base)
    ritmo = analise.ritmo_do_mes(atual, mes)
    brl = analise.brl

    partes = [f"*RESUMO — {analise.rotulo_mes_extenso(mes).upper()}*"]
    if not ritmo['mes_fechado']:
        partes.append(f"_Parcial: dia {ritmo['dia']} de {ritmo['dias_no_mes']}_")

    partes.append(_bloco([
        _linha("Receitas", brl(k['receita']), _seta(analise.variacao(k['receita'], kb['receita']))),
        _linha("Despesas", brl(k['custo']),
               _seta(analise.variacao(k['custo'], kb['custo']), inverter=True)),
        "-" * 34,
        _linha("Resultado", brl(k['saldo'])),
        _linha("Poupança", analise.pct(k['taxa_poupanca']), "da receita"),
        _linha("Lançamen.", str(k['n'])),
    ]).lstrip())
    partes.append(f"_Comparado com {analise.rotulo_mes_extenso(anterior)}_")

    emp = analise.por_empresa(atual)
    if not emp.empty:
        linhas = []
        for _, r in emp.iterrows():
            marca = "🟢" if r['Saldo'] >= 0 else "🔴"
            margem = f"margem {analise.pct(r['Margem'], 0)}" if r['Receita'] > 0 else "só custos"
            linhas.append(f"{marca} {r['Empresa']:<10}{brl(r['Saldo']):>14}  {margem}")
        partes.append("*Por empresa*\n" + "\n".join(linhas))

    cats = analise.por_categoria(atual, 'CUSTO')
    if not cats.empty:
        linhas = [_linha(f"{i}. {_curto(r['Categoria'], 12)}", brl(r['Total']),
                         f"{analise.pct(r['Pct'], 0):>4}", larg_rot=16)
                  for i, (_, r) in enumerate(cats.head(5).iterrows(), 1)]
        partes.append("*Onde foi o dinheiro (top 5)*" + _bloco(linhas))

    if not base.empty:
        comp = analise.comparar_categorias(df, mes, anterior, 'CUSTO')
        comp = comp[comp['Delta'].abs() > 1]
        if not comp.empty:
            destaques = []
            alta = comp.iloc[0]
            if alta['Delta'] > 0:
                destaques.append(f"▲ {alta['Categoria']}: +{brl(alta['Delta'])}")
            baixa = comp.iloc[-1]
            if baixa['Delta'] < 0:
                destaques.append(f"▼ {baixa['Categoria']}: −{brl(abs(baixa['Delta']))}")
            if destaques:
                partes.append("*Maiores variações*\n" + "\n".join(destaques))

    if not ritmo['mes_fechado']:
        partes.append(
            f"*Projeção do mês*\n"
            f"No ritmo de {brl(ritmo['media_dia'])}/dia, a despesa fecha em "
            f"≈ {brl(ritmo['projecao_custo'])} "
            f"({'sobra' if ritmo['projecao_saldo'] >= 0 else 'falta'} "
            f"{brl(abs(ritmo['projecao_saldo']))})."
        )

    avisos = analise.problemas_de_dados(atual)
    if avisos:
        partes.append("⚠️ *Revisar na planilha*\n• " + "\n• ".join(avisos))

    await update.message.reply_text("\n\n".join(partes), parse_mode='Markdown')


async def cmd_categorias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _autorizado(update):
        return

    df = await _carregar(update)
    if df is None:
        return

    mes = _mes_corrente(df)
    atual = analise.fatiar_mes(df, mes)
    cats = analise.por_categoria(atual, 'CUSTO')

    if cats.empty:
        await update.message.reply_text(
            f"Nenhuma despesa registrada em {analise.rotulo_mes_extenso(mes)}.")
        return

    brl = analise.brl
    total = float(cats['Total'].sum())
    linhas = [_linha(_curto(r['Categoria'], 15), brl(r['Total']),
                     f"{analise.pct(r['Pct'], 0):>4} ({int(r['N'])}x)", larg_rot=16)
              for _, r in cats.iterrows()]
    linhas.append("-" * 42)
    linhas.append(_linha("TOTAL", brl(total), f"     ({int(cats['N'].sum())}x)", larg_rot=16))

    texto = (f"*DESPESAS POR CATEGORIA — {analise.rotulo_mes_extenso(mes)}*"
             + _bloco(linhas)
             + f"\n_Ticket médio: {brl(float(cats['Ticket'].mean()))} · "
               f"{len(cats)} categorias_")
    await update.message.reply_text(texto, parse_mode='Markdown')


async def cmd_comparar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _autorizado(update):
        return

    df = await _carregar(update)
    if df is None:
        return

    mes = _mes_corrente(df)
    anterior = analise.mes_anterior(mes)
    if analise.fatiar_mes(df, anterior).empty:
        await update.message.reply_text(
            f"Não há lançamentos em {analise.rotulo_mes_extenso(anterior)} para comparar.")
        return

    comp = analise.comparar_categorias(df, mes, anterior, 'CUSTO')
    comp = comp[comp['Delta'].abs() > 1]
    if comp.empty:
        await update.message.reply_text("Nenhuma variação relevante entre os dois meses.")
        return

    brl = analise.brl
    linhas = []
    for _, r in comp.iterrows():
        sinal = '▲' if r['Delta'] > 0 else '▼'
        variacao = ('novo' if analise.sem_comparativo(r['DeltaPct'])
                    else f"{abs(r['DeltaPct']):.0f}%")
        linhas.append(f"{sinal} {_curto(r['Categoria'], 15):<16}"
                      f"{('+' if r['Delta'] > 0 else '-') + brl(abs(r['Delta'])):>15}"
                      f"  {variacao:>5}")

    k_atual = analise.kpis(analise.fatiar_mes(df, mes))
    k_ant = analise.kpis(analise.fatiar_mes(df, anterior))
    delta_total = k_atual['custo'] - k_ant['custo']

    texto = (f"*{analise.rotulo_mes_extenso(mes)} vs {analise.rotulo_mes_extenso(anterior)}*\n"
             f"_Despesas: {brl(k_ant['custo'])} → {brl(k_atual['custo'])} "
             f"({'+' if delta_total > 0 else '−'}{brl(abs(delta_total))})_"
             + _bloco(linhas))
    await update.message.reply_text(texto, parse_mode='Markdown')


async def cmd_empresas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _autorizado(update):
        return

    df = await _carregar(update)
    if df is None:
        return

    mes = _mes_corrente(df)
    atual = analise.fatiar_mes(df, mes)
    emp = analise.por_empresa(atual)

    if emp.empty:
        await update.message.reply_text(
            f"Nenhum lançamento em {analise.rotulo_mes_extenso(mes)}.")
        return

    brl = analise.brl
    partes = [f"*RESULTADO POR EMPRESA — {analise.rotulo_mes_extenso(mes)}*"]
    for _, r in emp.iterrows():
        marca = "🟢" if r['Saldo'] >= 0 else "🔴"
        detalhe = analise.pct(r['Margem'], 1) if r['Receita'] > 0 else '—'
        partes.append(
            f"{marca} *{r['Empresa']}*" + _bloco([
                _linha("Receita", brl(r['Receita'])),
                _linha("Despesa", brl(r['Custo'])),
                _linha("Resultado", brl(r['Saldo'])),
                _linha("Margem", detalhe),
            ]))

    total_r = float(emp['Receita'].sum())
    total_c = float(emp['Custo'].sum())
    partes.append("*CONSOLIDADO*" + _bloco([
        _linha("Receita", brl(total_r)),
        _linha("Despesa", brl(total_c)),
        _linha("Resultado", brl(total_r - total_c)),
    ]))

    await update.message.reply_text("\n".join(partes), parse_mode='Markdown')


async def cmd_historico(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _autorizado(update):
        return

    try:
        registros = sheets.ultimos_lancamentos(10)
    except Exception as e:
        logger.error(f"Erro ao buscar histórico: {e}")
        await update.message.reply_text("Erro ao acessar a planilha. Tente novamente.")
        return

    if not registros:
        await update.message.reply_text("Nenhum lançamento encontrado.")
        return

    linhas = ["*Últimos lançamentos:*\n"]
    for r in reversed(registros):
        tipo = r.get('Tipo', '').upper()
        emoji = "💰" if tipo == 'RECEITA' else "💸"
        valor = float(str(r.get('Valor', 0)).replace(',', '.'))
        empresa = r.get('Empresa', r.get('Categoria', ''))
        cat = r.get('Categoria', '')
        data = r.get('Data', '')
        desc = r.get('Descrição', '') or '—'
        linhas.append(
            f"{emoji} {data} | {empresa} | {cat} | {lancamentos.formatar_brl(valor)}\n"
            f"   _{desc}_"
        )

    await update.message.reply_text('\n'.join(linhas), parse_mode='Markdown')


async def handle_mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _autorizado(update):
        return

    texto = update.message.text.strip()

    try:
        cats_custom = sheets.listar_categorias_custom()
    except Exception:
        cats_custom = []

    lancamento = lancamentos.parse(texto, cats_custom)

    if lancamento is None:
        await update.message.reply_text(
            "Não entendi. Use o formato:\n"
            "`receita 1200 extinprag descrição`\n\n"
            "Digite /ajuda para ver todos os exemplos.",
            parse_mode='Markdown',
        )
        return

    todas_cats = [lancamentos._normalizar(c) for c in lancamentos.CATEGORIAS_GASTO_FIXAS] + cats_custom + ['receita']
    cat = lancamento['categoria_gasto']

    # Categoria desconhecida — perguntar se quer criar
    if cat not in todas_cats:
        context.user_data['pendente'] = lancamento
        await update.message.reply_text(
            f"⚠️ A categoria *{cat}* não existe ainda.\n\nDeseja criá-la?",
            parse_mode='Markdown',
            reply_markup=_teclado_nova_categoria(cat),
        )
        return

    context.user_data['pendente'] = lancamento
    await update.message.reply_text(
        _montar_confirmacao(lancamento),
        parse_mode='Markdown',
        reply_markup=_teclado_confirmacao(),
    )


async def callback_confirmacao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    acao = query.data

    if acao == "confirmar":
        l = context.user_data.get('pendente')
        if not l:
            await query.edit_message_text("Nenhum lançamento pendente. Reenvie a mensagem.")
            return

        try:
            sheets.registrar(l['tipo'], l['valor'], l['empresa'], l['categoria_gasto'], l['descricao'])
        except Exception as e:
            logger.error(f"Erro ao registrar: {e}")
            await query.edit_message_text("❌ Erro ao salvar na planilha. Tente novamente.")
            return

        context.user_data.pop('pendente', None)

        # O lançamento é que dá baixa na conta fixa — não existe passo manual.
        extra, teclado = await _baixa_automatica(l)

        emoji = "💰" if l['tipo'] == 'receita' else "💸"
        await query.edit_message_text(
            f"{emoji} *Registrado com sucesso!*\n\n"
            f"🏢 Empresa: {l['empresa'].upper()}\n"
            f"🗂 Categoria: {l['categoria_gasto'].title()}\n"
            f"💵 Valor: {lancamentos.formatar_brl(l['valor'])}\n"
            f"📝 Descrição: {l['descricao'] or '—'}"
            f"{extra}",
            parse_mode='Markdown',
            reply_markup=teclado,
        )

    elif acao == "corrigir":
        context.user_data.pop('pendente', None)
        await query.edit_message_text(
            "✏️ Ok! Reenvie o lançamento com as correções.\n\n"
            "Para especificar a categoria, adicione `#categoria` no final:\n"
            "`custo 150 vsafety gasolina #transporte`",
            parse_mode='Markdown',
        )

    elif acao == "cancelar":
        context.user_data.pop('pendente', None)
        await query.edit_message_text("❌ Lançamento cancelado.")

    elif acao.startswith("criar_cat:"):
        cat_nova = acao.split(":", 1)[1]
        try:
            sheets.salvar_categoria_custom(cat_nova)
        except Exception as e:
            logger.error(f"Erro ao criar categoria: {e}")
            await query.edit_message_text("❌ Erro ao criar a categoria. Tente novamente.")
            return

        l = context.user_data.get('pendente')
        if l:
            await query.edit_message_text(
                f"✅ Categoria *{cat_nova}* criada!\n\n{_montar_confirmacao(l)}",
                parse_mode='Markdown',
                reply_markup=_teclado_confirmacao(),
            )
        else:
            await query.edit_message_text(f"✅ Categoria *{cat_nova}* criada!")

    elif acao == "usar_outros":
        l = context.user_data.get('pendente')
        if l:
            l['categoria_gasto'] = 'outros'
            context.user_data['pendente'] = l
            await query.edit_message_text(
                _montar_confirmacao(l),
                parse_mode='Markdown',
                reply_markup=_teclado_confirmacao(),
            )
        else:
            await query.edit_message_text("Nenhum lançamento pendente.")


# ---------------------------------------------------------------------------
# Contas fixas — cadastro, baixa e o lembrete que chega sozinho de manhã
# ---------------------------------------------------------------------------

HORA_LEMBRETE = os.environ.get('HORA_LEMBRETE', '07:00')

MSG_NOVA_CONTA = (
    "Formato do cadastro:\n"
    "`/novaconta nome | dia | empresa`\n\n"
    "*Exemplos:*\n"
    "`/novaconta Financiamento da casa | 10 | pessoal`\n"
    "`/novaconta Energia | 25 | extinprag`\n"
    "`/novaconta Internet | 5 | pessoal | telefone`\n\n"
    "_O valor não entra no cadastro: ele varia mês a mês e vem do custo que "
    "você lançar._\n"
    "_A categoria (4º campo) é opcional — sem ela o bot deduz pelo nome._"
)


async def _carregar_contas(update) -> "list | None":
    try:
        return sheets.listar_contas()
    except Exception as e:
        logger.error(f"Erro ao carregar contas fixas: {e}")
        await update.message.reply_text(
            "❌ Não consegui ler a aba *Contas Fixas* da planilha. Tente de novo.",
            parse_mode='Markdown',
        )
        return None


def _teclado_contas(contas: list, acao: str, valor: float = None,
                    com_nenhuma: bool = False) -> InlineKeyboardMarkup:
    """Um botão por conta. Evita numeração digitada, que muda de ordem todo dia."""
    botoes = []
    for c in contas:
        rotulo = (
            f"{vencimentos.EMOJI[c['status']]} {_curto(c['nome'], 26)} · "
            f"venc. {c['vencimento'].strftime('%d/%m')}"
        )
        dado = f"conta:{acao}:{c['linha']}:{c['competencia_alvo']}"
        if valor is not None:
            dado += f":{valor:.2f}"
        botoes.append([InlineKeyboardButton(rotulo, callback_data=dado)])
    if com_nenhuma:
        botoes.append([InlineKeyboardButton(
            "❌ Nenhuma delas", callback_data="conta:nenhuma:0:-",
        )])
    return InlineKeyboardMarkup(botoes)


async def cmd_contas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _autorizado(update):
        return
    contas = await _carregar_contas(update)
    if contas is None:
        return
    await update.message.reply_text(
        vencimentos.montar_painel(contas), parse_mode='Markdown',
    )


async def cmd_nova_conta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _autorizado(update):
        return

    bruto = update.message.text.partition(' ')[2]
    campos = [p.strip() for p in bruto.split('|')]

    if len(campos) < 3 or not campos[0]:
        await update.message.reply_text(MSG_NOVA_CONTA, parse_mode='Markdown')
        return

    nome, dia_txt, empresa = campos[0], campos[1], campos[2].lower()
    categoria = campos[3].lower() if len(campos) > 3 and campos[3] else None

    try:
        dia = int(dia_txt)
    except ValueError:
        dia = 0
    if not 1 <= dia <= 31:
        await update.message.reply_text(
            "❌ O dia do vencimento precisa ser um número de 1 a 31.\n\n"
            "_Dia 29, 30 ou 31 cai no último dia do mês quando ele for mais curto._",
            parse_mode='Markdown',
        )
        return

    if empresa not in lancamentos.CATEGORIAS:
        disponiveis = ' · '.join(f"`{c}`" for c in lancamentos.CATEGORIAS)
        await update.message.reply_text(
            f"❌ Empresa *{empresa}* não existe. Use: {disponiveis}",
            parse_mode='Markdown',
        )
        return

    deduzida = False
    if not categoria:
        categoria = lancamentos.detectar_categoria_gasto(nome)
        deduzida = categoria == 'outros'

    try:
        sheets.salvar_conta(nome, dia, empresa, categoria)
    except Exception as e:
        logger.error(f"Erro ao salvar conta fixa: {e}")
        await update.message.reply_text("❌ Erro ao salvar na planilha. Tente novamente.")
        return

    ref = vencimentos.hoje()
    prox = vencimentos.vencimento_do_mes(ref.year, ref.month, dia)

    # Cadastro feito depois do vencimento do mês: o bot não tem como saber se
    # essa parcela já foi paga, então avisa em vez de assumir.
    ressalva = ''
    if prox <= ref:
        ressalva = (
            f"\n\n⚠️ O vencimento de {prox.strftime('%d/%m')} já passou, então ela "
            f"entra como *em aberto*. Se você já pagou, use /paguei para dar baixa."
        )

    # O nome não bateu com nenhuma palavra-chave conhecida: melhor avisar do que
    # deixar a conta caindo em "Outros" e sujando o gráfico de categorias.
    if deduzida:
        ressalva += (
            "\n\n💡 Não consegui deduzir a categoria pelo nome, então ficou em "
            "*Outros*. Para escolher, informe no 4º campo:\n"
            f"`/novaconta {nome} | {dia} | {empresa} | moradia`"
        )

    await update.message.reply_text(
        f"✅ *Conta fixa cadastrada!*\n\n"
        f"📌 {nome}\n"
        f"📆 Todo dia {dia} · 🏢 {empresa.upper()} · 🗂 {categoria.title()}\n\n"
        f"Próxima cobrança na sua lista: {prox.strftime('%d/%m/%Y')}.\n"
        f"Vou te avisar {vencimentos.ANTECEDENCIA_AVISO} dias antes, às {HORA_LEMBRETE}.\n\n"
        f"Para dar baixa, é só lançar o custo como sempre:\n"
        f"`custo 2350 {empresa} {nome.lower()}`"
        f"{ressalva}",
        parse_mode='Markdown',
    )


def _texto_restantes(conta: dict) -> str:
    """Avisa quando ainda sobra mês em aberto na mesma conta.

    Quem esqueceu dois meses paga um de cada vez: dizer que ainda falta é o
    que impede o atraso antigo de sumir junto com o pagamento de hoje.
    """
    restantes = conta.get('ciclos_abertos', 1) - 1
    if restantes <= 0:
        return ''
    plural = 'meses' if restantes > 1 else 'mês'
    return f"\n🔴 Essa conta ainda tem *{restantes} {plural}* em aberto."


def _texto_baixa(conta: dict) -> str:
    comp = vencimentos.rotulo_competencia(conta['competencia_alvo'])
    return (
        f"\n\n✅ *Baixa automática:* {conta['nome']} — {comp} quitado."
        f"{_texto_restantes(conta)}"
    )


async def _baixa_automatica(l: dict) -> tuple:
    """Quita a conta fixa correspondente ao custo recém-lançado.

    Devolve (texto extra, teclado) para anexar à confirmação do lançamento.
    Falha aqui nunca derruba o lançamento: o custo já está gravado, e a baixa
    é um bônus — no pior caso a conta continua aparecendo no aviso.
    """
    if l['tipo'] != 'custo':
        return '', None

    try:
        contas = sheets.listar_contas()
    except Exception as e:
        logger.error(f"Baixa automática: falha ao ler as contas fixas: {e}")
        return '', None

    candidatas = vencimentos.candidatas_para_baixa(contas, l['descricao'], l['empresa'])
    if not candidatas:
        return '', None

    if len(candidatas) > 1:
        # Empate no casamento: baixar a conta errada é pior do que perguntar.
        return (
            "\n\n❓ *Esse custo quita qual conta fixa?*",
            _teclado_contas(candidatas, 'quita', valor=l['valor'], com_nenhuma=True),
        )

    conta = candidatas[0]
    try:
        sheets.marcar_conta_paga(conta['linha'], conta['competencia_alvo'], l['valor'])
    except Exception as e:
        logger.error(f"Baixa automática: falha ao gravar a baixa: {e}")
        return '', None

    return _texto_baixa(conta), None


async def cmd_paguei(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _autorizado(update):
        return
    contas = await _carregar_contas(update)
    if contas is None:
        return

    abertas = [
        c for c in vencimentos.analisar_todas(contas)
        if c['status'] not in (vencimentos.PAGO, vencimentos.PAUSADO)
    ]
    if not abertas:
        await update.message.reply_text(
            "✅ *Tudo quitado neste mês.* Nada em aberto.", parse_mode='Markdown',
        )
        return

    await update.message.reply_text(
        "Baixa manual — para conta paga *fora* do bot (débito automático, por "
        "exemplo). Lançando o custo normalmente, a baixa é automática.\n\n"
        "Qual conta você pagou?",
        parse_mode='Markdown',
        reply_markup=_teclado_contas(abertas, 'pagar'),
    )


async def cmd_pausar_conta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _autorizado(update):
        return
    contas = await _carregar_contas(update)
    if contas is None:
        return
    if not contas:
        await update.message.reply_text(MSG_NOVA_CONTA, parse_mode='Markdown')
        return

    await update.message.reply_text(
        "Toque para pausar (ou retomar) uma conta:",
        reply_markup=_teclado_contas(vencimentos.analisar_todas(contas), 'pausar'),
    )


async def cmd_lembrete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mesmo texto do aviso automático, sob demanda — serve de teste também."""
    if not _autorizado(update):
        return
    contas = await _carregar_contas(update)
    if contas is None:
        return

    texto = vencimentos.montar_lembrete(contas)
    if not texto:
        await update.message.reply_text(
            f"🟢 *Nada a pagar nos próximos {vencimentos.ANTECEDENCIA_AVISO} dias.*\n\n"
            "Use /contas para ver o mês inteiro.",
            parse_mode='Markdown',
        )
        return
    await update.message.reply_text(texto, parse_mode='Markdown')


async def callback_contas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    partes = query.data.split(':')
    acao = partes[1]

    if acao == 'nenhuma':
        # Só tira os botões: a confirmação do lançamento acima continua valendo.
        await query.edit_message_reply_markup(reply_markup=None)
        return

    try:
        contas = sheets.listar_contas()
    except Exception as e:
        logger.error(f"Erro ao carregar contas no callback: {e}")
        await query.edit_message_text("❌ Erro ao ler a planilha. Tente novamente.")
        return

    linha = int(partes[2])
    conta = next((c for c in contas if c['linha'] == linha), None)
    if conta is None:
        await query.edit_message_text("❌ Conta não encontrada. Use /contas para atualizar.")
        return

    if acao in ('pagar', 'quita'):
        competencia = partes[3]
        # 'quita' vem de um custo já lançado e carrega o valor; 'pagar' é a
        # baixa manual, sem valor conhecido.
        valor = float(partes[4]) if len(partes) > 4 else None

        try:
            sheets.marcar_conta_paga(linha, competencia, valor)
        except Exception as e:
            logger.error(f"Erro ao dar baixa: {e}")
            await query.edit_message_text("❌ Erro ao salvar a baixa. Tente novamente.")
            return

        # A conta lida da planilha ainda não tem os campos de análise.
        analisada = vencimentos.analisar(conta)
        analisada['competencia_alvo'] = competencia

        rotulo = vencimentos.rotulo_competencia(competencia)
        if valor is None:
            corpo = (
                f"✅ *Baixa manual:* {conta['nome']} — {rotulo} quitado.\n\n"
                "_Como foi paga fora do bot, o custo não entrou no financeiro._"
            )
        else:
            corpo = (
                f"💸 *Custo lançado e conta quitada.*\n\n"
                f"📌 {conta['nome']} — {rotulo}\n"
                f"💵 {lancamentos.formatar_brl(valor)}"
            )

        await query.edit_message_text(
            corpo + _texto_restantes(analisada), parse_mode='Markdown',
        )

    elif acao == 'pausar':
        novo_estado = not conta['ativa']
        try:
            sheets.alternar_conta_ativa(linha, novo_estado)
        except Exception as e:
            logger.error(f"Erro ao pausar conta: {e}")
            await query.edit_message_text("❌ Erro ao atualizar a planilha. Tente novamente.")
            return

        if novo_estado:
            await query.edit_message_text(
                f"▶️ *{conta['nome']}* reativada — volto a te lembrar dela.",
                parse_mode='Markdown',
            )
        else:
            await query.edit_message_text(
                f"⏸ *{conta['nome']}* pausada — não entra mais nos avisos.\n\n"
                "_O histórico continua na planilha; use /pausarconta para retomar._",
                parse_mode='Markdown',
            )


async def job_lembrete(context: ContextTypes.DEFAULT_TYPE):
    """Roda todo dia no horário configurado e só fala quando há o que cobrar."""
    if not ALLOWED_USER_ID:
        logger.warning("ALLOWED_USER_ID não definido — lembrete automático desligado.")
        return

    try:
        contas = sheets.listar_contas()
    except Exception as e:
        logger.error(f"Lembrete: falha ao ler a planilha: {e}")
        return

    ref = vencimentos.hoje()

    # No dia 1º ele recebe o mapa do mês inteiro, antes de qualquer cobrança.
    if ref.day == 1:
        agenda = vencimentos.montar_agenda_do_mes(contas, ref)
        if agenda:
            await context.bot.send_message(
                chat_id=ALLOWED_USER_ID, text=agenda, parse_mode='Markdown',
            )

    texto = vencimentos.montar_lembrete(contas, ref)
    if not texto:
        logger.info("Lembrete: nada em aberto hoje, nenhum aviso enviado.")
        return

    await context.bot.send_message(
        chat_id=ALLOWED_USER_ID, text=texto, parse_mode='Markdown',
    )


def _agendar_lembrete(app) -> None:
    if app.job_queue is None:
        logger.error(
            "JobQueue indisponível — instale python-telegram-bot[job-queue]. "
            "Os comandos de contas funcionam, mas o aviso automático não."
        )
        return

    try:
        horas, _, minutos = HORA_LEMBRETE.partition(':')
        alvo = hora_do_dia(
            hour=int(horas), minute=int(minutos or 0), tzinfo=vencimentos.FUSO,
        )
    except ValueError:
        logger.error(f"HORA_LEMBRETE inválida ({HORA_LEMBRETE}); usando 07:00.")
        alvo = hora_do_dia(hour=7, minute=0, tzinfo=vencimentos.FUSO)

    app.job_queue.run_daily(job_lembrete, time=alvo, name='lembrete_contas')
    logger.info(f"Lembrete de contas agendado para {alvo} ({vencimentos.FUSO}).")


def main():
    token = os.environ['TELEGRAM_TOKEN']
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler('start', cmd_start))
    app.add_handler(CommandHandler('ajuda', cmd_ajuda))
    app.add_handler(CommandHandler('resumo', cmd_resumo))
    app.add_handler(CommandHandler('historico', cmd_historico))
    app.add_handler(CommandHandler('dashboard', cmd_dashboard))
    app.add_handler(CommandHandler('categorias', cmd_categorias))
    app.add_handler(CommandHandler('comparar', cmd_comparar))
    app.add_handler(CommandHandler('empresas', cmd_empresas))
    app.add_handler(CommandHandler('contas', cmd_contas))
    app.add_handler(CommandHandler('novaconta', cmd_nova_conta))
    app.add_handler(CommandHandler('paguei', cmd_paguei))
    app.add_handler(CommandHandler('pausarconta', cmd_pausar_conta))
    app.add_handler(CommandHandler('lembrete', cmd_lembrete))

    # O handler de contas vem antes do genérico: o de lançamentos não tem
    # pattern e engoliria os callbacks `conta:*` se viesse primeiro.
    app.add_handler(CallbackQueryHandler(callback_contas, pattern=r'^conta:'))
    app.add_handler(CallbackQueryHandler(callback_confirmacao))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_mensagem))

    _agendar_lembrete(app)

    logger.info("Bot iniciado.")
    app.run_polling()


if __name__ == '__main__':
    main()
