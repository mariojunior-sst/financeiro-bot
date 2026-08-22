import logging
import os
from datetime import datetime

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
        emoji = "💰" if l['tipo'] == 'receita' else "💸"
        await query.edit_message_text(
            f"{emoji} *Registrado com sucesso!*\n\n"
            f"🏢 Empresa: {l['empresa'].upper()}\n"
            f"🗂 Categoria: {l['categoria_gasto'].title()}\n"
            f"💵 Valor: {lancamentos.formatar_brl(l['valor'])}\n"
            f"📝 Descrição: {l['descricao'] or '—'}",
            parse_mode='Markdown',
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
    app.add_handler(CallbackQueryHandler(callback_confirmacao))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_mensagem))

    logger.info("Bot iniciado.")
    app.run_polling()


if __name__ == '__main__':
    main()
