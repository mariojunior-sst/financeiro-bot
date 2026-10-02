"""Contas fixas mensais — vencimentos, atrasos e o casamento com os custos.

Fonte única da verdade sobre o que está em aberto: o comando /contas, a baixa
automática e o aviso da manhã consomem as mesmas funções daqui, então os três
nunca divergem entre si — mesma ideia do `analise.py` para os lançamentos.

O valor não é cadastrado: conta fixa é fixa no *compromisso*, não no valor.
Energia e financiamento mudam todo mês. O valor real entra sozinho quando o
custo é lançado, e fica guardado só como referência do último mês.

Este módulo é puro: não fala com a planilha (isso é o `sheets.py`), só recebe
as contas já carregadas e devolve status e texto.
"""

import calendar
import os
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from lancamentos import _normalizar, formatar_brl


def _fuso():
    """Fuso de Belém, com queda para UTC-3 fixo se faltar o banco de fusos.

    Sem esse fallback, um container sem `tzdata` derrubaria o bot inteiro no
    import — e não só o lembrete. Pará não tem horário de verão, então o
    offset fixo dá exatamente o mesmo resultado.
    """
    try:
        return ZoneInfo(os.environ.get('FUSO_HORARIO', 'America/Belem'))
    except (ZoneInfoNotFoundError, KeyError, ValueError):
        return timezone(timedelta(hours=-3), 'UTC-3')


# Deixar o fuso explícito evita o bot avisar de madrugada quando o Railway
# roda o container em UTC.
FUSO = _fuso()

# A partir de quantos dias antes do vencimento o lembrete começa a cobrar.
ANTECEDENCIA_AVISO = int(os.environ.get('ANTECEDENCIA_AVISO', '5'))

# Teto de ciclos que o sistema reconstrói para trás. Sem isso, uma conta
# cadastrada hoje e nunca quitada apareceria devendo anos.
MAX_CICLOS_RETROATIVOS = 12

ATRASADO = 'atrasado'
HOJE = 'hoje'
PROXIMO = 'proximo'
EM_DIA = 'em_dia'
PAGO = 'pago'
PAUSADO = 'pausado'

EMOJI = {
    ATRASADO: '🔴',
    HOJE: '🟠',
    PROXIMO: '🟡',
    EM_DIA: '🟢',
    PAGO: '✅',
    PAUSADO: '⏸',
}

ORDEM_URGENCIA = [ATRASADO, HOJE, PROXIMO, EM_DIA, PAGO, PAUSADO]


def agora() -> datetime:
    return datetime.now(FUSO)


def hoje() -> date:
    return agora().date()


def competencia(d: date) -> str:
    """Mês de referência no formato AAAA-MM — ordenável como texto puro."""
    return f"{d.year:04d}-{d.month:02d}"


def rotulo_competencia(comp: str) -> str:
    try:
        ano, mes = comp.split('-')
        return f"{int(mes):02d}/{ano}"
    except (ValueError, AttributeError):
        return comp or '—'


def vencimento_do_mes(ano: int, mes: int, dia: int) -> date:
    """Vencimento no mês pedido, encaixando dia 31 em fevereiro sem quebrar."""
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    return date(ano, mes, max(1, min(int(dia), ultimo_dia)))


def _mes_seguinte(ano: int, mes: int) -> tuple:
    return (ano + 1, 1) if mes == 12 else (ano, mes + 1)


def ciclos_em_aberto(conta: dict, ref: date) -> list:
    """Vencimentos já chegados (<= hoje) que ainda não foram quitados.

    É o que pega o caso clássico: a conta de setembro foi paga, mas a de
    agosto passou batido. Sem isso, a virada do mês esconderia o esquecimento.
    """
    pago_ate = conta.get('pago_ate') or ''
    comp_atual = competencia(ref)

    if pago_ate >= comp_atual:
        return []

    if pago_ate:
        ano, mes = int(pago_ate[:4]), int(pago_ate[5:7])
        ano, mes = _mes_seguinte(ano, mes)
    else:
        # Conta recém-cadastrada: começa a cobrar do mês corrente, não do
        # início dos tempos.
        ano, mes = ref.year, ref.month

    abertos = []
    for _ in range(MAX_CICLOS_RETROATIVOS):
        if (ano, mes) > (ref.year, ref.month):
            break
        venc = vencimento_do_mes(ano, mes, conta['dia'])
        if venc <= ref:
            abertos.append(venc)
        ano, mes = _mes_seguinte(ano, mes)

    return abertos


def analisar(conta: dict, ref: date = None) -> dict:
    """Devolve a conta enriquecida com status, vencimento alvo e dias restantes."""
    ref = ref or hoje()
    dados = dict(conta)

    venc_atual = vencimento_do_mes(ref.year, ref.month, conta['dia'])
    dados['vencimento'] = venc_atual
    dados['dias'] = (venc_atual - ref).days
    dados['atrasados'] = []
    dados['ciclos_abertos'] = 0
    dados['competencia_alvo'] = competencia(venc_atual)

    if not conta.get('ativa', True):
        dados['status'] = PAUSADO
        return dados

    abertos = ciclos_em_aberto(conta, ref)

    if not abertos:
        if (conta.get('pago_ate') or '') >= competencia(ref):
            dados['status'] = PAGO
            # Já quitou este mês: o próximo alvo é o mês que vem.
            ano, mes = _mes_seguinte(ref.year, ref.month)
            prox = vencimento_do_mes(ano, mes, conta['dia'])
            dados['vencimento'] = prox
            dados['dias'] = (prox - ref).days
            dados['competencia_alvo'] = competencia(prox)
        elif dados['dias'] <= ANTECEDENCIA_AVISO:
            dados['status'] = PROXIMO
        else:
            dados['status'] = EM_DIA
        return dados

    # Existe coisa em aberto: o alvo da baixa é sempre o ciclo mais antigo,
    # para que um lançamento quite um mês por vez e o atraso não suma junto.
    mais_antigo = abertos[0]
    dados['vencimento'] = mais_antigo
    dados['dias'] = (mais_antigo - ref).days
    dados['competencia_alvo'] = competencia(mais_antigo)
    dados['atrasados'] = [d for d in abertos if d < ref]
    dados['ciclos_abertos'] = len(abertos)
    dados['status'] = ATRASADO if dados['atrasados'] else HOJE
    return dados


def analisar_todas(contas: list, ref: date = None) -> list:
    ref = ref or hoje()
    analisadas = [analisar(c, ref) for c in contas]
    analisadas.sort(key=lambda c: (ORDEM_URGENCIA.index(c['status']), c['vencimento']))
    return analisadas


# ---------------------------------------------------------------------------
# Casamento entre o custo lançado e a conta em aberto
# ---------------------------------------------------------------------------

# Palavras que não identificam nada sozinhas — se contassem, "conta de água" e
# "conta de luz" pareceriam meio parecidas só por causa do "conta de".
CONECTIVOS = {
    'a', 'as', 'o', 'os', 'da', 'de', 'do', 'das', 'dos', 'e', 'em', 'no', 'na',
    'nos', 'nas', 'com', 'por', 'para', 'pra', 'ao', 'aos', 'um', 'uma',
    'conta', 'contas', 'pagamento', 'pago', 'boleto', 'fatura', 'parcela', 'mes',
}

# Um token curto que bate sozinho não basta para dar baixa automática: "casa"
# aparece em "casa de carnes". A partir deste tamanho a palavra é distintiva.
TAMANHO_DISTINTIVO = 5


def _tokens(texto: str) -> list:
    norm = _normalizar(texto or '')
    return [t for t in re.findall(r'[a-z0-9]+', norm) if t not in CONECTIVOS]


def pontuar_casamento(nome: str, descricao: str) -> float:
    """Quanto da conta *nome* aparece na descrição do custo. 0 = não casou.

    Exige ou o nome inteiro presente, ou metade dele com pelo menos uma
    palavra distintiva. É o que separa "financiamento" (quita o financiamento
    da casa) de "casa de carnes" (não quita nada).
    """
    alvo = _tokens(nome)
    if not alvo:
        return 0.0

    descritos = set(_tokens(descricao))
    achados = [t for t in alvo if t in descritos]
    if not achados:
        return 0.0

    proporcao = len(achados) / len(alvo)
    if proporcao >= 1.0:
        return proporcao
    if proporcao >= 0.5 and any(len(t) >= TAMANHO_DISTINTIVO for t in achados):
        return proporcao
    return 0.0


def candidatas_para_baixa(contas: list, descricao: str, empresa: str = None,
                          ref: date = None) -> list:
    """Contas em aberto que o custo lançado pode estar quitando.

    Devolve vazio quando nada casa, um item quando o casamento é claro, e
    vários quando há empate — nesse caso quem decide é o Mário, porque baixar
    a conta errada é pior do que perguntar.
    """
    ref = ref or hoje()
    pontuadas = []

    for conta in analisar_todas(contas, ref):
        if conta['status'] in (PAGO, PAUSADO):
            continue
        if empresa and conta['empresa'] != empresa:
            continue
        nota = pontuar_casamento(conta['nome'], descricao)
        if nota > 0:
            pontuadas.append((nota, conta))

    if not pontuadas:
        return []

    melhor = max(nota for nota, _ in pontuadas)
    return [conta for nota, conta in pontuadas if nota == melhor]


# ---------------------------------------------------------------------------
# Textos
# ---------------------------------------------------------------------------

def _prazo(conta: dict) -> str:
    dias = conta['dias']
    if conta['status'] == PAUSADO:
        return 'pausada'
    if conta['atrasados']:
        atraso = abs(dias)
        plural = 's' if atraso != 1 else ''
        extra = ''
        if len(conta['atrasados']) > 1:
            extra = f" · {len(conta['atrasados'])} meses em aberto"
        return f"venceu há {atraso} dia{plural}{extra}"
    if dias == 0:
        return 'vence HOJE'
    if dias == 1:
        return 'vence amanhã'
    if dias > 0:
        return f"vence em {dias} dias"
    return f"venceu há {abs(dias)} dias"


def _referencia(conta: dict) -> str:
    """Último valor pago, quando existe — é referência, não previsão."""
    valor = conta.get('ultimo_valor')
    if not valor:
        return ''
    return f" · último: {formatar_brl(valor)}"


def linha_conta(conta: dict) -> str:
    data = conta['vencimento'].strftime('%d/%m')
    return (
        f"{EMOJI[conta['status']]} *{conta['nome']}*\n"
        f"    dia {data} · {_prazo(conta)}{_referencia(conta)}"
    )


def _total_referencia(contas: list) -> str:
    """Soma dos últimos valores conhecidos, deixando claro que é estimativa."""
    com_historico = [c for c in contas if c.get('ultimo_valor')]
    if not com_historico:
        return ''

    total = sum(c['ultimo_valor'] * max(1, c['ciclos_abertos']) for c in com_historico)
    sem_historico = len(contas) - len(com_historico)
    texto = f"\n💵 Referência (últimos valores): *{formatar_brl(total)}*"
    if sem_historico:
        plural = 's' if sem_historico > 1 else ''
        texto += f"\n_+ {sem_historico} conta{plural} sem histórico ainda_"
    return texto


def precisa_avisar(conta: dict) -> bool:
    return conta['status'] in (ATRASADO, HOJE, PROXIMO)


def montar_lembrete(contas: list, ref: date = None) -> str:
    """Texto do aviso da manhã. Devolve '' quando não há nada a cobrar.

    O silêncio é proposital: aviso que chega todo dia sem motivo vira ruído e
    deixa de ser lido justamente no dia em que importa.
    """
    ref = ref or hoje()
    pendentes = [c for c in analisar_todas(contas, ref) if precisa_avisar(c)]
    if not pendentes:
        return ''

    atrasadas = [c for c in pendentes if c['status'] == ATRASADO]
    vencem_hoje = [c for c in pendentes if c['status'] == HOJE]
    proximas = [c for c in pendentes if c['status'] == PROXIMO]

    partes = [f"⏰ *Contas a pagar* — {ref.strftime('%d/%m/%Y')}"]

    if atrasadas:
        partes.append("\n🔴 *ATRASADAS — resolver hoje*")
        partes += [linha_conta(c) for c in atrasadas]
    if vencem_hoje:
        partes.append("\n🟠 *Vencem HOJE*")
        partes += [linha_conta(c) for c in vencem_hoje]
    if proximas:
        partes.append(f"\n🟡 *Nos próximos {ANTECEDENCIA_AVISO} dias*")
        partes += [linha_conta(c) for c in proximas]

    referencia = _total_referencia(pendentes)
    if referencia:
        partes.append(referencia)
    partes.append("\n_Lance o custo normalmente que eu dou a baixa sozinho._")
    return '\n'.join(partes)


def montar_agenda_do_mes(contas: list, ref: date = None) -> str:
    """Panorama do mês inteiro — enviado no dia 1º, para ele ver o que vem."""
    ref = ref or hoje()
    ativas = [c for c in analisar_todas(contas, ref) if c['status'] != PAUSADO]
    if not ativas:
        return ''

    partes = [
        f"📅 *Agenda de contas — {ref.strftime('%m/%Y')}*",
        f"_{len(ativas)} contas fixas neste mês_\n",
    ]
    partes += [linha_conta(c) for c in sorted(ativas, key=lambda c: c['vencimento'])]
    referencia = _total_referencia(ativas)
    if referencia:
        partes.append(referencia)
    return '\n'.join(partes)


def montar_painel(contas: list, ref: date = None) -> str:
    """Resposta do /contas — tudo que existe, urgente primeiro."""
    ref = ref or hoje()
    if not contas:
        return (
            "📋 *Nenhuma conta fixa cadastrada ainda.*\n\n"
            "Cadastre com:\n"
            "`/novaconta Financiamento da casa | 10 | pessoal`\n\n"
            "_(nome | dia do vencimento | empresa)_\n"
            "_O valor não entra aqui — vem do custo que você lançar._"
        )

    analisadas = analisar_todas(contas, ref)
    ativas = [c for c in analisadas if c['status'] != PAUSADO]
    em_aberto = [c for c in ativas if c['status'] != PAGO]

    partes = [f"📋 *Contas fixas* — {ref.strftime('%d/%m/%Y')}\n"]
    partes += [linha_conta(c) for c in analisadas]

    if em_aberto:
        plural = 's' if len(em_aberto) > 1 else ''
        partes.append(f"\n⏳ *{len(em_aberto)} conta{plural} em aberto neste mês*")
        referencia = _total_referencia(em_aberto)
        if referencia:
            partes.append(referencia.lstrip('\n'))
    else:
        partes.append("\n✅ *Tudo quitado neste mês.*")

    partes.append("\n_A baixa é automática ao lançar o custo._")
    return '\n'.join(partes)
