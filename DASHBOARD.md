# Dashboard Financeiro

O dashboard é um app Streamlit que roda no mesmo projeto do bot (processo `web`
no `Procfile`). Ele lê a mesma planilha e usa o mesmo módulo de cálculo do bot
(`analise.py`) — os números do `/resumo` e do painel são sempre iguais.

Não é preciso configurar Looker Studio nem montar gráfico à mão.

---

## O que o painel mostra

Uma barra de filtros no topo controla tudo:

| Filtro | Opções |
|---|---|
| **Período** | Mês atual, mês anterior, últimos 3/6/12 meses, ano, todo o período, ou um mês específico |
| **Empresa** | EXTINPRAG, VSAFETY, Pessoal (uma, várias ou todas) |
| **Analisar** | Despesas ou Receitas |

Logo abaixo, quatro indicadores com a variação contra o período anterior:
**Receitas**, **Despesas**, **Resultado** e **Taxa de poupança**.

### Aba "Visão geral"
- Receita x despesa mês a mês, barras lado a lado na mesma escala
- Resultado mensal (sobrou/faltou), com o zero como referência
- Leituras do período: ritmo de gasto por dia e projeção do fechamento, maior
  despesa, categoria que mais subiu, categoria que mais caiu
- Avisos de qualidade dos dados (lançamentos sem categoria, sem descrição,
  possíveis duplicatas, receita lançada como custo)

### Aba "Categorias"
- Ranking de gastos por categoria, com valor e percentual na ponta da barra
- Tabela com total, % do total, nº de lançamentos, ticket médio e média mensal
- **O que mudou vs o mês anterior**: diferença em reais, categoria a categoria
- **Categoria x empresa**: de qual frente sai cada gasto

### Aba "Empresas"
- Receita x despesa por centro de custo
- DRE simplificada: receita, despesa, resultado e margem
- Resultado mensal de cada empresa em painéis com a mesma escala

### Aba "Lançamentos"
- Busca por descrição ou categoria, filtro por tipo
- Tabela completa e download do recorte em CSV (`;` e vírgula decimal, abre
  direto no Excel brasileiro)
- Maiores despesas do período

---

## Como as categorias são tratadas

`Cartão`, `cartão` e `CARTAO` eram três fatias diferentes no gráfico antigo.
Agora `analise.py` normaliza tudo para um rótulo único antes de somar, e ainda
agrupa sinônimos (`combustivel` → Transporte, `restaurante` → Alimentação,
`ipva` → Impostos e Taxas). A lista fica em `CATEGORIAS_CANONICAS`, dentro de
`analise.py` — é lá que se adiciona um sinônimo novo.

Lançamento com categoria vazia vira **"Sem categoria"** e aparece no aviso de
qualidade dos dados, em vez de sumir da conta.

---

## Publicar no Railway

O `Procfile` já sobe os dois processos:

```
worker: python bot.py
web: streamlit run dashboard.py --server.port=$PORT --server.address=0.0.0.0
```

1. No Railway, o serviço `web` precisa das mesmas variáveis do bot:
   `GOOGLE_CREDENTIALS` e `SHEET_ID`
2. Em **Settings → Networking**, gere um domínio público para o serviço
3. Copie a URL e coloque na variável `DASHBOARD_URL`
4. Redeploy — o comando `/dashboard` no Telegram passa a enviar esse link

O tema escuro vem de `.streamlit/config.toml`. O Streamlit lê esse arquivo a
partir do diretório onde o comando roda, então ele precisa continuar na raiz do
projeto.

---

## Rodar na sua máquina

```bash
pip install -r requirements.txt

export GOOGLE_CREDENTIALS='{"type":"service_account", ...}'
export SHEET_ID='id_da_planilha'

streamlit run dashboard.py
```

Abre em `http://localhost:8501`. Os dados ficam em cache por 5 minutos — o botão
**Recarregar dados** força a releitura da planilha.
