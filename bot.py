import logging
import os
from datetime import datetime

from telegram import Update
from telegram.ext import (
    Application,
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
`custo 350 vsafety deslocamento`
`receita 800 pessoal aluguel`
`custo 150 pessoal supermercado`

Use vírgula ou ponto para decimais: `1.200,50` ou `1200.50`

*Comandos:*
/resumo — totais do mês atual
/historico — últimos 10 lançamentos
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
        cat = r.get('Categoria', '')
        data = r.get('Data', '')
        desc = r.get('Descrição', '') or '—'
        linhas.append(
            f"{emoji} {data} | {cat} | {lancamentos.formatar_brl(valor)}\n"
            f"   _{desc}_"
        )

    await update.message.reply_text('\n'.join(linhas), parse_mode='Markdown')


async def handle_mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _autorizado(update):
        return

    texto = update.message.text.strip()
    lancamento = lancamentos.parse(texto)

    if lancamento is None:
        await update.message.reply_text(
            "Não entendi. Use o formato:\n"
            "`receita 1200 extinprag descrição`\n\n"
            "Digite /ajuda para ver todos os exemplos.",
            parse_mode='Markdown',
        )
        return

    try:
        sheets.registrar(
            lancamento['tipo'],
            lancamento['valor'],
            lancamento['categoria'],
            lancamento['descricao'],
        )
    except Exception as e:
        logger.error(f"Erro ao registrar lançamento: {e}")
        await update.message.reply_text("Erro ao salvar na planilha. Tente novamente.")
        return

    emoji = "💰" if lancamento['tipo'] == 'receita' else "💸"
    await update.message.reply_text(
        f"{emoji} *Registrado!*\n\n"
        f"Tipo: {lancamento['tipo'].capitalize()}\n"
        f"Valor: {lancamentos.formatar_brl(lancamento['valor'])}\n"
        f"Empresa: {lancamento['categoria'].upper()}\n"
        f"Descrição: {lancamento['descricao'] or '—'}",
        parse_mode='Markdown',
    )


def main():
    token = os.environ['TELEGRAM_TOKEN']
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler('start', cmd_start))
    app.add_handler(CommandHandler('ajuda', cmd_ajuda))
    app.add_handler(CommandHandler('resumo', cmd_resumo))
    app.add_handler(CommandHandler('historico', cmd_historico))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_mensagem))

    logger.info("Bot iniciado.")
    app.run_polling()


if __name__ == '__main__':
    main()
