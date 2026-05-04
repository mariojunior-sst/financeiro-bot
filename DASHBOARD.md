# Dashboard Financeiro — Google Looker Studio

Tempo estimado: 20 a 30 minutos. Feito uma vez, atualiza sozinho sempre que você lançar no bot.

---

## Passo 1 — Acessar o Looker Studio

1. Acesse [lookerstudio.google.com](https://lookerstudio.google.com) com a mesma conta Google da planilha
2. Clique em **+ Criar → Relatório**

---

## Passo 2 — Conectar ao Google Sheets

1. Na tela "Adicionar dados ao relatório", selecione **Google Sheets**
2. Escolha a planilha **Financeiro**
3. Selecione a aba **Lançamentos**
4. Marque **"Usar a primeira linha como cabeçalho"** ✓
5. Clique em **Adicionar** → **Adicionar ao relatório**

---

## Passo 3 — Configurar os campos

No painel lateral direito (Dados), confirme que os campos foram reconhecidos:

| Campo | Tipo esperado |
|---|---|
| Data | Data (DD/MM/AAAA) |
| Tipo | Texto |
| Empresa | Texto |
| Categoria | Texto |
| Valor | Número |
| Descrição | Texto |

> Se "Data" aparecer como Texto: clique no campo → mude o tipo para **Data** → formato `DD/MM/AAAA`

---

## Passo 4 — Criar os gráficos

### 4.1 — Receita vs Custo por Empresa (gráfico de barras)

1. Clique em **Inserir → Gráfico de barras**
2. Dimensão: `Empresa`
3. Métrica: `Valor` (agregação: **Soma**)
4. Adicionar uma segunda dimensão de detalhamento: `Tipo`
5. Título: **Receita vs Custo por Empresa**

---

### 4.2 — Gastos por Categoria (gráfico de pizza)

1. Clique em **Inserir → Gráfico de pizza**
2. Dimensão: `Categoria`
3. Métrica: `Valor` (agregação: **Soma**)
4. Em "Filtro", adicione: `Tipo = CUSTO`
5. Título: **Onde estou gastando mais**

---

### 4.3 — Evolução mensal (gráfico de linhas)

1. Clique em **Inserir → Gráfico de série temporal**
2. Dimensão de data: `Data` → granularidade **Mês**
3. Métrica: `Valor`
4. Adicionar um segundo campo: crie uma **Métrica calculada**:
   - Nome: `Saldo`
   - Fórmula: `SUM(IF(Tipo = "RECEITA", Valor, -Valor))`
5. Título: **Evolução Mensal**

---

### 4.4 — Cartões de resumo (scorecards)

Inserir **4 scorecards** no topo do dashboard:

**Scorecard 1 — Total Receitas**
- Métrica: `Valor` → Soma
- Filtro: `Tipo = RECEITA`
- Rótulo: "Receitas do mês"

**Scorecard 2 — Total Custos**
- Métrica: `Valor` → Soma
- Filtro: `Tipo = CUSTO`
- Rótulo: "Custos do mês"

**Scorecard 3 — Saldo**
- Métrica calculada: `SUM(IF(Tipo = "RECEITA", Valor, -Valor))`
- Rótulo: "Saldo"

**Scorecard 4 — Lançamentos no mês**
- Métrica: `Contagem de registros`
- Rótulo: "Lançamentos"

---

## Passo 5 — Adicionar filtro de mês

1. Clique em **Inserir → Controle → Intervalo de datas**
2. Posicione no topo do relatório
3. Isso permite filtrar qualquer mês sem mudar os gráficos

Também adicione um filtro de empresa:
1. **Inserir → Controle → Lista suspensa**
2. Dimensão: `Empresa`
3. Isso filtra todos os gráficos por EXTINPRAG, VSAFETY ou PESSOAL

---

## Passo 6 — Copiar o link e configurar no bot

1. Clique em **Compartilhar → Gerenciar acesso**
2. Mude para **"Qualquer pessoa com o link pode visualizar"**
3. Copie o link
4. No Railway, adicione a variável de ambiente:
   ```
   DASHBOARD_URL = [cole o link aqui]
   ```
5. Faça o redeploy

Depois disso, o comando `/dashboard` no bot vai enviar o link direto pra você.

---

## Dicas de design

- Use as cores da sua marca: verde para receitas, vermelho para custos
- Fixe o filtro de data como "Mês atual" por padrão
- Dê um nome pro relatório: **Dashboard Financeiro — Mário**
- Salve como favorito no celular pra acesso rápido
