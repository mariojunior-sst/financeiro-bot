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
/resumo — totais do mês atual
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
            "Configure a variável `DASHBOARD_URL` no Railway com o link do Looker Studio.",
            parse_mode='Markdown',
        )


async def cmd_resumo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _autorizado(update):
        return

    await update.message.reply_text("Buscando dados... um momento.")

    try:
        dados = sheets.resumo_mes()
    except Exception as e:
        logger.error(f"Erro ao buscar resumo: {e}")
        await update.message.reply_text("Erro ao acessar a planilha. Tente novamente.")
        return

    agora = datetime.now()
    mes_nome = agora.strftime('%B/%Y').capitalize()
    linhas = [f"*Resumo Financeiro — {mes_nome}*\n"]

    total_receita = 0.0
    total_custo = 0.0
    ordem = ['extinprag', 'vsafety', 'pessoal']
    nomes = {'extinprag': 'EXTINPRAG', 'vsafety': 'VSAFETY', 'pessoal': 'Pessoal'}

    for cat in ordem:
        valores = dados[cat]
        r = valores['receita']
        c = valores['custo']
        saldo = r - c
        total_receita += r
        total_custo += c

        if r == 0 and c == 0:
            continue

        emoji = "🔴" if saldo < 0 else "🟢"
        linhas.append(
            f"{emoji} *{nomes[cat]}*\n"
            f"  Receitas: {lancamentos.formatar_brl(r)}\n"
            f"  Custos:   {lancamentos.formatar_brl(c)}\n"
            f"  Saldo:    {lancamentos.formatar_brl(saldo)}\n"
        )

    saldo_total = total_receita - total_custo
    emoji_total = "🔴" if saldo_total < 0 else "🟢"
    linhas.append(
        f"{'—' * 20}\n"
        f"{emoji_total} *TOTAL GERAL*\n"
        f"  Receitas: {lancamentos.formatar_brl(total_receita)}\n"
        f"  Custos:   {lancamentos.formatar_brl(total_custo)}\n"
        f"  Saldo:    {lancamentos.formatar_brl(saldo_total)}"
    )

    await update.message.reply_text('\n'.join(linhas), parse_mode='Markdown')


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

    todas_cats = lancamentos.CATEGORIAS_GASTO_FIXAS + cats_custom + ['receita']
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
    app.add_handler(CallbackQueryHandler(callback_confirmacao))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_mensagem))

    logger.info("Bot iniciado.")
    app.run_polling()


if __name__ == '__main__':
    main()
